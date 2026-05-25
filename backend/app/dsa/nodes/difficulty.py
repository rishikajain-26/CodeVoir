from __future__ import annotations

from typing import Literal

from app.dsa.state import DSAState
from app.utils.logger import logger


def difficulty_adjuster(state: DSAState) -> dict:
    """Adapt pressure and difficulty level based on live performance signals.

    Called after evaluation so turn_score and behaviour_profile are current.
    Only triggers meaningful changes — avoids thrashing on single-turn noise.
    """
    turns = state.memory.turns
    if not turns:
        return {}

    recent_scores = [r.score.weighted_total for r in turns[-3:]]
    avg = sum(recent_scores) / len(recent_scores)
    confidence = state.behaviour_profile.overall_confidence
    hints = state.memory.hints_given
    hint_dependency = state.behaviour_profile.hint_dependency_score
    approach_optimal = state.approach.final_approach_optimal
    current_pressure = state.pressure_level
    current_difficulty = state.difficulty_level

    total_s = state.progress.allocated_minutes * 60
    remaining_s = state.progress.remaining_seconds
    time_fraction = remaining_s / max(total_s, 1)

    # --- Determine new pressure ---
    if time_fraction < 0.20 and not state.candidate_code.strip():
        # Critical: almost no time left and no code — maximise pressure regardless of score
        new_pressure = min(current_pressure + 0.25, 1.0)
    elif time_fraction < 0.35 and not state.brute_force_given:
        # Running low and candidate hasn't even proposed an approach
        new_pressure = min(current_pressure + 0.15, 0.90)
    elif avg > 0.78 and confidence > 0.65 and hints == 0 and approach_optimal:
        # Candidate is clearly comfortable — escalate
        new_pressure = min(current_pressure + 0.15, 0.95)
    elif avg > 0.65 and hints <= 1 and len(turns) >= 3:
        # Steady solid performance — gentle escalation
        new_pressure = min(current_pressure + 0.07, 0.80)
    elif avg < 0.35 or hint_dependency > 0.6:
        # Struggling significantly — back off
        new_pressure = max(current_pressure - 0.12, 0.10)
    elif avg < 0.50 and hints >= 2:
        # Below average with multiple hints — slight relief
        new_pressure = max(current_pressure - 0.05, 0.15)
    else:
        new_pressure = current_pressure

    # --- Determine new difficulty label ---
    if new_pressure >= 0.75 or (avg > 0.80 and len(turns) >= 4):
        new_difficulty: Literal["easy", "medium", "hard"] = "hard"
    elif new_pressure <= 0.25 or avg < 0.35:
        new_difficulty = "easy"
    else:
        new_difficulty = "medium"

    if new_pressure == current_pressure and new_difficulty == current_difficulty:
        return {}

    logger.info(
        "DifficultyAdjuster: avg=%.2f conf=%.2f hints=%d → pressure %.2f→%.2f diff %s→%s",
        avg, confidence, hints,
        current_pressure, new_pressure,
        current_difficulty, new_difficulty,
    )
    return {"pressure_level": new_pressure, "difficulty_level": new_difficulty}
