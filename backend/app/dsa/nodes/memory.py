from __future__ import annotations

import time

from app.dsa.progress import refresh_dsa_progress
from app.dsa.state import DSAState, SessionMemory, TurnRecord


def turn_memory_writer(state: DSAState) -> dict:
    record = TurnRecord(
        turn=state.progress.current_question_index,
        problem_excerpt=state.config.problem_statement[:600],
        code_excerpt=state.candidate_code[-1500:],
        explanation_excerpt=state.candidate_explanation[:500],
        score=state.turn_score,
        behaviour=state.behaviour_profile,
        followup_asked=state.followup_question or state.interviewer_reply,
        hint_given=state.hint,
        timeline_snapshot=state.timeline.events[-5:],
    )
    memory = state.memory
    turns = [*memory.turns, record][-40:]
    return {"memory": memory.model_copy(update={"turns": turns})}


def behaviour_memory_writer(state: DSAState) -> dict:
    memory = state.memory
    history = [*memory.behaviour_history, state.behaviour_profile][-40:]
    trend = [*memory.confidence_trend, state.behaviour_profile.overall_confidence][-40:]
    weak = list(memory.known_weak_areas)
    strong = list(memory.known_strong_areas)
    score = state.turn_score

    def add_unique(items: list[str], key: str) -> None:
        if key not in items:
            items.append(key)

    if score.approach_quality < 0.4:
        add_unique(weak, "approach_quality")
    if score.complexity_accuracy < 0.4:
        add_unique(weak, "complexity_analysis")
    if score.debugging < 0.4:
        add_unique(weak, "debugging")
    if score.communication < 0.4:
        add_unique(weak, "communication")
    if score.implementation < 0.4:
        add_unique(weak, "code_quality")
    if score.approach_quality > 0.75:
        add_unique(strong, "approach_quality")
    if score.communication > 0.75:
        add_unique(strong, "communication")
    if score.debugging > 0.75:
        add_unique(strong, "debugging")

    return {
        "memory": memory.model_copy(
            update={
                "behaviour_history": history,
                "confidence_trend": trend,
                "known_weak_areas": weak[:12],
                "known_strong_areas": strong[:12],
                "total_silence_s": memory.total_silence_s + state.silence_profile.total_silence,
                "total_coding_s": memory.total_coding_s + state.editor_signals.time_coding_s,
            }
        )
    }


def pattern_store(state: DSAState) -> dict:
    memory = state.memory
    patterns = dict(memory.approach_patterns)
    coding_patterns = state.scratch.get("_coding_patterns", {})
    for flag in state.behaviour_profile.nervousness_flags:
        patterns[flag] = patterns.get(flag, 0) + 1
    for key, value in coding_patterns.items():
        patterns[key] = patterns.get(key, 0) + int(value)
    for pattern in state.approach.pattern_recognised:
        patterns[f"dsa_pattern_{pattern}"] = patterns.get(f"dsa_pattern_{pattern}", 0) + 1
    return {"memory": memory.model_copy(update={"approach_patterns": patterns})}


def session_state_updater(state: DSAState) -> dict:
    memory = state.memory
    started = state.progress.started_at_epoch or time.time()
    elapsed = max(0, int(time.time() - started))
    remaining = max(0, int(state.progress.allocated_minutes * 60 - elapsed))
    progress = state.progress.model_copy(
        update={
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
            "time_expired": remaining <= 0,
            "label": (
                f"Question {state.progress.current_question_index} of {state.progress.total_questions}"
            ),
        }
    )
    return {
        "memory": memory,
        "progress": progress,
        "turn_number": state.turn_number + 1,
    }


def memory_update_bundle(state: DSAState) -> dict:
    merged: dict = {}
    current = state
    for node in (turn_memory_writer, behaviour_memory_writer, pattern_store, session_state_updater):
        update = node(current)
        merged.update(update)
        current = current.model_copy(update=update)
    return merged
