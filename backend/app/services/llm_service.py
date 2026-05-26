from __future__ import annotations

import json
import os
from typing import Any

from litellm import completion

from app.utils.json_utils import clean_json_response, extract_json_object


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

        provider = self.active_provider()
        if provider == "groq":
            text = self._generate_groq(system_prompt, user_payload, temperature, max_tokens)
            if text:
                health.record_ok()
            else:
                health.record_fail("groq_empty_or_error")
            return text or fallback
        if provider == "gemini":
            text = self._generate_gemini(system_prompt, user_payload, temperature, max_tokens)
            if text:
                health.record_ok()
            else:
                health.record_fail("gemini_empty_or_error")
            return text or fallback
        health.record_fail("no_provider_configured")
        return fallback

    def _generate_groq(self, system_prompt: str, user_payload: dict[str, Any] | str, temperature: float, max_tokens: int) -> str:
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            return ""
        body = {
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _payload_to_text(user_payload)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = _post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            body,
            {"Authorization": f"Bearer {key}", "User-Agent": "ClioInterviewLab/1.0"},
        )
        if not raw_text:
            return None
        try:
            parsed = json.loads(extract_json_object(clean_json_response(raw_text)))
            if (
                isinstance(parsed, dict)
                and len(parsed) == 1
                and not any(key in response_schema.model_fields for key in parsed)
            ):
                parsed = next(iter(parsed.values()))
            return response_schema.model_validate(parsed)
        except Exception:
            return None

    def _generate_litellm(
        self,
        system_prompt: str,
        user_payload: dict[str, Any] | str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        settings = self._litellm_settings()
        if not settings.get("api_key"):
            return ""
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
            return (response.choices[0].message.content or "").strip()
        except Exception:
            return ""

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
