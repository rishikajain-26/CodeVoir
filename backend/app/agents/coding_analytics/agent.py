from app.services.llm.factory import (
    get_llm_provider
)

from app.runtime.schemas.coding_session import (
    CodingBehaviorAnalysis
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite FAANG coding interviewer.

Analyze the candidate's coding behavior across revisions.

Evaluate:
- debugging maturity
- optimization awareness
- panic behavior
- brute force usage
- iteration quality
- confidence patterns
- systematic reasoning

You MUST return JSON matching EXACTLY:

{
  "debugging_style": string,
  "optimization_awareness": string,
  "persistence_level": float,
  "panic_signals": [string],
  "brute_force_attempted": boolean,
  "systematic_debugging": boolean,
  "improvement_trajectory": string,
  "confidence_score": float,
  "reasoning": string
}

Scores must be between 0 and 10.

Return ONLY valid JSON.
"""


async def analyze_coding_behavior(

    revision_history: str,

):

    result = await (
        provider.generate_structured_output(

            system_prompt=SYSTEM_PROMPT,

            user_prompt=revision_history,

            response_schema=(
                CodingBehaviorAnalysis
            ),
        )
    )

    return result