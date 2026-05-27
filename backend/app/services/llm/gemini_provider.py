import json

import litellm
from litellm import acompletion

from pydantic import ValidationError

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.services.llm.base_provider import (
    BaseLLMProvider
)
from app.services.llm.litellm_config import resolve_litellm_settings
from app.services.llm import health

from app.services.llm.exceptions import (
    LLMGenerationError,
    LLMParsingError,
    LLMValidationError,
)

from app.utils.json_utils import (
    clean_json_response,
    extract_json_object,
)

from app.utils.logger import logger


def _gemini_direct_settings() -> dict | None:
    """Return Gemini settings as rate-limit fallback, or None if unavailable."""
    from app.core.config import settings
    if not settings.GEMINI_API_KEY:
        return None
    model = (settings.GEMINI_MODEL or "gemini-2.0-flash").strip()
    if not model.startswith("gemini/"):
        model = f"gemini/{model}"
    return {"provider": "gemini", "model": model, "api_key": settings.GEMINI_API_KEY}


class GeminiProvider(BaseLLMProvider):

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    async def generate_structured_output(

        self,
        system_prompt: str,
        user_prompt: str,
        response_schema,

    ):

        logger.info(
            "Generating structured output"
        )

        # =========================
        # LLM GENERATION
        # =========================

        try:
            llm = resolve_litellm_settings()
            if not llm.get("api_key"):
                health.record_fail("no_api_key")
                raise LLMGenerationError("No LLM API key configured (set GROQ_API_KEY or GEMINI_API_KEY).")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt + "\n\nReturn ONLY valid JSON."},
            ]

            try:
                response = await acompletion(
                    model=llm["model"],
                    messages=messages,
                    api_key=llm["api_key"],
                )
            except litellm.RateLimitError:
                # Primary provider rate-limited — skip retries, try Gemini immediately
                fallback = _gemini_direct_settings()
                if fallback and fallback["model"] != llm.get("model"):
                    logger.warning(
                        "Structured output rate-limited by %s, falling back to Gemini",
                        llm.get("provider"),
                    )
                    response = await acompletion(
                        model=fallback["model"],
                        messages=messages,
                        api_key=fallback["api_key"],
                    )
                else:
                    raise

        except litellm.RateLimitError as e:
            logger.error(f"LLM generation rate-limited (no fallback available): {e}")
            health.record_exception(e)
            raise LLMGenerationError(str(e))

        except LLMGenerationError:
            raise

        except Exception as e:

            logger.error(
                f"LLM generation failed: {e}"
            )

            health.record_exception(e)
            raise LLMGenerationError(
                str(e)
            )

        # =========================
        # JSON PARSING
        # =========================

        try:

            raw_text = (
                response.choices[0]
                .message
                .content
            )

            cleaned = clean_json_response(
                raw_text
            )

            extracted = extract_json_object(
                cleaned
            )

            parsed_json = json.loads(
                extracted
            )

            # Gemini sometimes wraps:
            # {"evaluation": {...}}

            if (
                isinstance(parsed_json, dict)
                and len(parsed_json) == 1
                and not any(
                    k in response_schema.model_fields
                    for k in parsed_json
                )
            ):

                parsed_json = next(
                    iter(parsed_json.values())
                )

        except Exception as e:

            logger.error(
                f"JSON parsing failed: {e}"
            )

            raise LLMParsingError(
                str(e)
            )

        # =========================
        # SCHEMA VALIDATION
        # =========================

        try:

            parsed = response_schema.model_validate(
                parsed_json
            )

            logger.info(
                "Structured output validated"
            )

            health.record_ok()
            return parsed

        except ValidationError:

            logger.warning(
                "Initial schema validation failed. "
                "Attempting fallback normalization."
            )

            try:

                # Common LLM field alias repair

                key_mapping = {

                    # contradiction aliases
                    "contradiction":
                        "contradiction_detected",

                    "detection":
                        "contradiction_detected",

                    "reason":
                        "contradiction_reason",

                    "reasoning":
                        "contradiction_reason",

                    "severity":
                        "severity_score",

                    "confidence":
                        "confidence_score",

                    "topics":
                        "related_topics",

                    # generic aliases
                    "score":
                        "severity_score",

                    "followup":
                        "follow_up_question",

                    "followup_question":
                        "follow_up_question",
                }

                normalized = {}

                for key, value in parsed_json.items():

                    normalized_key = (
                        key_mapping.get(key, key)
                    )

                    normalized[
                        normalized_key
                    ] = value

                # Add safe defaults

                schema_fields = (
                    response_schema.model_fields
                )

                for field_name in schema_fields:

                    if field_name not in normalized:

                        field_info = (
                            schema_fields[field_name]
                        )

                        annotation = (
                            field_info.annotation
                        )

                        if annotation == bool:

                            normalized[field_name] = False

                        elif annotation == float:

                            normalized[field_name] = 0.0

                        elif annotation == list[str]:

                            normalized[field_name] = []

                        else:

                            normalized[field_name] = ""

                parsed = response_schema.model_validate(
                    normalized
                )

                logger.info(
                    "Fallback schema normalization succeeded"
                )

                health.record_ok()
                return parsed

            except Exception as normalization_error:

                logger.error(
                    "Schema normalization failed: "
                    f"{normalization_error}"
                )

                raise LLMValidationError(
                    str(normalization_error)
                )
