from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Verity"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    LITELLM_MODEL: str = ""

    # Claude Sonnet (primary LLM when ANTHROPIC_API_KEY is set)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    GEMINI_API_KEY: str = ""

    GEMINI_MODEL: str = "gemini-2.0-flash"

    GROQ_API_KEY: str = ""

    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    LLM_PROVIDER: str = ""  # blank = auto-priority (OpenAI > Claude > Groq > Gemini)

    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/ai_interview"
    )

    REDIS_URL: str = "redis://localhost:6379"

    MODEL_NAME: str = "gemini/gemini-2.5-flash"

    MAX_CONTEXT_MESSAGES: int = 20

    MAX_INTERVIEW_DURATION_MINUTES: int = 60

    MEMORY_SUMMARY_TRIGGER: int = 15

    CONTRADICTION_CONFIDENCE_THRESHOLD: float = 0.7


@lru_cache
def get_settings():

    return Settings()


settings = get_settings()
