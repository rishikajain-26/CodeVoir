from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    APP_NAME: str = "Verity"

    GEMINI_API_KEY: str = ""

    LLM_PROVIDER: str = "gemini"

    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/ai_interview"
    )

    REDIS_URL: str = "redis://localhost:6379"

    MODEL_NAME: str = "gemini/gemini-2.5-flash"

    MAX_CONTEXT_MESSAGES: int = 20

    MAX_INTERVIEW_DURATION_MINUTES: int = 60

    MEMORY_SUMMARY_TRIGGER: int = 15

    CONTRADICTION_CONFIDENCE_THRESHOLD: float = 0.7

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():

    return Settings()


settings = get_settings()