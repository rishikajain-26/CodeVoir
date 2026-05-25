from __future__ import annotations

import json
from typing import Any

from app.dsa.llm_text import generate_text
from app.utils.json_utils import clean_json_response, extract_json_object


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
    dsa_memory = session.get("dsa", {})
    graph_report = dsa_memory.get("report") or {}
    strengths = list(graph_report.get("strengths_weaknesses", {}).get("strengths", []))
    weak_areas = list(graph_report.get("strengths_weaknesses", {}).get("weaknesses", []))
    if dsa_memory.get("known_weak_areas"):
        weak_areas = _dedupe([*weak_areas, *dsa_memory.get("known_weak_areas", [])])
    if dsa_memory.get("known_strong_areas"):
        strengths = _dedupe([*strengths, *dsa_memory.get("known_strong_areas", [])])
    graph_scores = graph_report.get("scores", {}) if isinstance(graph_report, dict) else {}
    if graph_scores.get("overall"):
        run_score = max(run_score, float(graph_scores["overall"]) * 100)
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
        "hiring_recommendation": graph_report.get("recommendation", ""),
        "recommendation_rationale": graph_report.get("recommendation_rationale", ""),
        "radar_data": graph_report.get("radar_data", {}),
        "behaviour_summary": graph_report.get("behaviour_summary", ""),
        "confidence_trend": dsa_memory.get("confidence_trend", []),
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
        "contradiction_history": [
            {"claim_before": c.get("claim_before", ""), "claim_now": c.get("claim_now", ""), "topic": c.get("topic", "")}
            for c in (dsa_memory.get("contradiction_history") or [])[-5:]
        ],
        "rolling_summary": dsa_memory.get("rolling_summary", ""),
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

    # STAR completeness across all turns
    star_counts = {"situation": 0, "task": 0, "action": 0, "result": 0}
    for turn in turns:
        for component, present in (turn.get("star_components") or {}).items():
            if present and component in star_counts:
                star_counts[component] += 1
    star_completeness_pct = round(
        sum(star_counts.values()) / max(len(turns) * 4, 1) * 100, 0
    ) if turns else 0

    # Exaggeration and accountability signals
    exaggeration_turns = sum(1 for t in turns if t.get("exaggeration_risk"))
    contradiction_history = memory.get("contradiction_history", [])

    if project:
        strengths.append(f"Discussed resume project focus: {project}.")
    if jd_skills:
        strengths.append(f"Connected the round to JD signals: {', '.join(jd_skills[:5])}.")
    if memory.get("company_style"):
        strengths.append(f"Interview adapted to company style: {memory.get('company_style')}.")
    if star_completeness_pct >= 75:
        strengths.append(f"STAR framework used in {star_completeness_pct:.0f}% of turns.")

    if not turns:
        weak_areas.append("No Project + Behavioural answer turns were recorded.")
    missing_star = [c for c, count in star_counts.items() if turns and count / len(turns) < 0.4]
    if missing_star:
        weak_areas.append(f"STAR components often missing: {', '.join(missing_star)}. Practice including all four.")
    if exaggeration_turns > 0:
        weak_areas.append(
            f"Possible claim exaggeration in {exaggeration_turns} turn{'s' if exaggeration_turns != 1 else ''} — use specific, verifiable metrics."
        )
    if memory.get("accountability_gap"):
        weak_areas.append("Accountability gap detected: used 'we' language without clarifying personal ownership.")
    if contradiction_history:
        weak_areas.append(
            f"{len(contradiction_history)} potential metric contradiction{'s' if len(contradiction_history) != 1 else ''} detected across turns."
        )

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
        "star_breakdown": star_counts,
        "star_completeness_pct": star_completeness_pct,
        "exaggeration_turns": exaggeration_turns,
        "contradiction_history": contradiction_history,
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


# --- LLM-grounded report synthesis -------------------------------------------------
# build_feedback_report (above) stays synchronous and template-based — it is the
# always-available fallback and also supplies structured signals to the model.
# build_feedback_report_async layers a transcript-grounded LLM pass on top so the
# narrative reflects what THIS candidate actually said and did.

_ROUND_PARAMETERS = {
    "dsa": ["Problem Solving", "Coding & Implementation", "Complexity Analysis", "Communication", "Debugging"],
    "cs_fundamentals": ["Conceptual Clarity", "Correctness", "Examples & Application", "Depth of Understanding", "Communication"],
    "project_behavioral": ["Ownership & Impact", "STAR Structure", "Technical Depth", "Communication", "Authenticity"],
}

_ROUND_LABEL = {
    "dsa": "Data Structures & Algorithms",
    "cs_fundamentals": "CS Fundamentals",
    "project_behavioral": "Project & Behavioural",
}

_SYS_REPORT = """You are a senior technical interviewer writing the post-interview report the candidate will read.
Be SPECIFIC and EVIDENCE-BASED: ground every point in what THIS candidate actually said, wrote, or did in the transcript and code below. Paraphrase or quote their own words and reference concrete moments (a specific answer, a data structure they chose, a test case that failed, a complexity claim). Never use generic filler that could describe any candidate.

Return ONLY a JSON object (no markdown, no prose outside the JSON) with exactly this shape:
{
  "summary": "2-3 sentences on how THIS candidate performed, citing specifics.",
  "skill_gap": "2-4 sentences naming the candidate's biggest skill lag — the specific skills/concepts holding them back, WHY they are lagging (what they got wrong or never demonstrated), and what closing the gap looks like.",
  "strengths": ["3-5 concrete strengths, each tied to a specific moment, answer, or code behaviour"],
  "weaknesses": ["3-5 concrete gaps, each tied to a specific moment, missing edge case, wrong complexity, or vague answer"],
  "suggestions": ["3-6 actionable next steps that directly address the weaknesses listed above"],
  "parameters": [{"name": "<one of the provided parameter_names>", "score": <integer 0-100>, "note": "one sentence justifying the score with evidence"}],
  "topic_mastery": [{"topic": "<a specific topic/concept actually asked about or required by the problem>", "mastery": <integer 0-100>, "note": "one sentence on how well they demonstrated this topic, citing evidence"}]
}

Rules:
- Use exactly the parameter names provided in parameter_names, one entry each.
- topic_mastery: cover every distinct topic/concept that was actually probed (use topics_asked as a starting point and add any others the transcript reveals). Mastery reflects demonstrated command of THAT topic — high only if they reasoned correctly about it; low if they avoided, misunderstood, or failed it.
- Scores must track the evidence: clear reasoning plus passing tests is high; vague answers and failing tests are low.
- If engagement or evidence is thin, say so honestly and score conservatively — do NOT invent strengths or topic mastery."""


def _build_transcript(session: dict[str, Any], max_turns: int = 30, per_msg: int = 600) -> str:
    lines: list[str] = []
    for message in session.get("messages", [])[-max_turns:]:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        speaker = "Candidate" if message.get("role") == "candidate" else "Interviewer"
        lines.append(f"{speaker}: {content[:per_msg]}")
    return "\n".join(lines)


def _build_code_evidence(session: dict[str, Any]) -> dict[str, Any]:
    runs = session.get("code_runs", [])
    if not runs:
        return {}
    latest = runs[-1]
    failing = [
        {
            "input": str(tc.get("input", ""))[:200],
            "expected": str(tc.get("expected_output", ""))[:200],
            "actual": str(tc.get("actual_output", ""))[:200],
            "stderr": str(tc.get("stderr", ""))[:160],
        }
        for tc in latest.get("testcase_results", [])
        if not tc.get("passed")
    ][:3]
    return {
        "language": latest.get("language", ""),
        "passed": latest.get("passed_testcases", 0),
        "total": latest.get("total_testcases", 0),
        "runs_count": len(runs),
        "failing_cases": failing,
    }


def _normalise_parameters(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            score = max(0, min(100, int(round(float(item.get("score", 0))))))
        except (TypeError, ValueError):
            score = 0
        out.append({"name": name, "score": score, "note": str(item.get("note", "")).strip()})
    return out


def _normalise_topic_mastery(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        try:
            mastery = max(0, min(100, int(round(float(item.get("mastery", 0))))))
        except (TypeError, ValueError):
            mastery = 0
        out.append({"topic": topic, "mastery": mastery, "note": str(item.get("note", "")).strip()})
    return out


def _topics_asked(session: dict[str, Any], section: dict[str, Any], round_type: str) -> list[str]:
    """Best-effort list of topics/concepts actually probed, used to seed the model."""
    topics: list[str] = []
    if round_type == "dsa":
        topics.extend(section.get("problem", {}).get("topics", []) or [])
        for run_problem in session.get("attempted_problems", []) or []:
            topics.extend(run_problem.get("topics", []) or [])
    elif round_type == "cs_fundamentals":
        topics.extend(section.get("topics_covered", []) or [])
        topics.extend(section.get("strong_topics", []) or [])
        topics.extend(section.get("weak_topics", []) or [])
        for question in section.get("evidence", []) or []:
            if isinstance(question, dict) and question.get("topic"):
                topics.append(str(question["topic"]))
    elif round_type == "project_behavioral":
        topics.extend(section.get("jd_signals", {}).get("skills", []) or [])
        if section.get("resume_focus", {}).get("selected_project"):
            topics.append(str(section["resume_focus"]["selected_project"]))
    return _dedupe([str(t).strip() for t in topics if str(t).strip()])[:12]


async def _llm_report_synthesis(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    transcript = _build_transcript(session)
    if not transcript:
        return None
    round_type = base.get("round_type", "dsa")
    section = base.get("round_breakdown", {})
    context = {
        "round": _ROUND_LABEL.get(round_type, round_type),
        "role": session.get("job_role", ""),
        "company": session.get("target_company", ""),
        "parameter_names": _ROUND_PARAMETERS.get(round_type, _ROUND_PARAMETERS["dsa"]),
        "topics_asked": _topics_asked(session, section, round_type),
        "transcript": transcript,
        "code_evidence": _build_code_evidence(session),
        "observed_signals": {
            "heuristic_strengths": section.get("strengths", [])[:6],
            "heuristic_weak_areas": (base.get("weak_areas", []) or [])[:6],
            "hints_used": session.get("hint_count", 0),
            "raw_turn_scores": base.get("scores", {}),
            "integrity_score": base.get("integrity", {}).get("score", 100),
            "round_specifics": {
                key: section.get(key)
                for key in ("problem", "topics_covered", "weak_topics", "strong_topics", "star_completeness_pct", "company_style")
                if section.get(key)
            },
        },
    }
    raw = await generate_text(
        _SYS_REPORT,
        json.dumps(context, ensure_ascii=False, default=str),
        temperature=0.3,
        max_tokens=900,
    )
    if not raw:
        return None
    try:
        data = json.loads(extract_json_object(clean_json_response(raw)))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def build_feedback_report_async(session: dict[str, Any]) -> dict[str, Any]:
    """Heuristic report enriched with a transcript-grounded LLM pass.

    Falls back to the pure-heuristic report if the model is unavailable or returns
    nothing, so the endpoint always renders."""
    report = build_feedback_report(session)
    try:
        synth = await _llm_report_synthesis(session, report)
    except Exception:
        synth = None
    if not synth:
        return report

    summary = str(synth.get("summary", "")).strip()
    skill_gap = str(synth.get("skill_gap", "")).strip()
    strengths = [str(s).strip() for s in synth.get("strengths", []) if str(s).strip()]
    weaknesses = [str(w).strip() for w in synth.get("weaknesses", []) if str(w).strip()]
    suggestions = [str(x).strip() for x in synth.get("suggestions", []) if str(x).strip()]
    parameters = _normalise_parameters(synth.get("parameters", []))
    topic_mastery = _normalise_topic_mastery(synth.get("topic_mastery", []))

    if summary:
        report["summary"] = summary
    if skill_gap:
        report["skill_gap"] = skill_gap
    if strengths:
        report["strengths"] = strengths
    if weaknesses:
        report["weak_areas"] = weaknesses
    if suggestions:
        report["study_plan"] = suggestions
    if parameters:
        report["parameter_scores"] = parameters
    if topic_mastery:
        report["topic_mastery"] = topic_mastery
    report["ai_generated"] = bool(summary or strengths or weaknesses or parameters)
    return report
