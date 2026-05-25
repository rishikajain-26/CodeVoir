from __future__ import annotations

import asyncio
from typing import Any

from app.dsa.graph import DSA_GRAPH, run_dsa_turn
from app.dsa.nodes.ingestion import build_editor_events_from_session
from app.dsa.session_actions import apply_session_actions
from app.dsa.session_adapter import dsa_state_to_session_result, session_to_dsa_state, sync_progress_to_session
from app.dsa.state import DSAState
from app.utils.logger import logger


async def run_dsa_turn_async(
    session: dict[str, Any],
    candidate_code: str,
    candidate_explanation: str,
    problem_statement: str | None = None,
    editor_context: str | None = None,
    metrics: dict[str, Any] | None = None,
    *,
    trigger: str = "message",
    select_next_problem=None,
) -> dict[str, Any]:
    """Run one DSA turn through the full graph; actions follow candidate intent."""

    session["dsa_trigger"] = trigger
    prior = session.get("dsa", {})
    prior_state: DSAState | None = None
    if isinstance(prior.get("graph_state"), dict):
        try:
            prior_state = DSAState.model_validate(prior["graph_state"])
        except Exception as exc:
            logger.error(
                "DSA graph_state failed to deserialize (session=%s), falling back to cold state: %s",
                session.get("session_id", "unknown"),
                exc,
            )
            prior_state = None

    state = prior_state or session_to_dsa_state(
        session,
        candidate_code=candidate_code,
        candidate_explanation=candidate_explanation,
        problem_statement=problem_statement,
        editor_context=editor_context or "",
        metrics=metrics,
    )
    exchange = int(session.get("exchange_count", session.get("question_count", 0)) or 0)
    current_code = candidate_code or state.candidate_code
    fresh_events = build_editor_events_from_session(session, current_code)
    state = state.model_copy(
        update={
            "candidate_code": current_code,
            "candidate_explanation": candidate_explanation or state.candidate_explanation,
            "editor_context": editor_context or state.editor_context,
            "exchange_number": exchange,
            "turn_number": exchange,
            "trigger": trigger,
            "latest_code_run": dict(session.get("latest_code_run") or {}),
            "editor_events": fresh_events,
            "hint": None,
            "followup_question": "",
            "interviewer_reply": "",
            "next_action": "next_turn",
        }
    )

    try:
        result = await DSA_GRAPH.ainvoke(state)
        if isinstance(result, dict):
            final_state = DSAState.model_validate(result)
        else:
            final_state = result
    except Exception as exc:
        logger.error("DSA graph failed: %s", exc, exc_info=True)
        return _fallback_turn_result(session, candidate_explanation, str(exc))

    if select_next_problem:
        progress = apply_session_actions(
            session,
            final_state,
            select_next_problem=select_next_problem,
        )
    else:
        from app.dsa.progress import refresh_dsa_progress

        progress = refresh_dsa_progress(session)

    payload = dsa_state_to_session_result(final_state)
    payload["dsa_progress"] = progress

    question_advanced = (
        final_state.candidate_intent.should_advance_question
        and not progress.get("round_complete")
    )

    if question_advanced:
        # Do NOT cache graph_state — it holds the old problem's config.
        # The next turn must rebuild from session, which now has the new problem.
        # Also reset phase fields so session_to_dsa_state starts fresh.
        payload["dsa"].pop("graph_state", None)
        payload["dsa"].update({
            "interview_phase": "reading",
            "phase_turns": 0,
            "brute_force_given": False,
            "optimized_approach_confirmed": False,
        })
    else:
        payload["dsa"]["graph_state"] = final_state.model_dump()

    session["dsa"] = payload["dsa"]
    session["dsa_progress"] = progress
    sync_progress_to_session(session, final_state)

    if (
        final_state.progress.time_expired
        or final_state.next_action == "generate_report"
        or final_state.candidate_intent.should_end_round
    ):
        session["phase"] = "complete"

    if final_state.hint and final_state.memory.hints_given > int(session.get("hint_count", 0) or 0):
        session["hint_count"] = final_state.memory.hints_given

    if final_state.candidate_intent.should_advance_question and trigger != "code_submit" and session.get("problem"):
        payload["problem"] = session["problem"]

    return payload


def run_dsa_turn(
    session: dict[str, Any],
    candidate_code: str,
    candidate_explanation: str,
    problem_statement: str | None = None,
    editor_context: str | None = None,
    metrics: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            run_dsa_turn_async(
                session=session,
                candidate_code=candidate_code,
                candidate_explanation=candidate_explanation,
                problem_statement=problem_statement,
                editor_context=editor_context,
                metrics=metrics,
                **kwargs,
            )
        )
    raise RuntimeError(
        "Cannot call run_dsa_turn synchronously from an active event loop. "
        "Use run_dsa_turn_async instead."
    )


def _fallback_turn_result(session: dict[str, Any], explanation: str, error: str) -> dict[str, Any]:
    return {
        "evaluation": {
            "correctness_score": 0.0,
            "optimization_score": 0.0,
            "debugging_score": 0.0,
            "communication_score": 0.0,
            "edge_case_handling_score": 0.0,
            "detected_strengths": [],
            "detected_weaknesses": [],
            "follow_up_questions": [],
            "confidence_score": 0.0,
            "reasoning": f"Graph fallback: {error}",
        },
        "comparison": {
            "alignment_score": 0.0,
            "expected_alignment_score": 0.0,
            "missing_concepts": [],
            "extra_risk_flags": [],
            "recommended_improvements": [],
            "confidence_score": 0.0,
            "reasoning": error,
        },
        "followup": "Walk me through your approach and its time complexity.",
        "interviewer_reply": "Walk me through your approach and its time complexity.",
        "dsa_errors": [error],
        "dsa": session.get("dsa", {}),
    }
