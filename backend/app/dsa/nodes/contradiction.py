from __future__ import annotations

import json

from app.dsa.llm_text import generate_text
from app.dsa.state import ContradictionRecord, DSAState
from app.utils.logger import logger

_SYS = """You are a rigorous DSA interview analyst. Your job is to detect logical contradictions between what a candidate said in earlier turns vs what they are saying now.

A CONTRADICTION is when:
- They claimed X was O(n) before but now claim it is O(n²), without acknowledging the change
- They said they would use a hash map but are now using a nested loop with a different rationale and no acknowledgment
- They asserted their approach handles empty input, but their code / latest explanation does not

NOT a contradiction: clarifications, corrections the candidate explicitly acknowledges, or different aspects of the same problem.

Return JSON only:
{
  "detected": <bool>,
  "claim_before": "<exact earlier claim, ≤ 80 chars>",
  "claim_now": "<what they are saying now, ≤ 80 chars>",
  "severity": <float 0.0–1.0>,
  "topic": "<one of: complexity | data_structure | approach | correctness | edge_case>"
}"""


async def contradiction_detector(state: DSAState) -> dict:
    """Detect contradictions between prior claims and current explanation."""
    turns = state.memory.turns
    if len(turns) < 2:
        return {"latest_contradiction": None}
    if len(state.candidate_explanation.split()) < 8:
        return {"latest_contradiction": None}

    recent_excerpts = [
        f"Turn {r.turn}: {r.explanation_excerpt[:300]}"
        for r in turns[-5:]
    ]
    ctx = {
        "previous_turns": recent_excerpts,
        "current_explanation": state.candidate_explanation[:1200],
        "current_code": state.candidate_code[-600:],
    }

    raw = await generate_text(_SYS, str(ctx), temperature=0.1, max_tokens=180)
    if not raw:
        return {"latest_contradiction": None}

    try:
        data = json.loads(raw)
        if not data.get("detected"):
            return {"latest_contradiction": None}
        record = ContradictionRecord(
            turn=state.turn_number,
            claim_before=data.get("claim_before", "")[:200],
            claim_now=data.get("claim_now", "")[:200],
            severity=float(data.get("severity", 0.5)),
            topic=data.get("topic", ""),
        )
        updated_memory = state.memory.model_copy(
            update={
                "contradiction_history": [
                    *state.memory.contradiction_history,
                    record,
                ][-20:]
            }
        )
        logger.info(
            "Contradiction detected at turn %d: %s → %s (severity %.2f)",
            state.turn_number,
            record.claim_before[:60],
            record.claim_now[:60],
            record.severity,
        )
        return {"latest_contradiction": record, "memory": updated_memory}
    except Exception as exc:
        logger.debug("contradiction_detector parse failed: %s", exc)
        return {"latest_contradiction": None}
