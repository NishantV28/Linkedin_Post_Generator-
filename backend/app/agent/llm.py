import os
import logging
import time
from typing import Any, Optional, Tuple, Type

import openai
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from backend.app.core.config import settings

logger = logging.getLogger("autonomous_agent.agent.llm")

# Groq only supports the `json_schema` response format on some models. Everything
# else must go through tool calling instead. Getting this wrong fails every request
# with a 400, which previously surfaced as fabricated editorial rejections.
JSON_SCHEMA_MODEL_PREFIXES = ("openai/gpt-oss", "gpt-4", "gpt-5", "o1", "o3")

# Fallback when LLM_MODEL is unset. Deliberately not a llama model: those need tool
# calling instead of json_schema, fail it roughly 1 time in 3, and score candidates
# more leniently than the thresholds in the persona presets assume.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

# Attempts per structured-output call, covering transient malformed tool calls.
STRUCTURED_OUTPUT_ATTEMPTS = 3

# Failures worth retrying on the same model. Rate limits are deliberately excluded:
# they do not clear in seconds, so the fallback model should be reached immediately.
RETRYABLE_ERRORS = (
    openai.BadRequestError,       # malformed tool call - llama does this ~1 in 3
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


def structured_output_method(model_name: str) -> Optional[str]:
    """Return the structured-output method to use, or None for the library default."""
    if model_name.startswith(JSON_SCHEMA_MODEL_PREFIXES):
        return None  # native json_schema support
    return "function_calling"


class LLMCheck(BaseModel):
    """Trivial schema used only to prove structured output works."""
    ok: bool = Field(..., description="Always true")


def validate_llm_configuration() -> Tuple[bool, str]:
    """
    Prove at startup that the configured model can actually return structured output.

    Every node depends on this, and when it fails it fails for every candidate. The
    agent has twice been left publishing nothing for hours because a model silently
    rejected the request format - once a 400 for an unsupported response format, once
    an exhausted token quota - while the logs showed ordinary editorial activity.

    One cheap call at startup turns that into a message an operator can act on.
    """
    try:
        checker = get_structured_llm(LLMCheck, temperature=0.0)
        checker.invoke([
            ("system", "Reply with ok=true."),
            ("user", "ping"),
        ])
    except Exception as exc:
        detail = str(exc)
        model = settings.LLM_MODEL or "(provider default)"
        if "rate_limit" in detail or "429" in detail:
            return False, (
                f"Model '{model}' is reachable but rate limited right now. Cycles will "
                f"abort until quota frees up. Detail: {detail[:200]}"
            )
        if "response_format" in detail or "json_schema" in detail or "tool_use_failed" in detail:
            return False, (
                f"Model '{model}' cannot produce the structured output every node "
                f"requires. Choose a model that supports it, or the agent will publish "
                f"nothing. Detail: {detail[:200]}"
            )
        return False, f"Model '{model}' failed a startup check: {detail[:200]}"

    return True, f"Structured output confirmed for model '{settings.LLM_MODEL or '(provider default)'}'."


def _throttle(value: Any) -> Any:
    """
    Pause before a model call.

    Placed inside the retry and fallback wrappers so every attempt is spaced, not just
    the first. A cycle fires a dozen calls back to back, which is what trips per-minute
    limits even when the daily budget is fine.
    """
    delay = settings.LLM_CALL_DELAY_SECONDS
    if delay and delay > 0:
        time.sleep(delay)
    return value


def _build_structured(schema: Type[Any], model_name: Optional[str], temperature: float):
    """One model, bound to the schema, throttled and retried."""
    llm = get_llm(model_name=model_name, temperature=temperature)
    method = structured_output_method(llm.model_name)
    structured = (
        llm.with_structured_output(schema, method=method) if method
        else llm.with_structured_output(schema)
    )

    # Retry only what retrying can actually fix. A malformed tool call or a dropped
    # connection succeeds on a second attempt; a rate limit will not, and retrying
    # into it just delays the fallback that would have worked.
    return (RunnableLambda(_throttle) | structured).with_retry(
        retry_if_exception_type=RETRYABLE_ERRORS,
        stop_after_attempt=STRUCTURED_OUTPUT_ATTEMPTS,
    )


def fallback_models() -> list:
    """Configured fallback model names, minus the primary and any blanks."""
    primary = (settings.LLM_MODEL or "").strip()
    names = [n.strip() for n in (settings.LLM_FALLBACK_MODELS or "").split(",")]
    return [n for n in names if n and n != primary]


def get_structured_llm(schema: Type[Any], temperature: float = 0.2, model_name: Optional[str] = None):
    """
    Build a chat model bound to a structured output schema, with throttling, retries
    and model fallbacks.

    Use this rather than calling `with_structured_output` directly: it selects the
    structured-output method the model supports, so swapping models stays a config
    change rather than a code change.

    Fallbacks matter because each Groq model has its own quota. Exhausting the primary
    used to stall every cycle until the window refilled; now the run continues on the
    next model, which is a smaller quality cost than publishing nothing.
    """
    primary = _build_structured(schema, model_name, temperature)

    # An explicit model_name is a deliberate choice by the caller - do not silently
    # substitute a different one.
    if model_name is not None:
        return primary

    alternates = [_build_structured(schema, name, temperature) for name in fallback_models()]
    if not alternates:
        return primary
    return primary.with_fallbacks(alternates)

def get_llm(model_name: Optional[str] = None, temperature: float = 0.7) -> ChatOpenAI:
    """
    Returns a configured LangChain Chat model.
    Prioritizes GROQ_API_KEY (ultra-fast inference via Groq API) if present,
    otherwise falls back to OPENAI_API_KEY.
    """
    groq_api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY")
    openai_api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")

    if groq_api_key and groq_api_key != "your_groq_api_key_here":
        selected_model = model_name or settings.LLM_MODEL or DEFAULT_GROQ_MODEL
        base_url = settings.LLM_BASE_URL or "https://api.groq.com/openai/v1"
        logger.debug(f"Groq client ready (model: {selected_model})")
        return ChatOpenAI(
            api_key=groq_api_key,
            base_url=base_url,
            model=selected_model,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT_SECONDS
        )

    if openai_api_key and openai_api_key != "your_openai_api_key_here":
        selected_model = model_name or settings.LLM_MODEL or "gpt-4o-mini"
        logger.debug(f"OpenAI client ready (model: {selected_model})")
        return ChatOpenAI(
            api_key=openai_api_key,
            model=selected_model,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT_SECONDS
        )

    raise ValueError(
        "No LLM API key provided. Please add GROQ_API_KEY or OPENAI_API_KEY to your .env file."
    )
