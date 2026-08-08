from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    """Application settings and environment configuration."""
    
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # SQLite Database
    DATABASE_URL: str = "sqlite:///./post_generator.db"
    
    # LLM & Search API Keys
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    
    # LLM Provider & Model Settings
    LLM_MODEL: Optional[str] = None  # e.g., 'llama-3.3-70b-versatile' for Groq or 'gpt-4o-mini' for OpenAI
    LLM_BASE_URL: Optional[str] = None
    
    # Posting cadence fallback, used only when a persona defines no cadence of its own.
    CADENCE_MIN_HOURS: float = 2.0
    CADENCE_MAX_HOURS: float = 5.0

    # Demo/test override. When both are set they win over the persona's cadence
    # everywhere, so a full autonomous loop can be observed in minutes instead of
    # hours. Leave unset for real runs - cadence is part of the persona's identity.
    CADENCE_OVERRIDE_MIN_HOURS: Optional[float] = None
    CADENCE_OVERRIDE_MAX_HOURS: Optional[float] = None

    MAX_POSTS_48H: int = 16
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
