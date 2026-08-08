import os
import logging
from typing import Optional
from langchain_openai import ChatOpenAI
from backend.app.core.config import settings

logger = logging.getLogger("autonomous_agent.agent.llm")

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
