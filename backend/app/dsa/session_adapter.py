from __future__ import annotations

from typing import Any

from app.dsa.nodes.ingestion import (
    build_audio_meta_from_session,
    build_editor_events_from_session,
)
from app.dsa.progress import build_dsa_progress, refresh_dsa_progress
from app.dsa.state import DSAState, InterviewProgress, SessionConfig, SessionMemory
from app.services.personality_service import get_interviewer_personality


def session_to_dsa_state(
    session: dict[str, Any],
    *,
    candidate_code: str,
    candidate_explanation: str,
    problem_statement: str | None = None,
    editor_context: str = "",
    metrics: dict[str, Any] | None = None,
) -> DSAState:
    problem = session.get("problem", {})
    prompt = problem_statement or problem.get("prompt", "") or session.get("active_problem", "")
    dsa_memory = session.get("dsa", {})
    memory_payload = dsa_memory.get("memory") if isinstance(dsa_memory.get("memory"), dict) else dsa_memory

    memory = SessionMemory()
    if memory_payload:
        try:
            memory = SessionMemory.model_validate(memory_payload)
        except Exception:
            memory = SessionMemory()

    round_config = session.get("round_config", {})
    progress_payload = session.get("dsa_progress") or {}
    if progress_payload:
        try:
            progress = InterviewProgress.model_validate(progress_payload)
        except Exception:
            progress = InterviewProgress(**build_dsa_progress(
                round_config=round_config,
                timer_minutes=int(session.get("timer_minutes", 35) or 35),
                current_question_index=int(progress_payload.get("current_question_index", 1) or 1),
                started_at_epoch=float(progress_payload.get("started_at_epoch") or 0) or None,
                completed_questions=progress_payload.get("completed_questions"),
            ))
    else:
        progress = InterviewProgress(**build_dsa_progress(
            round_config=round_config,
            timer_minutes=int(session.get("timer_minutes", 35) or 35),
        ))

    topics = problem.get("topics", []) or []
    total_questions = int(round_config.get("question_count", progress.total_questions) or progress.total_questions)
    allocated_minutes = int(progress.allocated_minutes or round_config.get("minutes", 45) or 45)
    difficulty = str(problem.get("difficulty", session.get("difficulty", "medium")) or "medium").lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    config = SessionConfig(
        session_id=session.get("session_id", ""),
        target_company=session.get("target_company", ""),
        problem_id=str(problem.get("id", problem.get("title", ""))),
        problem_statement=prompt,
        expected_solution=problem.get("expected_solution", "") or "",
        expected_time_complexity=problem.get("time_complexity", "") or "",
        allowed_patterns=[str(topic).lower().replace(" ", "_") for topic in topics[:6]],
        difficulty=difficulty,
        max_hints=max(3, int(session.get("round_config", {}).get("max_hints", 3) or 3)),
        max_turns=max(12, total_questions * 12),
        total_questions=total_questions,
        allocated_minutes=allocated_minutes,
        per_question_minutes=round(allocated_minutes / max(total_questions, 1), 1),
    )

    code = candidate_code or ""
    code_language = "python"
    if session.get("code_snapshots"):
        if not code:
            code = session["code_snapshots"][-1].get("code", "")
        code_language = session["code_snapshots"][-1].get("language", "python")

    exchange = int(session.get("exchange_count", session.get("question_count", 0)) or 0)

    # Derive interviewer personality from company dataset
    company = session.get("target_company", "")
    pressure_level = float(dsa_memory.get("pressure_level", 0.3) or 0.3)
    personality = get_interviewer_personality(company, "dsa", pressure_level)

    # Restore phase state from the dsa dict (fallback when graph_state fails to load)
    interview_phase = dsa_memory.get("interview_phase", "reading")
    if interview_phase not in {"reading", "clarification", "brute_force", "optimization", "coding", "testing", "closing"}:
        interview_phase = "reading"
    phase_turns = int(dsa_memory.get("phase_turns", 0) or 0)
    brute_force_given = bool(dsa_memory.get("brute_force_given", False))
    optimized_approach_confirmed = bool(dsa_memory.get("optimized_approach_confirmed", False))

    return DSAState(
        config=config,
        progress=progress,
        exchange_number=exchange,
        turn_number=exchange,
        trigger=session.get("dsa_trigger", "message"),
        latest_code_run=dict(session.get("latest_code_run") or {}),
        candidate_code=code,
        code_language=code_language,
        candidate_explanation=candidate_explanation or "",
        editor_context=editor_context or "",
        audio_meta=build_audio_meta_from_session(
            candidate_explanation or "",
            metrics=metrics,
            behavioral=session.get("behavioral_signals"),
        ),
        editor_events=build_editor_events_from_session(session, code),
        memory=memory,
        personality=personality,
        pressure_level=pressure_level,
        difficulty_level=difficulty,
        interview_phase=interview_phase,
        phase_turns=phase_turns,
        brute_force_given=brute_force_given,
        optimized_approach_confirmed=optimized_approach_confirmed,
    )


def dsa_state_to_session_result(state: DSAState) -> dict[str, Any]:
    progress = state.progress.model_dump()
    return {
        "evaluation": state.evaluation,
        "comparison": state.comparison,
        "followup": state.followup_question,
        "interviewer_reply": state.interviewer_reply,
        "hint": state.hint,
        "hint_tightness": state.hint_tightness,
        "turn_score": state.turn_score.model_dump(),
        "behaviour_profile": state.behaviour_profile.model_dump(),
        "session_scores": state.session_scores.model_dump(),
        "next_action": state.next_action,
        "report": state.report.model_dump() if state.report.session_id else {},
        "dsa_progress": progress,
        "candidate_intent": state.candidate_intent.model_dump(),
        "exchange_count": state.exchange_number,
        "dsa": {
            "memory": state.memory.model_dump(),
            "latest_evaluation": state.evaluation,
            "latest_comparison": state.comparison,
            "latest_followup": state.followup_question,
            "latest_interviewer_reply": state.interviewer_reply,
            "turn_scores": state.session_scores.per_turn,
            "confidence_trend": state.memory.confidence_trend,
            "known_weak_areas": state.memory.known_weak_areas,
            "known_strong_areas": state.memory.known_strong_areas,
            "approach_patterns": state.memory.approach_patterns,
            "hints_given": state.memory.hints_given,
            "timeline": state.timeline.model_dump(),
            "progress": progress,
            "report": state.report.model_dump() if state.report.recommendation != "insufficient_data" else {},
            "pressure_level": state.pressure_level,
            "difficulty_level": state.difficulty_level,
            "contradiction_history": [c.model_dump() for c in state.memory.contradiction_history],
            "rolling_summary": state.memory.rolling_summary,
            "personality": state.personality,
            # Phase fields — saved here as a fallback in case graph_state fails to reload
            "interview_phase": state.interview_phase,
            "phase_turns": state.phase_turns,
            "brute_force_given": state.brute_force_given,
            "optimized_approach_confirmed": state.optimized_approach_confirmed,
        },
        "weak_areas": state.memory.known_weak_areas,
    }


def sync_progress_to_session(session: dict[str, Any], state: DSAState) -> dict[str, Any]:
    session["dsa_progress"] = state.progress.model_dump()
    refresh_dsa_progress(session)
    return session["dsa_progress"]
