from __future__ import annotations

from typing import Any

from app.dsa.progress import advance_dsa_question, refresh_dsa_progress
from app.dsa.state import DSAState


def apply_session_actions(
    session: dict[str, Any],
    state: DSAState,
    *,
    select_next_problem,
) -> dict[str, Any]:
    """
    Apply graph decisions to the live session (advance problem, end round, load next problem).
    `select_next_problem` is injected from main to avoid circular imports.
    """
    intent = state.candidate_intent
    progress = refresh_dsa_progress(session)

    # A code submission should produce test feedback and a follow-up on the same
    # problem. Advancement is reserved for explicit conversational turns.
    if intent.should_advance_question and state.trigger != "code_submit":
        progress = advance_dsa_question(session, reason=intent.reasoning or intent.primary_intent)
        if not progress.get("round_complete") and select_next_problem:
            next_problem = select_next_problem(session)
            if next_problem:
                session["problem"] = next_problem
                session.setdefault("used_problem_ids", []).append(next_problem.get("id"))
                session["code_snapshots"] = []
                session["code_runs"] = []
                session["latest_code_analysis"] = {}
                session["latest_code_run"] = {}
        progress = refresh_dsa_progress(session)

    if intent.should_end_round or state.next_action == "generate_report":
        session["phase"] = "complete"
        progress["round_complete"] = True
        session["dsa_progress"] = progress

    return progress
