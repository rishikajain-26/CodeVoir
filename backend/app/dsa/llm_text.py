from __future__ import annotations

import litellm
from litellm import acompletion

from app.services.llm.litellm_config import resolve_litellm_settings
from app.services.llm import health
from app.utils.logger import logger


def _gemini_fallback_settings() -> dict[str, str] | None:
    """Return Gemini settings directly as a rate-limit fallback, or None if unavailable."""
    from app.core.config import settings
    if not settings.GEMINI_API_KEY:
        return None
    model = (settings.GEMINI_MODEL or "gemini-2.0-flash").strip()
    if not model.startswith("gemini/"):
        model = f"gemini/{model}"
    return {"provider": "gemini", "model": model, "api_key": settings.GEMINI_API_KEY}


async def _call_llm(
    llm: dict,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    response = await acompletion(
        model=llm["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        api_key=llm["api_key"],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.35,
    max_tokens: int = 220,
) -> str:
    llm = resolve_litellm_settings()
    if not llm.get("api_key"):
        logger.warning("DSA text generation skipped: no API key configured")
        health.record_fail("no_api_key")
        return ""
    try:
        text = await _call_llm(llm, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
        if text:
            health.record_ok()
        else:
            health.record_fail("empty_response")
        return text
    except litellm.RateLimitError:
        # Primary provider rate-limited — try Gemini fallback
        fallback = _gemini_fallback_settings()
        if fallback and fallback["model"] != llm.get("model"):
            logger.warning("DSA text generation rate-limited by %s, falling back to Gemini", llm.get("provider"))
            try:
                text = await _call_llm(fallback, system_prompt, user_prompt, temperature=temperature, max_tokens=max_tokens)
                if text:
                    health.record_ok()
                else:
                    health.record_fail("empty_response")
                return text
            except Exception as exc2:
                logger.warning("DSA text generation Gemini fallback also failed: %s", exc2)
        health.record_fail("rate_limited")
        return ""
    except Exception as exc:
        logger.warning("DSA text generation failed (%s): %s", llm.get("provider"), exc)
        health.record_fail(str(exc))
        return ""
