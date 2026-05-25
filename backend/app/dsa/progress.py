from __future__ import annotations

import time
from typing import Any


def normalize_dsa_round_config(config: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize company DSA config keys from interview_round_sources.json."""
    defaults = defaults or {}
    default_dsa = defaults.get("dsa", {}) if isinstance(defaults, dict) else {}
    question_count = (
        config.get("question_count")
        or config.get("questions")
        or default_dsa.get("question_count")
        or default_dsa.get("questions")
        or 2
    )
    minutes = config.get("minutes") or default_dsa.get("minutes") or 45
    normalized = dict(config)
    normalized["question_count"] = max(1, int(question_count))
    normalized["minutes"] = max(10, int(minutes))
    return normalized


def build_dsa_progress(
    *,
    round_config: dict[str, Any],
    timer_minutes: int,
    current_question_index: int = 1,
    started_at_epoch: float | None = None,
    completed_questions: list[int] | None = None,
) -> dict[str, Any]:
    company_minutes = int(round_config.get("minutes", 45) or 45)
    total_questions = int(round_config.get("question_count", 2) or 2)
    allocated_minutes = max(10, min(int(timer_minutes or company_minutes), company_minutes))
    per_question_minutes = round(allocated_minutes / max(total_questions, 1), 1)
    started = started_at_epoch or time.time()
    elapsed = max(0, int(time.time() - started))
    remaining = max(0, allocated_minutes * 60 - elapsed)

    return {
        "current_question_index": max(1, min(current_question_index, total_questions)),
        "total_questions": total_questions,
        "company_minutes": company_minutes,
        "allocated_minutes": allocated_minutes,
        "per_question_minutes": per_question_minutes,
        "started_at_epoch": started,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "time_expired": remaining <= 0,
        "completed_questions": list(completed_questions or []),
        "label": f"Question {max(1, min(current_question_index, total_questions))} of {total_questions}",
    }


def refresh_dsa_progress(session: dict[str, Any]) -> dict[str, Any]:
    progress = dict(session.get("dsa_progress") or {})
    if not progress:
        progress = build_dsa_progress(
            round_config=session.get("round_config", {}),
            timer_minutes=int(session.get("timer_minutes", 35) or 35),
        )
    started = float(progress.get("started_at_epoch") or time.time())
    allocated = int(progress.get("allocated_minutes", 45) or 45)
    elapsed = max(0, int(time.time() - started))
    remaining = max(0, allocated * 60 - elapsed)
    progress["elapsed_seconds"] = elapsed
    progress["remaining_seconds"] = remaining
    progress["time_expired"] = remaining <= 0
    progress["label"] = (
        f"Question {progress.get('current_question_index', 1)} of {progress.get('total_questions', 1)}"
    )
    session["dsa_progress"] = progress
    return progress


def advance_dsa_question(session: dict[str, Any], *, reason: str = "") -> dict[str, Any]:
    progress = refresh_dsa_progress(session)
    current = int(progress.get("current_question_index", 1) or 1)
    total = int(progress.get("total_questions", 1) or 1)
    completed = list(progress.get("completed_questions", []))
    if current not in completed:
        completed.append(current)

    if current >= total:
        progress["completed_questions"] = completed
        progress["round_complete"] = True
        session["dsa_progress"] = progress
        session["phase"] = "complete"
        return progress

    progress["current_question_index"] = current + 1
    progress["completed_questions"] = completed
    progress["last_advance_reason"] = reason
    progress["label"] = f"Question {current + 1} of {total}"
    session["dsa_progress"] = progress
    return progress


def should_generate_dsa_report(session: dict[str, Any], turn_number: int, max_turns: int) -> bool:
    progress = refresh_dsa_progress(session)
    if progress.get("time_expired"):
        return True
    if progress.get("round_complete"):
        return True
    if int(progress.get("current_question_index", 1)) > int(progress.get("total_questions", 1)):
        return True
    return turn_number >= max_turns
