import json
import re


def clean_json_response(
    raw_text: str,
):

    cleaned = raw_text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace(
            "```json",
            ""
        )

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    return cleaned


def extract_json_object(
    raw_text: str,
):

    match = re.search(
        r"\{.*\}",
        raw_text,
        re.DOTALL,
    )

    if match:
        return match.group(0)

    return raw_text