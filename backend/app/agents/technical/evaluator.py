from app.schemas.evaluation import (
    TechnicalEvaluation
)

from app.services.llm.factory import (
    get_llm_provider
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite senior FAANG technical interviewer.

Evaluate the candidate deeply.

Focus on:
- technical depth
- architecture understanding
- reasoning quality
- scalability understanding
- authenticity of claims

Detect bluffing aggressively.

Return ONLY a valid JSON object with EXACTLY these keys:
{
    "technical_depth_score": <float 0.0-10.0>,
    "system_design_score": <float 0.0-10.0>,
    "problem_solving_score": <float 0.0-10.0>,
    "detected_strengths": [<string>, ...],
    "detected_weaknesses": [<string>, ...],
    "follow_up_topics": [<string>, ...],
    "confidence_score": <float 0.0-10.0>,
    "suspected_bluffing": <true|false>,
    "reasoning": <string>
}

No extra keys. No nesting. No explanation. No markdown.
"""


async def evaluate_technical_response(
    question: str,
    answer: str,
):

    user_prompt = f"""
QUESTION:
{question}

ANSWER:
{answer}
"""

    result = await provider.generate_structured_output(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_schema=TechnicalEvaluation,
    )

    return result