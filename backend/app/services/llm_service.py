from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMService:
    """Small API-ready LLM gateway with deterministic no-key fallback behavior."""

    def is_configured(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY"))

    def active_provider(self) -> str:
        if os.getenv("LLM_PROVIDER", "").lower() == "gemini" and os.getenv("GEMINI_API_KEY"):
            return "gemini"
        if os.getenv("GROQ_API_KEY"):
            return "groq"
        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        return "local"

    def status(self) -> dict[str, Any]:
        provider = self.active_provider()
        model = ""
        if provider == "groq":
            model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        elif provider == "gemini":
            model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        return {
            "provider": provider,
            "configured": self.is_configured(),
            "model": model,
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
        provider = self.active_provider()
        if provider == "groq":
            text = self._generate_groq(system_prompt, user_payload, temperature, max_tokens)
            return text or fallback
        if provider == "gemini":
            text = self._generate_gemini(system_prompt, user_payload, temperature, max_tokens)
            return text or fallback
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
        choices = data.get("choices") or [{}]
        return choices[0].get("message", {}).get("content", "").strip()

    def _generate_gemini(self, system_prompt: str, user_payload: dict[str, Any] | str, temperature: float, max_tokens: int) -> str:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return ""
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        body = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{_payload_to_text(user_payload)}"}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        data = _post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
            body,
            {},
        )
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return " ".join(part.get("text", "") for part in parts).strip()


def _payload_to_text(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=True)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
        return {}


llm_service = LLMService()
