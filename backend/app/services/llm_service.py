from __future__ import annotations

import json
from typing import Any, Type, TypeVar

from litellm import completion
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMService:
    """Small API-ready LLM gateway with deterministic no-key fallback behavior."""

    def is_configured(self) -> bool:
        return bool(self._litellm_settings().get("api_key"))

    def active_provider(self) -> str:
        settings = self._litellm_settings()
        provider = settings.get("provider", "unconfigured")
        return "local" if provider == "unconfigured" else provider

    def status(self) -> dict[str, Any]:
        provider = self.active_provider()
        litellm_settings = self._litellm_settings()
        return {
            "provider": provider,
            "configured": self.is_configured(),
            "model": litellm_settings.get("model", ""),
            "dsa_graph_model": litellm_settings.get("model", ""),
            "dsa_graph_provider": litellm_settings.get("provider", ""),
            "fallback": "deterministic_local",
        }

    def generate(
        self,
        system_prompt: str,
        user_payload: dict[str, Any] | str,
        *,
        fallback: str = "",
        temperature: float = 0.45,
        max_tokens: int = 220,
    ) -> str:
        from app.services.llm import health

        settings = self._litellm_settings()
        provider = self.active_provider()
        if settings.get("api_key"):
            text, failure_reason = self._generate_litellm(system_prompt, user_payload, temperature, max_tokens)
            if text:
                health.record_ok()
            else:
                health.record_fail(failure_reason or f"{provider}_empty_or_error")
            return text or fallback
        health.record_fail("no_provider_configured")
        return fallback

    def generate_structured(
        self,
        system_prompt: str,
        user_payload: str,
        schema: Type[T],
        *,
        max_tokens: int = 650,
        temperature: float = 0.2,
    ) -> T | None:
        """Call the LLM and parse the response into a validated Pydantic model.

        Returns None if the LLM is not configured, generation fails, or the
        response cannot be validated against the schema.
        """
        from app.utils.json_utils import clean_json_response, extract_json_object

        if not self.is_configured():
            return None
        text, _ = self._generate_litellm(system_prompt, user_payload, temperature, max_tokens)
        if not text:
            return None
        try:
            cleaned = clean_json_response(text)
            extracted = extract_json_object(cleaned)
            parsed = json.loads(extracted)
            return schema.model_validate(parsed)
        except (ValueError, ValidationError, Exception):
            return None

    def _generate_litellm(
        self,
        system_prompt: str,
        user_payload: dict[str, Any] | str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, str]:
        from app.services.llm import health

        settings = self._litellm_settings()
        if not settings.get("api_key"):
            return "", "no_api_key"
        try:
            response = completion(
                model=settings["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _payload_to_text(user_payload)},
                ],
                api_key=settings["api_key"],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip(), "empty_response"
        except Exception as exc:
            return "", health.classify_failure(exc, f"{settings.get('provider', 'llm')}_error")

    def _litellm_settings(self) -> dict[str, str]:
        try:
            from app.services.llm.litellm_config import resolve_litellm_settings

            return resolve_litellm_settings()
        except Exception:
            return {"provider": "unconfigured", "model": "", "api_key": ""}


def _payload_to_text(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=True)


llm_service = LLMService()
