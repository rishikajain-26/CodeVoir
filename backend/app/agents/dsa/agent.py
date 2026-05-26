from app.schemas.evaluation import (
    DSAComparison,
    DSAEvaluation,
    DSAFollowUp,
)

from app.services.llm.factory import (
    get_llm_provider,
)

from app.utils.logger import logger


provider = get_llm_provider()


SYSTEM_PROMPT_EVALUATE = """
You are an expert algorithm and data-structures interviewer.

Evaluate the candidate's solution (code and explanation) against the problem statement and typical expected approaches.

Focus on:
- correctness (does it solve all required cases)
- optimization (time / space complexity)
- edge-case handling and robustness
- debugging and testability
- communication and clarity of explanation

Return ONLY valid JSON compatible with the DSAEvaluation schema. No extra keys, no markdown.
"""


async def evaluate_dsa_solution(
    problem_statement: str,
    candidate_code: str,
    candidate_explanation: str,
    editor_context: str | None = None,
):
    """Evaluate a candidate's DSA solution and return a structured DSAEvaluation."""

    user_prompt = f"""
PROBLEM:
{problem_statement}

CANDIDATE CODE:
{candidate_code}

CANDIDATE EXPLANATION:
{candidate_explanation}

EDITOR CONTEXT:
{editor_context or ''}
"""

    result = await provider.generate_structured_output(
        system_prompt=SYSTEM_PROMPT_EVALUATE,
        user_prompt=user_prompt,
        response_schema=DSAEvaluation,
    )

    return result


SYSTEM_PROMPT_COMPARE = """
You are an expert interviewer. Compare the candidate's described approach with an expected or model approach.

Return a short JSON object with the same shape as DSAEvaluation where the reasoning should focus on differences and suggested repair steps. Return ONLY valid JSON.
"""


async def compare_with_expected(
    problem_statement: str,
    candidate_explanation: str,
    expected_solution: str,
):
    """Compare candidate approach to the expected approach and surface differences.

    Returns a DSAComparison model instance with reasoning highlighting the delta.
    """

    user_prompt = f"""
PROBLEM:
{problem_statement}

CANDIDATE APPROACH:
{candidate_explanation}

EXPECTED APPROACH:
{expected_solution}
"""

    result = await provider.generate_structured_output(
        system_prompt=SYSTEM_PROMPT_COMPARE,
        user_prompt=user_prompt,
        response_schema=DSAComparison,
    )

    return result


SYSTEM_PROMPT_FOLLOWUP = """
You are an expert technical interviewer.

Read the problem, candidate code, and candidate explanation.
Ask exactly one concise follow-up question that will reveal whether the candidate's solution is correct, robust, or optimizable.
Return ONLY valid JSON with one key: follow_up_question.
"""


async def generate_followup_question(
    problem_statement: str,
    candidate_code: str,
    candidate_explanation: str,
    expected_solution: str | None = None,
    editor_context: str | None = None,
    fallback: str = "Can you clarify or improve your approach?",
):
    """Generate one focused follow-up question tailored to the candidate's code and explanation."""

    user_prompt = f"""
PROBLEM:
{problem_statement}

CANDIDATE CODE:
{candidate_code}

CANDIDATE EXPLANATION:
{candidate_explanation}

EXPECTED APPROACH:
{expected_solution or ''}

EDITOR CONTEXT:
{editor_context or ''}
"""

    try:
        response = await provider.generate_structured_output(
            system_prompt=SYSTEM_PROMPT_FOLLOWUP,
            user_prompt=user_prompt,
            response_schema=DSAFollowUp,
        )
        question = getattr(response, "follow_up_question", "")
        return question.strip() or fallback
    except Exception as exc:
        logger.warning(
            "DSA follow-up generation failed: %s",
            str(exc),
        )
        return fallback
