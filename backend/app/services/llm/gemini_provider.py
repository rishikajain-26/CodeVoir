import json

from litellm import acompletion

from pydantic import ValidationError

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

from app.services.llm.base_provider import (
    BaseLLMProvider
)

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


class GeminiProvider(BaseLLMProvider):

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=1,
            min=2,
            max=10,
        ),
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

            response = await acompletion(

                model=settings.MODEL_NAME,

                messages=[

                    {
                        "role": "system",
                        "content": system_prompt,
                    },

                    {
                        "role": "user",
                        "content": (
                            user_prompt
                            + "\n\nReturn ONLY valid JSON."
                        ),
                    },
                ],

                api_key=settings.GEMINI_API_KEY,
            )

        except Exception as e:

            logger.error(
                f"LLM generation failed: {e}"
            )

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

                return parsed

            except Exception as normalization_error:

                logger.error(
                    "Schema normalization failed: "
                    f"{normalization_error}"
                )

                raise LLMValidationError(
                    str(normalization_error)
                )