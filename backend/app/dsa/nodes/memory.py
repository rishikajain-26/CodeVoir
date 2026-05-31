from __future__ import annotations

import time

from app.dsa.progress import refresh_dsa_progress
from app.dsa.state import DSAState, SessionMemory, TurnRecord

# Weak/strong areas are decided from the SESSION AVERAGE of each skill dimension
# across turns where that dimension was actually exercised — never from a single
# (often early, low) turn. These are the only tunable cutoffs.
WEAK_AREA_THRESHOLD = 0.45      # avg below this → flagged as a weak area
STRONG_AREA_THRESHOLD = 0.68    # avg at/above this → flagged as a strong area
_MIN_SPEECH_WORDS = 5           # speech needed before judging spoken dimensions
_MIN_CODE_CHARS = 10            # code needed before judging code dimensions

# (TurnScore attribute, area label, requires_code?)
_SKILL_DIMENSIONS = (
    ("approach_quality",    "approach_quality",    False),
    ("complexity_accuracy", "complexity_analysis", False),
    ("communication",       "communication",       False),
    ("implementation",      "code_quality",        True),
    ("debugging",           "debugging",           True),
)


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

    base_update = {
        "behaviour_history": history,
        "confidence_trend": trend,
        "total_silence_s": memory.total_silence_s + state.silence_profile.total_silence,
        "total_coding_s": memory.total_coding_s + state.editor_signals.time_coding_s,
    }

    # `turn_memory_writer` runs before this node in memory_update_bundle, so
    # memory.turns already includes the current turn.
    turns = list(memory.turns)
    if not turns:
        return {"memory": memory.model_copy(update=base_update)}

    def _spoke(t: TurnRecord) -> bool:
        return len(t.explanation_excerpt.split()) >= _MIN_SPEECH_WORDS

    def _coded(t: TurnRecord) -> bool:
        return len(t.code_excerpt.strip()) >= _MIN_CODE_CHARS

    # Recompute weak/strong fresh each turn from the running average of each
    # dimension over the turns where it was actually exercised. This is
    # self-correcting: a single weak early turn no longer permanently brands a
    # skill, and a dimension that was never used (e.g. debugging before any code)
    # is left unjudged rather than flagged weak by default.
    weak: list[str] = []
    strong: list[str] = []
    for attr, label, requires_code in _SKILL_DIMENSIONS:
        applicable = [t for t in turns if (_coded(t) if requires_code else _spoke(t))]
        if not applicable:
            continue
        avg = sum(getattr(t.score, attr) for t in applicable) / len(applicable)
        if avg < WEAK_AREA_THRESHOLD:
            weak.append(label)
        elif avg >= STRONG_AREA_THRESHOLD:
            strong.append(label)

    return {
        "memory": memory.model_copy(
            update={
                **base_update,
                "known_weak_areas": weak[:12],
                "known_strong_areas": strong[:12],
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
