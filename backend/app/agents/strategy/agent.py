from app.schemas.strategy import (
    InterviewStrategy
)

from app.services.llm.factory import (
    get_llm_provider
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite FAANG interviewer.

Your task is to dynamically adjust
interview strategy based on:

- candidate performance
- contradictions
- confidence
- technical depth
- bluff probability

You MUST return JSON matching EXACTLY:

{
  "pressure_level": float,
  "skepticism_level": float,
  "follow_up_intensity": float,
  "next_question_difficulty": string,
  "should_probe_deeper": boolean,
  "should_switch_topic": boolean,
  "focus_topics": [string],
  "reasoning": string
}

Rules:
- scores must be between 0 and 10
- Return ONLY valid JSON
"""


async def generate_strategy(

    technical_evaluation: str,

    contradiction_analysis: str,

):

    user_prompt = f"""
TECHNICAL EVALUATION:
{technical_evaluation}

CONTRADICTION ANALYSIS:
{contradiction_analysis}

Determine optimal interview strategy.
"""

    result = await (
        provider.generate_structured_output(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=InterviewStrategy,
        )
    )

    return result