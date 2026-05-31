from app.schemas.memory import (
    MemorySummary
)

from app.services.llm.factory import (
    get_llm_provider
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite interview memory system.

Your task is to compress interview history into:

- strengths
- weaknesses
- contradictions
- important claims
- behavioral signals
- technical coverage
- future focus areas

You MUST return JSON matching EXACTLY:

{
  "candidate_strengths": [string],
  "candidate_weaknesses": [string],
  "important_claims": [string],
  "contradictions_detected": [string],
  "behavioral_signals": [string],
  "technical_topics_covered": [string],
  "overall_interview_direction": string,
  "recommended_focus_areas": [string],
  "summary": string
}

Return ONLY valid JSON.
"""


async def generate_memory_summary(

    conversation_history: str,

):

    user_prompt = f"""
INTERVIEW HISTORY:
{conversation_history}

Generate compressed interview memory.
"""

    result = await (
        provider.generate_structured_output(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=MemorySummary,
        )
    )

    return result