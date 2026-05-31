from app.services.llm.factory import (
    get_llm_provider
)

from app.runtime.schemas.telemetry import (
    TelemetryAnalysis
)


provider = get_llm_provider()


SYSTEM_PROMPT = """
You are an elite coding interview behavioral analyst.

Analyze editor telemetry events.

Detect:
- hesitation
- panic behavior
- confidence
- suspicious copy-pasting
- debugging maturity
- behavioral signals

You MUST return JSON matching EXACTLY:

{
  "hesitation_score": float,
  "panic_score": float,
  "confidence_score": float,
  "suspected_copy_paste": boolean,
  "debugging_maturity": string,
  "behavioral_signals": [string],
  "reasoning": string
}

Scores must be between 0 and 10.

Return ONLY valid JSON.
"""


async def analyze_telemetry(

    telemetry_history: str,

):

    result = await (
        provider.generate_structured_output(

            system_prompt=SYSTEM_PROMPT,

            user_prompt=telemetry_history,

            response_schema=(
                TelemetryAnalysis
            ),
        )
    )

    return result