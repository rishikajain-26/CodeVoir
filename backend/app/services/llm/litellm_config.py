from __future__ import annotations

from app.core.config import settings


def resolve_litellm_settings() -> dict[str, str]:
    """
    Pick model + API key for LiteLLM.

    Priority: explicit override → Claude (if ANTHROPIC_API_KEY) → Groq → Gemini → unconfigured.
    Claude Sonnet is preferred when available for richer interview responses.
    """
    explicit = (settings.LLM_PROVIDER or "").strip().lower()

    if explicit == "anthropic" and settings.ANTHROPIC_API_KEY:
        return _anthropic_settings()

    if explicit == "gemini" and settings.GEMINI_API_KEY:
        return _gemini_settings()

    if explicit == "groq" and settings.GROQ_API_KEY:
        return _groq_settings()

    # Default priority: Claude > Groq > Gemini
    if settings.ANTHROPIC_API_KEY:
        return _anthropic_settings()

    if settings.GROQ_API_KEY:
        return _groq_settings()

    if settings.GEMINI_API_KEY:
        return _gemini_settings()

    model = settings.MODEL_NAME or "gemini/gemini-2.0-flash"
    return {
        "provider": "unconfigured",
        "model": model,
        "api_key": settings.GEMINI_API_KEY or "",
    }


def _groq_settings() -> dict[str, str]:
    model = (settings.GROQ_MODEL or "llama-3.3-70b-versatile").strip()
    if not model.startswith("groq/"):
        model = f"groq/{model}"
    return {
        "provider": "groq",
        "model": model,
        "api_key": settings.GROQ_API_KEY,
    }


def _anthropic_settings() -> dict[str, str]:
    model = (settings.ANTHROPIC_MODEL or "claude-sonnet-4-5").strip()
    if not model.startswith("anthropic/"):
        model = f"anthropic/{model}"
    return {
        "provider": "anthropic",
        "model": model,
        "api_key": settings.ANTHROPIC_API_KEY,
    }


def _gemini_settings() -> dict[str, str]:
    model = (settings.GEMINI_MODEL or settings.MODEL_NAME or "gemini-2.0-flash").strip()
    if not model.startswith("gemini/"):
        model = f"gemini/{model}"
    return {
        "provider": "gemini",
        "model": model,
        "api_key": settings.GEMINI_API_KEY,
    }
