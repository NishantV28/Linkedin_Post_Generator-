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
    
    # Posting Cadence Bounds (hours)
    CADENCE_MIN_HOURS: float = 2.0
    CADENCE_MAX_HOURS: float = 5.0
    MAX_POSTS_48H: int = 16
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
