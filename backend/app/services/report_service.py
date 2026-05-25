from __future__ import annotations

from typing import Any


def build_feedback_report(session: dict[str, Any]) -> dict[str, Any]:
    scores = _average_scores(session.get("scores", {}))
    integrity = _integrity_section(session)
    round_type = session.get("round_type", "dsa")
    round_section = _round_section(session, round_type)
    weak_areas = _dedupe([*session.get("weak_areas", []), *round_section.get("weak_areas", [])])
    strengths = round_section.get("strengths", [])
    overall = _overall_score(scores, integrity["score"], round_section.get("round_score", 0))
    return {
        "session_id": session.get("session_id", ""),
        "round_type": round_type,
        "target_company": session.get("target_company", ""),
        "job_role": session.get("job_role", ""),
        "overall_score": overall,
        "hiring_signal": _hiring_signal(overall),
        "summary": _summary(session, round_section, overall),
        "scores": scores,
        "strengths": strengths or ["Completed the interview flow with enough evidence for feedback."],
        "weak_areas": weak_areas or ["Add more precise examples, measurable outcomes, and explicit tradeoff reasoning."],
        "round_breakdown": round_section,
        "behavioral_signals": session.get("behavioral_signals", {}),
        "behavior_log": session.get("behavior_log", []),
        "hint_count": session.get("hint_count", 0),
        "integrity": integrity,
        "code_runs": session.get("code_runs", []),
        "project_behavioral": session.get("project_behavioral", {}),
        "cs_fundamentals": session.get("cs_fundamentals", {}),
        "study_plan": _practice_plan(round_type, weak_areas, round_section),
        "conversation": session.get("messages", []),
    }


def _average_scores(raw_scores: dict[str, list[int]]) -> dict[str, float]:
    scores = {}
    for key, values in raw_scores.items():
        scores[key] = round(sum(values) / len(values), 1) if values else 0
    return scores


def _integrity_section(session: dict[str, Any]) -> dict[str, Any]:
    violations = session.get("violations", [])
    signals = session.get("behavioral_signals", {})
    penalty = min(35, len(violations) * 5 + min(10, signals.get("large_pastes", 0) * 2))
    return {
        "score": max(0, 100 - penalty),
        "violations": violations,
        "focus_loss": signals.get("focus_loss", 0),
        "paste_events": signals.get("paste_events", 0),
        "large_pastes": signals.get("large_pastes", 0),
        "idle_gaps": signals.get("idle_gaps", 0),
        "voice_turns": signals.get("voice_turns", 0),
    }


def _round_section(session: dict[str, Any], round_type: str) -> dict[str, Any]:
    if round_type == "project_behavioral":
        return _project_behavioral_section(session)
    if round_type == "cs_fundamentals":
        return _cs_section(session)
    return _dsa_section(session)


def _dsa_section(session: dict[str, Any]) -> dict[str, Any]:
    problem = session.get("problem", {})
    code_runs = session.get("code_runs", [])
    latest = code_runs[-1] if code_runs else {}
    passed = int(latest.get("passed_testcases", 0) or 0)
    total = int(latest.get("total_testcases", 0) or 0)
    run_score = float(latest.get("overall_score", 0) or 0)
    hints = int(session.get("hint_count", 0) or 0)
    code_analysis = session.get("latest_code_analysis", {})
    strengths = []
    weak_areas = []
    if total and passed == total:
        strengths.append(f"Code passed all {total} runnable test cases.")
    elif total:
        weak_areas.append(f"Code passed {passed}/{total} runnable test cases.")
    if hints:
        weak_areas.append(f"Used {hints} hint{'s' if hints != 1 else ''}; practice moving from approach to implementation independently.")
    if code_analysis.get("optimization_prompts"):
        weak_areas.extend(code_analysis["optimization_prompts"][:2])
    if not total:
        weak_areas.append("No code submission was recorded, so correctness evidence is limited.")
    return {
        "type": "dsa",
        "title": "DSA Round",
        "round_score": round(run_score if total else 55, 1),
        "problem": {
            "title": problem.get("title", ""),
            "difficulty": problem.get("difficulty", ""),
            "topics": problem.get("topics", []),
            "companies": problem.get("companies", []),
        },
        "submission": {
            "language": latest.get("language", ""),
            "passed_testcases": passed,
            "total_testcases": total,
            "overall_score": run_score,
        },
        "strengths": strengths,
        "weak_areas": weak_areas,
        "evidence": _message_evidence(session, 4),
    }


def _project_behavioral_section(session: dict[str, Any]) -> dict[str, Any]:
    memory = session.get("project_behavioral", {})
    turns = memory.get("turns", [])
    latest_scores = memory.get("latest_scores", {})
    latest_flags = memory.get("latest_flags", [])
    avg_score = _avg_dict(latest_scores) * 10 if latest_scores else _avg_turn_scores(turns)
    strengths = []
    weak_areas = list(latest_flags)
    jd_skills = memory.get("jd_signals", {}).get("skills", [])
    project = memory.get("resume_focus", {}).get("selected_project", "")
    if project:
        strengths.append(f"Discussed resume project focus: {project}.")
    if jd_skills:
        strengths.append(f"Connected the round to JD signals: {', '.join(jd_skills[:5])}.")
    if memory.get("company_style"):
        strengths.append(f"Interview adapted to company style: {memory.get('company_style')}.")
    if not turns:
        weak_areas.append("No Project + Behavioural answer turns were recorded.")
    return {
        "type": "project_behavioral",
        "title": "Project + Behavioural Round",
        "round_score": round(avg_score or 55, 1),
        "company_style": memory.get("company_style", ""),
        "company_profile": memory.get("company_profile", ""),
        "resume_focus": memory.get("resume_focus", {}),
        "jd_signals": memory.get("jd_signals", {}),
        "turn_count": len(turns),
        "latest_scores": latest_scores,
        "latest_flags": latest_flags,
        "strengths": strengths,
        "weak_areas": weak_areas,
        "evidence": turns[-5:],
    }


def _cs_section(session: dict[str, Any]) -> dict[str, Any]:
    memory = session.get("cs_fundamentals", {})
    questions = memory.get("questions_asked", [])
    latest_scores = memory.get("latest_scores", {})
    latest_flags = memory.get("latest_flags", [])
    scratchpad_history = memory.get("scratchpad_history", [])
    score = _avg_dict(latest_scores) * 10 if latest_scores else _avg_question_scores(questions)
    strengths = []
    weak_areas = list(latest_flags)
    if memory.get("strong_topics"):
        strengths.append(f"Strong topics: {', '.join(memory.get('strong_topics', [])[:4])}.")
    if scratchpad_history:
        strengths.append(f"Used scratchpad evidence in {len(scratchpad_history)} turn{'s' if len(scratchpad_history) != 1 else ''}.")
    if memory.get("weak_topics"):
        weak_areas.append(f"Weak topics to revise: {', '.join(memory.get('weak_topics', [])[:4])}.")
    if not questions:
        weak_areas.append("No CS Fundamentals answer turns were recorded.")
    return {
        "type": "cs_fundamentals",
        "title": "CS Fundamentals Round",
        "round_score": round(score or 55, 1),
        "current_topic": memory.get("current_topic", ""),
        "topic_plan": memory.get("topic_plan", []),
        "topics_covered": memory.get("topics_covered", []),
        "strong_topics": memory.get("strong_topics", []),
        "weak_topics": memory.get("weak_topics", []),
        "latest_scores": latest_scores,
        "latest_flags": latest_flags,
        "scratchpad_observations": scratchpad_history[-5:],
        "strengths": strengths,
        "weak_areas": weak_areas,
        "evidence": questions[-6:],
    }


def _overall_score(scores: dict[str, float], integrity_score: int, round_score: float) -> float:
    communication = (sum(scores.values()) / max(1, len(scores))) * 20 if scores else 55
    blended = (communication * 0.35) + (round_score * 0.5) + (integrity_score * 0.15)
    return round(max(0, min(100, blended)), 1)


def _hiring_signal(overall: float) -> str:
    if overall >= 82:
        return "Strong hire"
    if overall >= 68:
        return "Leaning hire"
    if overall >= 52:
        return "Needs targeted preparation"
    return "Needs significant preparation"


def _summary(session: dict[str, Any], section: dict[str, Any], overall: float) -> str:
    company = session.get("target_company") or "the target company"
    role = session.get("job_role") or "the role"
    title = section.get("title", "Interview")
    evidence_count = len(section.get("evidence", []))
    return f"{title} report for {role} at {company}. The score is {overall}/100 based on {evidence_count} recorded evidence item{'s' if evidence_count != 1 else ''}, round-specific performance, and integrity signals."


def _practice_plan(round_type: str, weak_areas: list[str], section: dict[str, Any]) -> list[str]:
    if round_type == "project_behavioral":
        return [
            "Prepare 3 STAR stories with situation, action, result, and reflection.",
            "Add honest metrics to your strongest project explanation.",
            "Practice explaining architecture tradeoffs, rejected alternatives, and ownership clearly.",
            *_from_weak_areas(weak_areas),
        ][:6]
    if round_type == "cs_fundamentals":
        weak_topics = section.get("weak_topics", [])
        topic_action = f"Revise weak CS topics: {', '.join(weak_topics[:4])}." if weak_topics else "Practice DBMS, OOP, OS, and networking comparison questions."
        return [
            topic_action,
            "Explain every concept with one definition, one example, and one tradeoff.",
            "Use the scratchpad for SQL, process/thread sketches, transaction schedules, or protocol flows when helpful.",
            *_from_weak_areas(weak_areas),
        ][:6]
    return [
        "State approach, invariant, time complexity, and space complexity before coding.",
        "Write edge cases before implementation.",
        "Practice debugging failed test cases out loud before changing code.",
        *_from_weak_areas(weak_areas),
    ][:6]


def _from_weak_areas(weak_areas: list[str]) -> list[str]:
    return [f"Fix: {area}" for area in weak_areas[:3]]


def _message_evidence(session: dict[str, Any], limit: int) -> list[dict[str, str]]:
    return [
        {"role": message.get("role", ""), "content": str(message.get("content", ""))[:500]}
        for message in session.get("messages", [])[-limit:]
    ]


def _avg_turn_scores(turns: list[dict[str, Any]]) -> float:
    values = [_avg_dict(turn.get("scores", {})) * 10 for turn in turns if turn.get("scores")]
    return round(sum(values) / len(values), 1) if values else 0


def _avg_question_scores(questions: list[dict[str, Any]]) -> float:
    values = [_avg_dict(question.get("scores", {})) * 10 for question in questions if question.get("scores")]
    return round(sum(values) / len(values), 1) if values else 0


def _avg_dict(values: dict[str, int | float]) -> float:
    numeric = [float(value) for value in values.values() if isinstance(value, (int, float))]
    return round(sum(numeric) / len(numeric), 2) if numeric else 0


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
