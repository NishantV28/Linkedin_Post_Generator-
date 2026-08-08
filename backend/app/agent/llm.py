import os
import logging
from typing import Any, Optional, Type
from langchain_openai import ChatOpenAI
from backend.app.core.config import settings

logger = logging.getLogger("autonomous_agent.agent.llm")

# Groq only supports the `json_schema` response format on some models. Everything
# else must go through tool calling instead. Getting this wrong fails every request
# with a 400, which previously surfaced as fabricated editorial rejections.
JSON_SCHEMA_MODEL_PREFIXES = ("openai/gpt-oss", "gpt-4", "gpt-5", "o1", "o3")

# Attempts per structured-output call, covering transient malformed tool calls.
STRUCTURED_OUTPUT_ATTEMPTS = 3


def structured_output_method(model_name: str) -> Optional[str]:
    """Return the structured-output method to use, or None for the library default."""
    if model_name.startswith(JSON_SCHEMA_MODEL_PREFIXES):
        return None  # native json_schema support
    return "function_calling"


def get_structured_llm(schema: Type[Any], temperature: float = 0.2, model_name: Optional[str] = None):
    """
    Build a chat model bound to a structured output schema, choosing the method the
    configured model actually supports. Use this rather than calling
    `with_structured_output` directly, so a model swap stays a config change.

    Retries because structured output is unreliable on some models: llama-3.3-70b
    returns a malformed tool call ("tool_use_failed") roughly one time in three for
    the post-drafting schema. That is transient and succeeds on a retry, unlike a
    rate limit, which exhausts the attempts and correctly surfaces as an error.
    """
    llm = get_llm(model_name=model_name, temperature=temperature)
    method = structured_output_method(llm.model_name)
    if method:
        structured = llm.with_structured_output(schema, method=method)
    else:
        structured = llm.with_structured_output(schema)
    return structured.with_retry(stop_after_attempt=STRUCTURED_OUTPUT_ATTEMPTS)

def get_llm(model_name: Optional[str] = None, temperature: float = 0.7) -> ChatOpenAI:
    """
    Returns a configured LangChain Chat model.
    Prioritizes GROQ_API_KEY (ultra-fast inference via Groq API) if present,
    otherwise falls back to OPENAI_API_KEY.
    """
    groq_api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY")
    openai_api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")

    if groq_api_key and groq_api_key != "your_groq_api_key_here":
        selected_model = model_name or settings.LLM_MODEL or "llama-3.3-70b-versatile"
        base_url = settings.LLM_BASE_URL or "https://api.groq.com/openai/v1"
        logger.info(f"Initializing Groq ChatOpenAI client (Model: {selected_model})")
        return ChatOpenAI(
            api_key=groq_api_key,
            base_url=base_url,
            model=selected_model,
            temperature=temperature
        )

    if openai_api_key and openai_api_key != "your_openai_api_key_here":
        selected_model = model_name or settings.LLM_MODEL or "gpt-4o-mini"
        logger.info(f"Initializing OpenAI ChatOpenAI client (Model: {selected_model})")
        return ChatOpenAI(
            api_key=openai_api_key,
            model=selected_model,
            temperature=temperature
        )

    raise ValueError(
        "No LLM API key provided. Please add GROQ_API_KEY or OPENAI_API_KEY to your .env file."
    )
