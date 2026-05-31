"""
Analytics service — session-level and cross-session skill tracking.

Reads from the session store; never writes to it. All methods are async-safe
and read the in-memory SESSIONS dict through the public session_store API to
avoid coupling to the SQLite layer directly.
"""
from __future__ import annotations

from statistics import mean, stdev
from typing import Any

from app.utils.logger import logger


def _get_all_sessions() -> dict[str, dict]:
    """Return the in-memory sessions dict without importing at module level."""
    from app.services.session_store import SESSIONS
    return SESSIONS


# ─── Single-session helpers ───────────────────────────────────────────────────

def get_session_skill_scores(session_id: str) -> dict[str, float] | None:
    """Return the 4-skill weighted scores for a completed session, or None."""
    sessions = _get_all_sessions()
    session = sessions.get(session_id)
    if not session:
        return None
    report = session.get("report") or {}
    sf = report.get("skill_feedback") or {}
    if not sf:
        # Fall back to raw session_scores if skill_feedback not present
        scores = session.get("session_scores") or session.get("dsa", {}).get("session_scores") or {}
        if scores:
            return {
                "communication": float(scores.get("communication", 0)),
                "technical": float(scores.get("dsa_knowledge", 0)),
                "problem_solving": float(scores.get("problem_solving", 0)),
                "code_quality": float(scores.get("coding", 0)),
                "overall": float(scores.get("overall", 0)),
            }
        return None
    return {
        "communication": float(sf.get("communication", {}).get("score", 0)),
        "technical": float(sf.get("technical", {}).get("score", 0)),
        "problem_solving": float(sf.get("problem_solving", {}).get("score", 0)),
        "code_quality": float(sf.get("code_quality", {}).get("score", 0)),
        "overall": _weighted_overall(sf),
    }


def _weighted_overall(sf: dict) -> float:
    """Comm 25%, Tech 30%, PS 25%, CQ 20%."""
    return (
        float(sf.get("communication", {}).get("score", 0)) * 0.25
        + float(sf.get("technical", {}).get("score", 0)) * 0.30
        + float(sf.get("problem_solving", {}).get("score", 0)) * 0.25
        + float(sf.get("code_quality", {}).get("score", 0)) * 0.20
    )


# ─── Candidate-level analytics ────────────────────────────────────────────────

def get_candidate_sessions(candidate_id: str) -> list[dict]:
    """Return all sessions for a given candidate, newest first."""
    sessions = _get_all_sessions()
    result = [
        s for s in sessions.values()
        if s.get("candidate_id") == candidate_id and s.get("phase") == "complete"
    ]
    result.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return result


def get_skill_progression(candidate_id: str) -> dict[str, list[float]]:
    """Return per-skill score lists ordered oldest → newest for trend analysis."""
    candidate_sessions = get_candidate_sessions(candidate_id)
    candidate_sessions.reverse()  # oldest first for progression charts

    progression: dict[str, list[float]] = {
        "communication": [],
        "technical": [],
        "problem_solving": [],
        "code_quality": [],
        "overall": [],
    }
    for s in candidate_sessions:
        scores = get_session_skill_scores(s.get("session_id", ""))
        if scores:
            for skill in progression:
                progression[skill].append(scores.get(skill, 0.0))
    return progression


def get_skill_averages(candidate_id: str) -> dict[str, float]:
    """Return average per-skill scores across all completed sessions."""
    progression = get_skill_progression(candidate_id)
    return {
        skill: round(mean(values), 3) if values else 0.0
        for skill, values in progression.items()
    }


def get_skill_trends(candidate_id: str) -> dict[str, str]:
    """Return 'improving' | 'declining' | 'stable' | 'insufficient_data' per skill."""
    progression = get_skill_progression(candidate_id)
    trends: dict[str, str] = {}
    for skill, values in progression.items():
        if len(values) < 3:
            trends[skill] = "insufficient_data"
            continue
        recent = mean(values[-3:])
        earlier = mean(values[:-3]) if len(values) > 3 else values[0]
        delta = recent - earlier
        if delta > 0.05:
            trends[skill] = "improving"
        elif delta < -0.05:
            trends[skill] = "declining"
        else:
            trends[skill] = "stable"
    return trends


def get_weak_skills(candidate_id: str, threshold: float = 0.5) -> list[str]:
    """Return skills with average score below threshold (worst first)."""
    averages = get_skill_averages(candidate_id)
    weak = {skill: score for skill, score in averages.items() if score < threshold and skill != "overall"}
    return sorted(weak, key=lambda k: weak[k])


def get_candidate_insights(candidate_id: str) -> dict[str, Any]:
    """Aggregate analytics for a candidate dashboard."""
    sessions = get_candidate_sessions(candidate_id)
    if not sessions:
        return {"candidate_id": candidate_id, "sessions_count": 0, "message": "No completed sessions found."}

    averages = get_skill_averages(candidate_id)
    trends = get_skill_trends(candidate_id)
    weak = get_weak_skills(candidate_id)
    progression = get_skill_progression(candidate_id)

    consistency: dict[str, float] = {}
    for skill, values in progression.items():
        if len(values) >= 2:
            try:
                consistency[skill] = round(1.0 - stdev(values), 3)
            except Exception:
                consistency[skill] = 1.0

    return {
        "candidate_id": candidate_id,
        "sessions_count": len(sessions),
        "skill_averages": averages,
        "skill_trends": trends,
        "weak_skills": weak,
        "consistency": consistency,
        "recommendation_distribution": _recommendation_distribution(sessions),
        "avg_hints_per_session": _avg_hints(sessions),
    }


def _recommendation_distribution(sessions: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for s in sessions:
        rec = (s.get("report") or {}).get("recommendation", "insufficient_data")
        dist[rec] = dist.get(rec, 0) + 1
    return dist


def _avg_hints(sessions: list[dict]) -> float:
    hints = [int(s.get("hint_count", 0) or 0) for s in sessions]
    return round(mean(hints), 1) if hints else 0.0


# ─── Global / platform analytics ──────────────────────────────────────────────

def get_global_stats() -> dict[str, Any]:
    """Platform-wide aggregate stats (admin / dashboard use)."""
    sessions = _get_all_sessions()
    completed = [s for s in sessions.values() if s.get("phase") == "complete"]
    if not completed:
        return {"total_sessions": 0, "completed_sessions": 0}

    all_overalls = []
    rec_dist: dict[str, int] = {}
    for s in completed:
        sid = s.get("session_id", "")
        scores = get_session_skill_scores(sid)
        if scores:
            all_overalls.append(scores["overall"])
        rec = (s.get("report") or {}).get("recommendation", "insufficient_data")
        rec_dist[rec] = rec_dist.get(rec, 0) + 1

    return {
        "total_sessions": len(sessions),
        "completed_sessions": len(completed),
        "avg_overall_score": round(mean(all_overalls), 3) if all_overalls else 0.0,
        "recommendation_distribution": rec_dist,
    }
