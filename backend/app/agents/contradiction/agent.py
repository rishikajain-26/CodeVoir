from app.schemas.contradiction import (
    ContradictionAnalysis
)

from app.services.llm.factory import (
    get_llm_provider
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite technical interviewer.

Your task is to detect:
- contradictions
- inconsistencies
- shallow explanations
- exaggerated claims
- possible bluffing

You MUST return JSON matching EXACTLY this schema:

{
  "contradiction_detected": boolean,
  "contradiction_reason": string,
  "severity_score": float,
  "suspected_bluffing": boolean,
  "follow_up_question": string,
  "confidence_score": float,
  "related_topics": [string]
}

Rules:
- severity_score must be between 0 and 10
- confidence_score must be between 0 and 10
- related_topics must be an array of strings
- Return ONLY valid JSON
- Do NOT add explanations outside JSON
"""


async def analyze_contradiction(

    previous_claims: str,

    latest_answer: str,

):

    user_prompt = f"""
Analyze whether the latest answer is
consistent with the previous claims.

PREVIOUS CLAIMS:
{previous_claims}

LATEST ANSWER:
{latest_answer}

Determine:
- whether contradiction exists
- whether candidate may be bluffing
- severity of inconsistency
- best follow-up question
"""

    result = await (
        provider.generate_structured_output(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=ContradictionAnalysis,
        )
    )

    return result