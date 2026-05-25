from __future__ import annotations

import json

from litellm import acompletion
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.llm.base_provider import BaseLLMProvider
from app.services.llm.exceptions import LLMGenerationError, LLMParsingError, LLMValidationError
from app.utils.json_utils import clean_json_response, extract_json_object
from app.utils.logger import logger


class ClaudeProvider(BaseLLMProvider):
    """LLM provider backed by Claude Sonnet via LiteLLM.

    Uses the same interface as GeminiProvider so factory.py can swap them
    transparently. Structured output is obtained via JSON-mode instructions
    (no Anthropic tool_use required, keeps LiteLLM as the only transport).
    """

    def _settings(self) -> dict[str, str]:
        import os
        from app.core.config import settings as cfg

        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5").strip()
        if not model.startswith("anthropic/"):
            model = f"anthropic/{model}"
        return {
            "provider": "anthropic",
            "model": model,
            "api_key": os.getenv("ANTHROPIC_API_KEY", "").strip() or getattr(cfg, "ANTHROPIC_API_KEY", ""),
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_structured_output(self, system_prompt: str, user_prompt: str, response_schema):
        logger.info("ClaudeProvider: generating structured output")

        llm = self._settings()
        if not llm.get("api_key"):
            raise LLMGenerationError("No ANTHROPIC_API_KEY configured.")

        schema_hint = _schema_to_hint(response_schema)
        augmented_system = (
            f"{system_prompt}\n\n"
            f"Return ONLY valid JSON matching this schema:\n{schema_hint}"
        )

        try:
            response = await acompletion(
                model=llm["model"],
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
                system=augmented_system,
                api_key=llm["api_key"],
            )
        except Exception as exc:
            logger.error("ClaudeProvider generation failed: %s", exc)
            raise LLMGenerationError(str(exc))

        raw_text = (response.choices[0].message.content or "").strip()

        try:
            cleaned = clean_json_response(raw_text)
            extracted = extract_json_object(cleaned)
            parsed_json = json.loads(extracted)

            if (
                isinstance(parsed_json, dict)
                and len(parsed_json) == 1
                and not any(k in response_schema.model_fields for k in parsed_json)
            ):
                parsed_json = next(iter(parsed_json.values()))
        except Exception as exc:
            logger.error("ClaudeProvider JSON parse failed: %s", exc)
            raise LLMParsingError(str(exc))

        try:
            return response_schema.model_validate(parsed_json)
        except ValidationError:
            logger.warning("ClaudeProvider initial validation failed, trying normalization")
            try:
                return _normalize_and_validate(parsed_json, response_schema)
            except Exception as exc:
                raise LLMValidationError(str(exc))


def _schema_to_hint(schema) -> str:
    """Build a compact field-list hint from Pydantic model fields."""
    try:
        fields = schema.model_fields
        lines = []
        for name, info in fields.items():
            annotation = getattr(info, "annotation", None)
            type_name = getattr(annotation, "__name__", str(annotation))
            lines.append(f'  "{name}": <{type_name}>')
        return "{\n" + ",\n".join(lines) + "\n}"
    except Exception:
        return "{}"


def _normalize_and_validate(parsed_json: dict, schema):
    key_mapping = {
        "contradiction": "contradiction_detected",
        "detection": "contradiction_detected",
        "reason": "contradiction_reason",
        "reasoning": "contradiction_reason",
        "severity": "severity_score",
        "confidence": "confidence_score",
        "topics": "related_topics",
        "score": "severity_score",
        "followup": "follow_up_question",
        "followup_question": "follow_up_question",
    }
    normalized = {key_mapping.get(k, k): v for k, v in parsed_json.items()}
    for field_name, field_info in schema.model_fields.items():
        if field_name not in normalized:
            ann = getattr(field_info, "annotation", None)
            if ann == bool:
                normalized[field_name] = False
            elif ann == float:
                normalized[field_name] = 0.0
            elif ann == list:
                normalized[field_name] = []
            else:
                normalized[field_name] = ""
    return schema.model_validate(normalized)
