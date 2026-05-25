from __future__ import annotations

from app.dsa.state import DSAState


def turn_router(state: DSAState) -> str:
    """Route using contextual candidate intent (set by resolve_candidate_intent)."""
    if state.progress.time_expired:
        return "generate_report"
    if state.progress.round_complete:
        return "generate_report"
    if state.candidate_intent.should_end_round:
        return "generate_report"
    if state.next_action == "generate_report":
        return "generate_report"
    if state.turn_number >= state.config.max_turns:
        return "generate_report"

    if (
        state.candidate_intent.should_give_hint
        and state.memory.hints_given < state.config.max_hints
        and not state.hint
    ):
        return "escalate_hint"

    return "next_turn"
