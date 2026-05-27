from __future__ import annotations

import json
import re
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
    exchange_count = int(session.get("exchange_count", 0) or 0)
    overall = _overall_score(scores, integrity["score"], round_section.get("round_score", 0), exchange_count, session)
    return {
        "session_id": session.get("session_id", ""),
        "round_type": round_type,
        "target_company": session.get("target_company", ""),
        "job_role": session.get("job_role", ""),
        "overall_score": overall,
        "hiring_signal": _hiring_signal(overall),
        "summary": _summary(session, round_section, overall),
        "scores": scores,
        "parameter_scores": round_section.get("parameter_scores", []),
        "topic_mastery": round_section.get("topic_mastery", []),
        "scoring_explanation": round_section.get("scoring_explanation", ""),
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
        "ai_generated": False,
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
    # Use accumulated graph session score when no code run; never pad with arbitrary constant
    _dsa_mem = session.get("dsa", {})
    _sess_sc = _dsa_mem.get("session_scores") if isinstance(_dsa_mem.get("session_scores"), dict) else {}
    _sess_raw = float(_sess_sc.get("overall", 0) or 0)  # 0-1 scale
    _exchange_ct = int(session.get("exchange_count", 0) or 0)
    _no_code_score = round(_sess_raw * 80, 1) if _sess_raw > 0 else 0
    return {
        "type": "dsa",
        "title": "DSA Round",
        "round_score": round(run_score if total else (_no_code_score if _exchange_ct > 0 else 0), 1),
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
        "strengths": _dedupe(strengths),
        "weak_areas": _dedupe(weak_areas),
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
    avg_score = _avg_project_question_scores(turns) if turns else 0
    strengths = []
    weak_areas = list(latest_flags)
    jd_skills = memory.get("jd_signals", {}).get("skills", [])
    jd_has_input = bool(memory.get("jd_signals", {}).get("has_jd"))
    resume_has_project = int(memory.get("resume_focus", {}).get("project_count", 0) or 0) > 0
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
    evaluation_sources = _evaluation_source_summary(turns)

    project_discussed = _candidate_discussed_project(turns, project)
    jd_hits = _turn_hits(turns, "jd_skill_hits")
    resume_hits = _turn_hits(turns, "resume_skill_hits")
    company_hits = _turn_hits(turns, "company_focus_hits")
    role_hits = _turn_hits(turns, "role_alignment_hits")
    llm_strengths = _turn_hits(turns, "strengths")
    llm_weak_areas = _turn_hits(turns, "weak_areas")
    if llm_strengths:
        strengths.extend(llm_strengths[:4])
    if project and project_discussed:
        strengths.append(f"Explained project evidence related to {project}.")
    if jd_hits:
        strengths.append(f"Connected answers to JD signals actually mentioned: {', '.join(jd_hits[:5])}.")
    if resume_hits:
        strengths.append(f"Used resume/JD skill overlap as evidence: {', '.join(resume_hits[:5])}.")
    if company_hits:
        strengths.append(f"Addressed company focus areas in answers: {', '.join(company_hits[:5])}.")
    if role_hits:
        strengths.append(f"Connected experience to role context: {', '.join(role_hits[:4])}.")
    if star_completeness_pct >= 75:
        strengths.append(f"STAR framework used in {star_completeness_pct:.0f}% of turns.")

    if not turns:
        weak_areas.append("No Project + Behavioural answer turns were recorded.")
    weak_areas.extend(llm_weak_areas[:4])
    if resume_has_project and not project_discussed:
        weak_areas.append(f"Resume project {project} was available as context but was not clearly proven in candidate answers.")
    if jd_has_input and not jd_hits:
        weak_areas.append("Job description was provided, but answers did not clearly connect to its required skills or responsibilities.")
    if memory.get("round_config", {}).get("focus_areas") and not company_hits:
        weak_areas.append("Company/round focus areas were available, but candidate answers did not clearly address them.")
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
    parameter_scores = _project_parameter_scores(turns, latest_scores, latest_flags)

    return {
        "type": "project_behavioral",
        "title": "Project + Behavioural Round",
        "round_score": round(avg_score, 1),
        "parameter_scores": parameter_scores,
        "scoring_explanation": (
            "Project + Behavioural scoring is based on interview evidence: personal ownership, verified impact, "
            "STAR completeness, technical depth, communication, and authenticity. Unsupported claims, contradictions, "
            "and unclear personal contribution cap the score even if the answer sounds fluent."
        ),
        "company_style": memory.get("company_style", ""),
        "company_profile": memory.get("company_profile", ""),
        "resume_focus": memory.get("resume_focus", {}),
        "project_discussed": project_discussed,
        "jd_signals": memory.get("jd_signals", {}),
        "demonstrated_jd_signals": jd_hits,
        "demonstrated_resume_skills": resume_hits,
        "demonstrated_company_focus": company_hits,
        "demonstrated_role_alignment": role_hits,
        "turn_count": len(turns),
        "evaluation_sources": evaluation_sources,
        "latest_scores": latest_scores,
        "latest_flags": latest_flags,
        "star_breakdown": star_counts,
        "star_completeness_pct": star_completeness_pct,
        "exaggeration_turns": exaggeration_turns,
        "contradiction_history": contradiction_history,
        "strengths": _dedupe(strengths),
        "weak_areas": _dedupe(weak_areas),
        "evidence": _project_report_evidence(turns[-5:]),
    }


def _cs_section(session: dict[str, Any]) -> dict[str, Any]:
    memory = session.get("cs_fundamentals", {})
    questions = memory.get("questions_asked", [])
    latest_scores = memory.get("latest_scores", {})
    latest_flags = memory.get("latest_flags", [])
    scratchpad_history = memory.get("scratchpad_history", [])
    score = _avg_question_scores(questions) if questions else (_avg_scores_to_hundred(latest_scores) if latest_scores else 0)
    strengths = []
    weak_areas = list(latest_flags)
    evaluation_sources = _evaluation_source_summary(questions)
    llm_strengths = _turn_hits(questions, "strengths")
    llm_weak_areas = _turn_hits(questions, "weak_areas")
    missing_concepts = _turn_hits(questions, "missing_concepts")
    if llm_strengths:
        strengths.extend(llm_strengths[:4])
    strong_evidence = _cs_strength_evidence(questions)
    if strong_evidence:
        strengths.extend(strong_evidence[:3])
    if scratchpad_history:
        strengths.append(f"Used scratchpad evidence in {len(scratchpad_history)} turn{'s' if len(scratchpad_history) != 1 else ''}.")
    if memory.get("weak_topics"):
        weak_areas.append(f"Weak topics to revise: {', '.join(memory.get('weak_topics', [])[:4])}.")
    weak_areas.extend(llm_weak_areas[:4])
    if missing_concepts:
        weak_areas.append(f"Missing CS concepts in answers: {', '.join(missing_concepts[:5])}.")
    if not questions:
        weak_areas.append("No CS Fundamentals answer turns were recorded.")
    misconception_count = sum(len(q.get("misconceptions", []) or []) for q in questions)
    if misconception_count:
        weak_areas.append(
            f"{misconception_count} incorrect concept signal{'s' if misconception_count != 1 else ''} detected; wrong definitions receive little to no correctness credit."
        )
    parameter_scores = _cs_parameter_scores(questions, latest_scores)
    if parameter_scores:
        score = _avg_dict({item["name"]: item["score"] for item in parameter_scores})
    topic_mastery = _topic_mastery_from_questions(questions)
    return {
        "type": "cs_fundamentals",
        "title": "CS Fundamentals Round",
        "round_score": round(score or 35, 1),
        "parameter_scores": parameter_scores,
        "topic_mastery": topic_mastery,
        "scoring_explanation": (
            "CS Fundamentals scoring follows real interview judgment: correctness is the gate. "
            "A clear but wrong answer is capped low, while high scores require correct definitions, practical application, "
            "tradeoff depth, and readable communication across the topics actually asked."
        ),
        "current_topic": memory.get("current_topic", ""),
        "topic_plan": memory.get("topic_plan", []),
        "topics_covered": memory.get("topics_covered", []),
        "strong_topics": memory.get("strong_topics", []),
        "weak_topics": memory.get("weak_topics", []),
        "latest_scores": latest_scores,
        "latest_flags": latest_flags,
        "scratchpad_observations": scratchpad_history[-5:],
        "pending_question": memory.get("pending_question", {}),
        "last_answered_topic": memory.get("last_answered_topic", ""),
        "evaluation_sources": evaluation_sources,
        "strengths": strengths,
        "weak_areas": weak_areas,
        "evidence": _cs_report_evidence(questions[-6:]),
    }


def _project_parameter_scores(
    turns: list[dict[str, Any]],
    latest_scores: dict[str, Any],
    latest_flags: list[str],
) -> list[dict[str, Any]]:
    source = turns or [{"scores": latest_scores, "flags": latest_flags}]
    score_sets = [item.get("scores", {}) for item in source if item.get("scores")]
    if not score_sets:
        return []

    def avg_score(*keys: str) -> int:
        values = [
            _score_to_hundred(scores[key])
            for scores in score_sets
            for key in keys
            if isinstance(scores.get(key), (int, float))
        ]
        return int(round(sum(values) / len(values))) if values else 0

    flags = [flag for item in source for flag in (item.get("flags", []) or [])]
    contradiction_count = sum(1 for flag in flags if "contradiction" in str(flag).lower())
    exaggeration_count = sum(1 for item in source if item.get("exaggeration_risk"))
    accountability_count = sum(1 for flag in flags if "ownership" in str(flag).lower() or "personally" in str(flag).lower())
    missing_context_count = sum(1 for flag in flags if "resume project" in str(flag).lower() or "job description" in str(flag).lower())

    ownership = _cap_score(avg_score("ownership"), 65 if accountability_count else 100)
    impact = _cap_score(avg_score("impact"), 60 if any("quantified" in str(flag).lower() for flag in flags) else 100)
    context = _cap_score(avg_score("context_alignment"), 60 if missing_context_count else 100)
    authenticity = 100 - min(70, exaggeration_count * 25 + contradiction_count * 30)

    return [
        {
            "name": "Ownership & Impact",
            "score": int(round((ownership * 0.4) + (impact * 0.35) + (context * 0.25))),
            "note": "Credit requires clear personal contribution, verifiable outcome, and grounding in the resume/JD context; unclear 'we' language, unquantified impact, or missing context caps this score.",
        },
        {
            "name": "STAR Structure",
            "score": avg_score("star_completeness"),
            "note": "Measures whether answers included situation, task, candidate action, result, and reflection rather than only a project summary.",
        },
        {
            "name": "Technical Depth",
            "score": avg_score("technical_depth"),
            "note": "Rewards architecture, tradeoffs, failure modes, scale, and implementation details that the candidate personally explained.",
        },
        {
            "name": "Communication",
            "score": avg_score("specificity", "reflection"),
            "note": "Rewards concise, specific, structured answers; vague or over-long answers do not receive full credit.",
        },
        {
            "name": "Authenticity",
            "score": max(0, authenticity),
            "note": "Starts high, then drops for unsupported high-impact claims, exaggeration risk, or metric contradictions.",
        },
    ]


def _avg_project_question_scores(turns: list[dict[str, Any]]) -> float:
    values = []
    for turn in turns:
        scores = turn.get("scores", {}) or {}
        if isinstance(scores.get("question_score"), (int, float)):
            values.append(_score_to_hundred(scores["question_score"]))
            continue
        if scores:
            ownership = _score_to_hundred(scores.get("ownership", 0))
            technical_depth = _score_to_hundred(scores.get("technical_depth", 0))
            impact = _score_to_hundred(scores.get("impact", 0))
            star = _score_to_hundred(scores.get("star_completeness", 0))
            context = _score_to_hundred(scores.get("context_alignment", 0))
            values.append(
                ownership * 0.22
                + technical_depth * 0.22
                + impact * 0.20
                + star * 0.18
                + context * 0.18
            )
    return round(sum(values) / len(values), 1) if values else 0.0


def _cs_strength_evidence(questions: list[dict[str, Any]]) -> list[str]:
    strengths = []
    for question in questions:
        scores = question.get("scores", {}) or {}
        topic = question.get("topic", "CS Fundamentals")
        correctness = _score_to_ten(scores.get("correctness", 0))
        application = _score_to_ten(scores.get("application", 0))
        depth = _score_to_ten(scores.get("depth", 0))
        if correctness >= 7.5 and application >= 6:
            subtopic = question.get("asked_subtopic") or topic
            strengths.append(f"Answered {topic} / {subtopic} with correct concept signals and practical application.")
        elif correctness >= 7.5 and depth >= 6:
            strengths.append(f"Showed solid conceptual correctness on {topic} with some depth/tradeoff evidence.")
    return _dedupe(strengths)


def _score_to_ten(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0
    score = float(value)
    return score * 10 if 0 <= score <= 1 else score


def _score_to_hundred(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0
    score = float(value)
    if 0 <= score <= 1:
        return score * 100
    if score <= 10:
        return score * 10
    return score


def _evaluation_source_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in items:
        source = str(item.get("evaluation_source") or "unknown").strip() or "unknown"
        counts[source] = counts.get(source, 0) + 1
    primary = "none"
    if counts:
        primary = max(counts, key=counts.get)
    return {
        "primary": primary,
        "counts": counts,
        "llm_turns": counts.get("llm", 0),
        "fallback_turns": counts.get("local_fallback", 0),
        "mixed": len([source for source, count in counts.items() if count]) > 1,
    }


def _turn_hits(turns: list[dict[str, Any]], key: str) -> list[str]:
    return _dedupe([
        str(item).strip()
        for turn in turns
        for item in (turn.get(key, []) or [])
        if str(item).strip()
    ])


def _project_report_evidence(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for turn in turns:
        evidence.append({
            **turn,
            "answer_text": turn.get("answer_text") or turn.get("answer_excerpt", ""),
            "context_alignment": {
                "project_discussed": turn.get("project_discussed", False),
                "jd_skill_hits": turn.get("jd_skill_hits", []),
                "resume_skill_hits": turn.get("resume_skill_hits", []),
                "company_focus_hits": turn.get("company_focus_hits", []),
                "role_alignment_hits": turn.get("role_alignment_hits", []),
            },
            "evaluation_source": turn.get("evaluation_source", "unknown"),
            "next_question": turn.get("next_question", ""),
            "next_question_reason": turn.get("next_question_reason", ""),
        })
    return evidence


def _cs_report_evidence(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for question in questions:
        evidence.append({
            **question,
            "answer_text": question.get("answer_text") or question.get("answer_excerpt", ""),
            "asked_subtopic": question.get("asked_subtopic", ""),
            "asked_question_type": question.get("asked_question_type") or question.get("question_type", ""),
            "asked_question": question.get("asked_question", ""),
            "evaluation_source": question.get("evaluation_source", "unknown"),
            "next_question_reason": question.get("next_question_reason", ""),
        })
    return evidence


def _candidate_discussed_project(turns: list[dict[str, Any]], project: str) -> bool:
    if not turns or not project:
        return False
    explicit_project_flags = [
        turn.get("project_discussed")
        for turn in turns
        if "project_discussed" in turn
    ]
    if explicit_project_flags:
        return any(flag is True for flag in explicit_project_flags)
    project_tokens = {
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9]+", project)
        if len(token) >= 4
    }
    for turn in turns:
        answer = f"{turn.get('answer_text', '')} {turn.get('answer_excerpt', '')}".lower()
        word_count = len(re.findall(r"[a-zA-Z0-9+.#-]+", answer))
        if word_count < 25:
            continue
        if project_tokens and any(token in answer for token in project_tokens):
            return True
    return False


def _cs_parameter_scores(questions: list[dict[str, Any]], latest_scores: dict[str, Any]) -> list[dict[str, Any]]:
    source = questions or [{"scores": latest_scores}]
    score_sets = [item.get("scores", {}) for item in source if item.get("scores")]
    if not score_sets:
        return []

    def avg_score(key: str) -> int:
        values = [_score_to_hundred(scores[key]) for scores in score_sets if isinstance(scores.get(key), (int, float))]
        return int(round(sum(values) / len(values))) if values else 0

    correctness = avg_score("correctness")
    correctness_cap = 45 if any(item.get("misconceptions") for item in source) else 100
    correctness = _cap_score(correctness, correctness_cap)

    return [
        {
            "name": "Conceptual Clarity",
            "score": _cap_score(avg_score("clarity"), 70 if correctness < 45 else 100),
            "note": "Rewards precise definitions in the candidate's own words; clarity is capped when the concept itself is wrong.",
        },
        {
            "name": "Correctness",
            "score": correctness,
            "note": "Primary gate for CS rounds. Incorrect definitions or contradictions receive little credit even if the answer is fluent.",
        },
        {
            "name": "Examples & Application",
            "score": _cap_score(avg_score("application"), 55 if correctness < 45 else 100),
            "note": "Requires a correct real-system example, query, protocol flow, or design situation tied to the concept.",
        },
        {
            "name": "Depth of Understanding",
            "score": _cap_score(avg_score("depth"), 55 if correctness < 45 else 100),
            "note": "Rewards tradeoffs, edge cases, comparisons, and failure modes; wrong core concepts cap depth.",
        },
        {
            "name": "Communication",
            "score": avg_score("communication"),
            "note": "Measures whether the answer was structured enough for an interviewer to follow without hiding gaps behind buzzwords.",
        },
    ]


def _topic_mastery_from_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for question in questions:
        topic = str(question.get("topic", "")).strip()
        if not topic:
            continue
        by_topic.setdefault(topic, []).append(question)
    mastery = []
    for topic, items in by_topic.items():
        correctness_values = [
            _score_to_hundred(item.get("scores", {}).get("correctness", 0))
            for item in items
            if isinstance(item.get("scores", {}).get("correctness"), (int, float))
        ]
        score = int(round(sum(correctness_values) / len(correctness_values))) if correctness_values else 0
        if any(item.get("misconceptions") for item in items):
            score = min(score, 45)
        flags = [flag for item in items for flag in (item.get("flags", []) or [])]
        note = flags[0] if flags else f"Answered {len(items)} question{'s' if len(items) != 1 else ''} on this topic with no detected misconception."
        mastery.append({"topic": topic, "mastery": score, "note": note})
    return mastery


def _cap_score(score: int | float, cap: int | float) -> int:
    return int(round(max(0, min(float(score), float(cap)))))


def _early_exit_penalty(session: dict[str, Any]) -> float:
    """Penalize abandoning the round early without a working solution.

    Compares time used vs allocated. Ending with <50% of the allotted time used and
    no fully-passing solution deducts up to 25 points, scaled by how early the
    candidate bailed (bailing at ~0% time costs the full 25; at 45% costs ~2.5).
    Returns 0 when timing data is unavailable or the problem was actually solved.
    """
    prog = session.get("dsa_progress") or {}
    allocated_s = float(prog.get("allocated_minutes", 0) or 0) * 60
    elapsed_s = float(prog.get("elapsed_seconds", 0) or 0)
    if allocated_s <= 0 or elapsed_s <= 0:
        return 0.0
    runs = session.get("code_runs", [])
    latest = runs[-1] if runs else {}
    total = int(latest.get("total_testcases", 0) or 0)
    passed = int(latest.get("passed_testcases", 0) or 0)
    if total > 0 and passed == total:
        return 0.0  # solved it — leaving early is fine
    used = elapsed_s / allocated_s
    if used >= 0.5:
        return 0.0
    # Up to 15 points, proportional to how early they bailed. Kept moderate because the
    # no-code case is already penalized by round_score=0 in the blend — this shouldn't
    # double-count a quitter down to a no-show's score.
    return round(min(15.0, (0.5 - used) * 30), 1)


def _overall_score(
    scores: dict[str, float],
    integrity_score: int,
    round_score: float,
    exchange_count: int = 0,
    session: dict[str, Any] | None = None,
) -> float:
    if exchange_count == 0:
        return 0.0
    # For DSA: use the graph's accumulated session score as the primary signal.
    # This avoids inflating the overall via keyword-based text scores that always
    # return a non-zero floor regardless of candidate quality.
    if session and session.get("round_type", "dsa") == "dsa":
        dsa_mem = session.get("dsa", {})
        sess_sc = dsa_mem.get("session_scores") if isinstance(dsa_mem.get("session_scores"), dict) else {}
        sess_overall = float(sess_sc.get("overall", 0) or 0) * 100  # 0-100
        if sess_overall > 0 or round_score > 0:
            integrity_penalty = max(0.0, (100 - integrity_score) * 0.10)
            base = sess_overall * 0.60 + round_score * 0.40
            base -= _early_exit_penalty(session)
            return round(max(0.0, min(100.0, base - integrity_penalty)), 1)
        # No graph scores and no code: very low, capped at 5 (they showed up but did nothing)
        return round(min(5.0, exchange_count * 0.5), 1)
    if session and session.get("round_type") == "project_behavioral":
        return round(max(0.0, min(100.0, float(round_score or 0))), 1)
    # Non-DSA rounds: text-analysis based scoring
    avg = sum(scores.values()) / max(1, len(scores)) if scores else 0
    communication = avg * 20 if avg > 0 else 0
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
    round_type = session.get("round_type", "")
    title = section.get("title", "Interview")
    evidence_count = len(section.get("evidence", []))
    if round_type == "project_behavioral":
        return f"{title} report for {role} at {company}. The score is {overall}/100 based on how directly and meaningfully the answers addressed the interviewer prompts."
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
    values = [_avg_scores_to_hundred(turn.get("scores", {})) for turn in turns if turn.get("scores")]
    return round(sum(values) / len(values), 1) if values else 0


def _avg_question_scores(questions: list[dict[str, Any]]) -> float:
    values = [_avg_scores_to_hundred(question.get("scores", {})) for question in questions if question.get("scores")]
    return round(sum(values) / len(values), 1) if values else 0


def _avg_scores_to_hundred(scores: dict[str, Any]) -> float:
    values = [_score_to_hundred(value) for value in scores.values() if isinstance(value, (int, float))]
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
Score like a real interviewer, not like a keyword matcher. Correctness and truthfulness are gates:
- If the candidate gave a wrong answer, contradicted the question, or made a technically false claim, give little or no credit for that parameter even if the wording sounded confident.
- Do not award points for mentioning a correct term when the surrounding explanation is wrong.
- If the transcript does not prove a skill, score it conservatively and say the evidence is missing.
- For Project & Behavioural, do not reward inflated or unsupported claims; ownership, impact, and authenticity require concrete first-person evidence.
- For CS Fundamentals, correctness controls the score; application and depth must be capped low when the core concept is wrong.

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
- Any score above 80 requires positive evidence and no unresolved correctness/truthfulness issue for that parameter.
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


def _normalise_parameters(raw: Any, expected_names: list[str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    expected = expected_names or []
    by_name: dict[str, dict[str, Any]] = {}
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
        normalised = {"name": name, "score": score, "note": str(item.get("note", "")).strip()}
        by_name[name] = normalised
        out.append(normalised)
    if not expected:
        return out
    return [
        by_name.get(name, {"name": name, "score": 0, "note": "No reliable evidence was available for this parameter."})
        for name in expected
    ]


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
    """Heuristic report enriched with transcript-grounded LLM synthesis and DSA deep evaluation.

    Layer 1 (all rounds): general synthesis — summary, skill gap, parameter scores, topic mastery.
    Layer 2 (DSA only): comprehensive coaching report with 10 core metrics, advanced metrics,
    company-tailored feedback, weakness analysis, learning plan, benchmarking, and final verdict.
    Falls back gracefully to the pure-heuristic report when the model is unavailable."""
    report = build_feedback_report(session)

    # Layer 1: general LLM synthesis (all round types)
    try:
        synth = await _llm_report_synthesis(session, report)
    except Exception:
        synth = None

    if synth:
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

    # Layer 2: round-specific comprehensive evaluation
    round_type = report.get("round_type", "")

    if round_type == "dsa":
        try:
            dsa_eval = await _run_dsa_deep_eval(session, report)
        except Exception:
            dsa_eval = None
        # Always provide dsa_evaluation — fall back to heuristic when LLM is unavailable
        if not dsa_eval:
            dsa_eval = _build_heuristic_dsa_evaluation(session, report)
        # Reconcile: force the roadmap + behaviour coaching to be deterministic,
        # weakness-tied, and engagement-aware regardless of which path produced the
        # eval — so the roadmap is never hardcoded/repeated and coaching never claims
        # "basic interaction" on a no-show.
        dsa_eval = _reconcile_dsa_evaluation(dsa_eval, session, report)
        report["dsa_evaluation"] = dsa_eval
        verdict_signal = (dsa_eval.get("final_verdict") or {}).get("signal", "")
        if verdict_signal:
            report["hiring_signal"] = verdict_signal

    elif round_type == "cs_fundamentals":
        try:
            cs_eval = await _run_cs_deep_eval(session, report)
        except Exception:
            cs_eval = None
        if cs_eval:
            report["cs_evaluation"] = cs_eval
            verdict_signal = (cs_eval.get("final_verdict") or {}).get("signal", "")
            if verdict_signal:
                report["hiring_signal"] = verdict_signal

    elif round_type == "project_behavioral":
        try:
            pb_eval = await _run_pb_deep_eval(session, report)
        except Exception:
            pb_eval = None
        if pb_eval:
            report["pb_evaluation"] = pb_eval
            verdict_signal = (pb_eval.get("final_verdict") or {}).get("signal", "")
            if verdict_signal:
                report["hiring_signal"] = verdict_signal

    return report


# ─────────────────────────────────────────────────────────────────────────────
# DSA DEEP EVALUATION — comprehensive post-interview coaching report
# ─────────────────────────────────────────────────────────────────────────────

_SYS_DSA_DEEP_EVAL = """You are a senior FAANG technical interviewer writing a comprehensive post-interview coaching report that the candidate will read. Every insight MUST be grounded in what THIS candidate actually said, wrote, or did — never use generic feedback that could describe any candidate.

Bad feedback: "Weak in graphs."
Good feedback: "You identified BFS correctly but repeatedly revisited nodes due to improper visited-state handling in the adjacency traversal, causing TLE on the cycle-detection test case."

Return ONLY a valid JSON object — no markdown, no prose outside JSON:

{
  "core_metrics": [
    {"name": "Problem Solving Ability", "score": <int 0-100>, "label": "Exceptional|Strong|Competent|Developing|Weak", "note": "<2-3 sentences citing specific moments in this session>"},
    {"name": "DSA Knowledge", "score": <int>, "label": "<one of the 5 labels>", "note": "<specific to this session>"},
    {"name": "Optimization Skill", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Coding Accuracy", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Communication & Explanation", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Confidence During Interview", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Hint Dependency", "score": <int>, "label": "<...>", "note": "100=fully independent, 0=constant hand-holding; cite the actual hint count from context"},
    {"name": "Adaptability", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Complexity Analysis", "score": <int>, "label": "<...>", "note": "<specific>"},
    {"name": "Edge Case Awareness", "score": <int>, "label": "<...>", "note": "<specific>"}
  ],
  "advanced_metrics": {
    "contradiction_detection": {
      "score": <int 0-100>,
      "incidents": [{"claim_before": "<exact prior claim>", "claim_now": "<conflicting claim>", "analysis": "<1 sentence>"}],
      "summary": "<1-2 sentences — 100=fully consistent, lower if contradictions found>"
    },
    "thought_process_quality": {
      "score": <int>,
      "pattern": "systematic|exploratory|reactive|chaotic",
      "note": "<2 sentences on how this candidate structured their thinking>"
    },
    "company_fit": {
      "score": <int>,
      "fit_signals": ["<specific positive signal from this session>"],
      "concern_signals": ["<specific concern from this session>"],
      "note": "<1-2 sentences on fit>"
    },
    "interview_flow": {
      "score": <int>,
      "note": "<2 sentences on pacing and phase transitions in this session>"
    }
  },
  "company_tailored": {
    "company": "<target company name from context>",
    "bar_assessment": "Below Bar|Approaching Bar|At Bar|Above Bar",
    "optimization_quality": {"score": <int>, "note": "<2 sentences specific to this company's optimization bar>"},
    "communication_clarity": {"score": <int>, "note": "<2 sentences>"},
    "followup_handling": {"score": <int>, "note": "<2 sentences on how they handled follow-up constraints>"},
    "coding_speed": {"score": <int>, "note": "<2 sentences>"},
    "debugging_behavior": {"score": <int>, "note": "<2 sentences>"},
    "summary": "<2-3 sentences on overall fit for this specific company's interview bar>"
  },
  "weakness_analysis": [
    {
      "area": "<specific sub-skill — e.g. 'BFS visited-state management', NOT just 'graphs'>",
      "specific_issue": "<exactly what went wrong in THIS session, citing a specific moment>",
      "why_it_matters": "<1 sentence: why interviewers treat this as a signal>",
      "improvement": "<1 concrete, actionable next step>"
    }
  ],
  "improvement_recommendations": [
    {
      "category": "Practice Patterns|Interview Habits|Optimization Strategy|Debugging Strategy|Communication|Edge Case Handling",
      "recommendation": "<specific and actionable, referencing this candidate's actual behavior>",
      "priority": "high|medium|low"
    }
  ],
  "behavior_coaching": [
    {
      "observation": "<specific behavior observed in this session — e.g. 'began coding at minute 3 without stating brute-force approach'>",
      "impact": "<how this behavior affected the quality of this interview>",
      "coaching": "<what a senior interviewer would tell this specific candidate>"
    }
  ],
  "learning_plan": {
    "one_week": {
      "daily_goals": ["<5 specific daily practice goals based on THIS candidate's weaknesses>"],
      "focus_topics": ["<3-4 specific topics to target>"],
      "problem_types": ["<3-4 problem patterns to drill>"]
    },
    "two_week": {
      "daily_goals": ["<5 goals for week 2, progressing from week 1>"],
      "focus_topics": ["<4-5 topics>"],
      "problem_types": ["<4-5 patterns>"]
    },
    "recommended_problems": ["<6 specific problem types or named patterns tailored to this candidate's gaps>"]
  },
  "benchmarking": {
    "faang_readiness_score": <int 0-100>,
    "estimated_level": "Below L3|L3/Junior|L4/Mid|L5/Senior",
    "comparisons": [
      {"metric": "<specific measurable metric>", "candidate_score": <int>, "faang_bar": <int>, "gap_note": "<1 sentence on the gap and what it takes to close it>"}
    ],
    "overall_readiness_note": "<2 sentences on FAANG readiness based on THIS session>"
  },
  "strength_recognition": [
    {
      "strength": "<specific strength — NOT generic; name the exact skill or behavior>",
      "evidence": "<what they specifically did in this session that demonstrates this>",
      "interview_value": "<why this matters in a real FAANG interview>"
    }
  ],
  "final_verdict": {
    "signal": "Strong Hire|Hire|Lean Hire|Lean Reject|Reject",
    "confidence_score": <int 0-100>,
    "summary": "<2-3 sentences summarizing this specific candidate's overall performance>",
    "biggest_strength": "<1 sentence>",
    "biggest_weakness": "<1 sentence>",
    "most_important_next_step": "<1 concrete, actionable sentence>"
  }
}

Constraints:
- core_metrics: exactly 10 items in the order listed above
- weakness_analysis: 2-4 items; each must cite a specific moment, code behavior, or transcript quote
- improvement_recommendations: 4-6 items covering different categories
- behavior_coaching: 2-4 items based on observed behaviors
- strength_recognition: 2-4 items with specific evidence
- benchmarking comparisons: 3-5 items
- All scores are integers 0-100
- Never write advice that could describe any random candidate
- Score conservatively when evidence is thin — say so explicitly in the note"""


def _build_dsa_deep_context(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    dsa = session.get("dsa", {})
    problem = session.get("problem", {})
    code_runs = session.get("code_runs", [])
    latest_run = code_runs[-1] if code_runs else {}
    signals = session.get("behavioral_signals", {})

    failing_cases = [
        {
            "input": str(tc.get("input", ""))[:120],
            "expected": str(tc.get("expected_output", ""))[:120],
            "actual": str(tc.get("actual_output", ""))[:120],
        }
        for tc in latest_run.get("testcase_results", [])
        if not tc.get("passed")
    ][:3]

    return {
        "company": session.get("target_company", "Unknown"),
        "role": session.get("job_role", "Software Engineer"),
        "experience_level": session.get("experience_level", "mid"),
        "problem": {
            "title": problem.get("title", ""),
            "difficulty": problem.get("difficulty", ""),
            "topics": (problem.get("topics") or [])[:6],
        },
        "test_results": {
            "passed": int(latest_run.get("passed_testcases", 0) or 0),
            "total": int(latest_run.get("total_testcases", 0) or 0),
            "score_pct": float(latest_run.get("overall_score", 0) or 0),
            "run_count": len(code_runs),
            "failing_sample": failing_cases,
        },
        "behavioral": {
            "hint_count": int(session.get("hint_count", 0) or 0),
            "large_pastes": int(signals.get("large_pastes", 0) or 0),
            "paste_events": int(signals.get("paste_events", 0) or 0),
            "longest_silence_s": float((dsa.get("silence_profile") or {}).get("longest_gap", 0)),
            "approach_switches": int(signals.get("approach_switches", 0) or 0),
        },
        "known_weak_areas": (dsa.get("known_weak_areas") or [])[:5],
        "known_strong_areas": (dsa.get("known_strong_areas") or [])[:5],
        "contradiction_history": [
            {
                "claim_before": c.get("claim_before", ""),
                "claim_now": c.get("claim_now", ""),
                "topic": c.get("topic", ""),
            }
            for c in (dsa.get("contradiction_history") or [])[-3:]
        ],
        "heuristic_signals": {
            "strengths": ((base.get("round_breakdown") or {}).get("strengths") or [])[:4],
            "weak_areas": (base.get("weak_areas") or [])[:4],
            "parameter_scores": (base.get("parameter_scores") or [])[:5],
        },
        "transcript": _build_transcript(session, max_turns=25, per_msg=500),
    }


async def _run_dsa_deep_eval(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    ctx = _build_dsa_deep_context(session, base)
    if not ctx.get("transcript"):
        return None
    raw = await generate_text(
        _SYS_DSA_DEEP_EVAL,
        json.dumps(ctx, ensure_ascii=False, default=str),
        temperature=0.25,
        max_tokens=2500,
    )
    if not raw:
        return None
    try:
        data = json.loads(extract_json_object(clean_json_response(raw)))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# Core-metric display name → underlying skill key, so the roadmap/coaching can be
# driven by the SAME numbers shown on the cards (whether the LLM or the heuristic
# produced them) — never by a separate, divergent source.
_METRIC_TO_SKILL: dict[str, str] = {
    "Problem Solving Ability": "approach_quality",
    "DSA Knowledge": "dsa_knowledge",
    "Optimization Skill": "complexity_analysis",
    "Coding Accuracy": "code_quality",
    "Communication & Explanation": "communication",
    "Complexity Analysis": "complexity_analysis",
    "Edge Case Awareness": "edge_cases",
    "Adaptability": "adaptability",
}


def _build_behavior_coaching(
    *,
    engaged: bool,
    exchange_count: int,
    hint_count: int,
    signals: dict[str, Any],
    comm_score: int,
    total: int,
    passed: int,
    dsa: dict[str, Any],
) -> list[dict[str, Any]]:
    """Behaviour coaching grounded in what actually happened — never a canned
    'basic interaction observed' line. Returns a clear no-participation note when
    the candidate didn't engage."""
    if not engaged:
        return [{
            "observation": f"No meaningful interaction was recorded ({exchange_count} exchange{'s' if exchange_count != 1 else ''}, no code executed).",
            "impact": "With no engagement there is no behaviour to coach and no signal to evaluate — this reads as a non-attempt.",
            "coaching": "Treat the next session like a real interview: think aloud from the first minute, ask one clarifying question, state your approach, and write code — even a partial attempt creates evaluable signal.",
        }]

    items: list[dict[str, Any]] = []
    if hint_count >= 2:
        items.append({
            "observation": f"Requested {hint_count} hints during the session.",
            "impact": "Hint dependency is a direct negative signal — it tells the interviewer you can't yet drive to a solution independently.",
            "coaching": "Practice timed problems with zero hints. When stuck, narrate partial reasoning aloud ('I know I need O(n) but I can't yet avoid the inner loop') instead of asking for the answer.",
        })
    if comm_score < 40:
        items.append({
            "observation": "Little narration was detected while you solved the problem.",
            "impact": "Silent problem-solving leaves the interviewer with nothing to evaluate — they score what you say as much as what you write.",
            "coaching": "Say each decision out loud as you make it: 'I'm using a stack here because I need LIFO matching.' Practice until that running commentary is automatic.",
        })
    large_pastes = int(signals.get("large_pastes", 0) or 0)
    if large_pastes:
        items.append({
            "observation": f"{large_pastes} large paste event{'s' if large_pastes != 1 else ''} detected in the editor.",
            "impact": "Large pastes look like copied solutions and erode the interviewer's trust in your authorship.",
            "coaching": "Type your solution incrementally and explain each block as you write it, so your problem-solving is visible and clearly your own.",
        })
    longest_silence = float((dsa.get("silence_profile") or {}).get("longest_gap", 0) or 0)
    if longest_silence > 20:
        items.append({
            "observation": f"A long silent gap (~{int(longest_silence)}s) occurred mid-session.",
            "impact": "Extended silence reads as being stuck — the interviewer can't tell whether you're thinking or lost.",
            "coaching": "When you need to think, say so: 'Give me a moment to reason about the complexity.' Narrate the thinking instead of going quiet.",
        })
    if total and passed < total:
        items.append({
            "observation": f"Your code passed {passed}/{total} visible tests.",
            "impact": "Stopping before all visible tests pass signals rushed verification — a red flag in a real interview.",
            "coaching": "Before declaring done, trace one normal case and one edge case by hand through your code and confirm the output.",
        })
    if not items:
        items.append({
            "observation": "You engaged steadily and produced evaluable signal throughout.",
            "impact": "Consistent engagement is the baseline interviewers expect — you cleared it.",
            "coaching": "Keep sharpening the top: state time/space complexity before coding and enumerate edge cases before submitting.",
        })
    return items[:4]


_NO_ENGAGE_PLAN: dict[str, Any] = {
    "one_week": {
        "daily_goals": [
            "Complete at least one full interview session end to end — there is no performance data to build a personalized plan from yet.",
            "Treat it as real: narrate your approach, write code, and run it before ending.",
        ],
        "focus_topics": [],
        "problem_types": [],
    },
    "two_week": {"daily_goals": [], "focus_topics": [], "problem_types": []},
    "recommended_problems": [],
}


def _reconcile_dsa_evaluation(ev: dict[str, Any], session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Make the deterministic, data-driven sections authoritative on EITHER path
    (LLM or heuristic): a weakness+topic-tied roadmap and behaviour coaching grounded
    in real signals. The LLM still owns the narrative (metric notes, weakness
    reasoning, verdict prose); this only guarantees the roadmap/coaching reflect the
    candidate's true performance and never repeat across interviews."""
    if not isinstance(ev, dict):
        return ev

    problem = session.get("problem", {}) or {}
    dsa = session.get("dsa", {}) or {}
    code_runs = session.get("code_runs", []) or []
    latest = code_runs[-1] if code_runs else {}
    total = int(latest.get("total_testcases", 0) or 0)
    passed = int(latest.get("passed_testcases", 0) or 0)
    hint_count = int(session.get("hint_count", 0) or 0)
    exchange_count = int(session.get("exchange_count", 0) or 0)
    signals = session.get("behavioral_signals", {}) or {}
    sess = dsa.get("session_scores") if isinstance(dsa.get("session_scores"), dict) else {}
    sess_overall = float(sess.get("overall", 0) or 0)
    overall = float(base.get("overall_score", 0) or 0)
    engaged = exchange_count > 0 and (overall >= 1.0 or total > 0 or sess_overall > 0.01)

    # Weak/strong skills derived from the eval's OWN core-metric scores → consistent
    # with the cards the candidate sees, no matter which path produced them.
    cm = {m.get("name"): int(m.get("score", 0) or 0) for m in (ev.get("core_metrics") or []) if isinstance(m, dict)}
    weak_skills: list[str] = []
    strong_skills: list[str] = []
    for name, score in cm.items():
        skill = _METRIC_TO_SKILL.get(name)
        if not skill:
            continue
        if score < 40 and skill not in weak_skills:
            weak_skills.append(skill)
        elif score >= 70 and skill not in strong_skills:
            strong_skills.append(skill)

    diff = str(dsa.get("difficulty_level") or problem.get("difficulty", "medium") or "medium").lower()
    if diff not in {"easy", "medium", "hard"}:
        diff = "medium"

    if engaged:
        ev["learning_plan"] = _build_learning_plan(
            known_weak=weak_skills,
            known_strong=strong_skills,
            approach_patterns=dsa.get("approach_patterns") or {},
            topics=problem.get("topics") or [],
            difficulty_level=diff,
            passed=passed,
            total=total,
            hint_count=hint_count,
            exchange_count=exchange_count,
        )
    else:
        ev["learning_plan"] = _NO_ENGAGE_PLAN

    ev["behavior_coaching"] = _build_behavior_coaching(
        engaged=engaged,
        exchange_count=exchange_count,
        hint_count=hint_count,
        signals=signals,
        comm_score=cm.get("Communication & Explanation", 0),
        total=total,
        passed=passed,
        dsa=dsa,
    )
    return ev


_WEAK_TO_TOPIC: dict[str, str] = {
    "approach_quality":    "Problem decomposition & brute-force-to-optimal transitions",
    "complexity_analysis": "Big-O analysis — time and space complexity reasoning",
    "code_quality":        "Clean code practices — naming, modularity, no redundant logic",
    "communication":       "Technical narration: speaking decisions aloud while coding",
    "debugging":           "Systematic debugging — trace the failing case before touching code",
    "edge_cases":          "Boundary condition enumeration before submission",
    "dsa_knowledge":       "Core DSA pattern recognition — when to use each structure",
    "adaptability":        "Handling interviewer pushback and pivoting approaches",
}

_WEAK_TO_PROBLEMS: dict[str, list[str]] = {
    "approach_quality":    ["Two Sum → 3Sum (brute to hash map)", "Coin Change (naive recursion → DP)", "Best Time to Buy and Sell Stock (greedy vs DP)"],
    "complexity_analysis": ["Merge Sort (derive O(n log n))", "Binary Search on answer", "LRU Cache (amortized O(1) design)"],
    "code_quality":        ["Valid Parentheses (clean stack)", "Reverse Linked List (minimal pointer logic)", "Merge Two Sorted Lists (readable iteration)"],
    "communication":       ["Group Anagrams (narrate key-building)", "Climbing Stairs (explain recurrence aloud)", "Max Depth of Binary Tree (DFS narration practice)"],
    "debugging":           ["Subarray Sum Equals K (trace off-by-one)", "Find Duplicate Number (trace in-place)", "Detect Cycle in Linked List (pointer trace)"],
    "edge_cases":          ["Contains Duplicate (empty, single)", "Rotate Array (k > n)", "Palindrome Number (negatives, single digit)"],
    "dsa_knowledge":       ["Number of Islands (BFS/DFS)", "Top K Frequent Elements (heap)", "Implement Trie (design)"],
    "adaptability":        ["Add Two Numbers (follow-up: no extra space)", "Remove Nth Node (follow-up: one pass)", "Word Search (follow-up: pruning)"],
}

_TOPIC_TO_PROBLEMS: dict[str, list[str]] = {
    "array":          ["Maximum Subarray", "Product of Array Except Self", "Container With Most Water"],
    "hash_map":       ["Group Anagrams", "Top K Frequent Elements", "Subarray Sum Equals K"],
    "two_pointer":    ["3Sum", "Trapping Rain Water", "Remove Duplicates from Sorted Array"],
    "sliding_window": ["Minimum Window Substring", "Longest Substring Without Repeating Characters", "Sliding Window Maximum"],
    "binary_search":  ["Search in Rotated Sorted Array", "Find Minimum in Rotated Sorted Array", "Koko Eating Bananas"],
    "graph":          ["Number of Islands", "Course Schedule", "Word Ladder"],
    "tree":           ["Level Order Traversal", "Lowest Common Ancestor", "Serialize and Deserialize Binary Tree"],
    "dynamic_programming": ["Coin Change", "Longest Increasing Subsequence", "Edit Distance"],
    "stack":          ["Min Stack", "Daily Temperatures", "Largest Rectangle in Histogram"],
    "heap":           ["Merge K Sorted Lists", "Find Median from Data Stream", "Task Scheduler"],
    "linked_list":    ["Reverse Linked List", "Detect Cycle", "Merge Two Sorted Lists"],
    "recursion":      ["Climbing Stairs", "Generate Parentheses", "Permutations"],
}


def _build_learning_plan(
    *,
    known_weak: list[str],
    known_strong: list[str],
    approach_patterns: dict[str, int],
    topics: list[str],
    difficulty_level: str,
    passed: int,
    total: int,
    hint_count: int,
    exchange_count: int,
) -> dict[str, Any]:
    # Normalize keys
    weak_keys = [w.lower().replace(" ", "_") for w in known_weak[:4]]
    topic_keys = [t.lower().replace(" ", "_") for t in topics[:4]]

    # Focus topics: weak areas first, then problem topics
    focus_w1 = [_WEAK_TO_TOPIC.get(k, k.replace("_", " ").title()) for k in weak_keys[:2]]
    focus_w1 += [t.replace("_", " ").title() for t in topic_keys[:2]]
    focus_w1 = list(dict.fromkeys(focus_w1))[:4] or [
        "Problem decomposition & brute-force-to-optimal transitions",
        "Big-O analysis — time and space complexity reasoning",
        "Edge case enumeration before submission",
        "Core DSA pattern recognition",
    ]

    # Recommended problems: LEAD with the actual problem's topic (so the roadmap is
    # visibly tied to the problem just attempted), then one per weak area.
    rec_problems: list[str] = []
    for k in topic_keys[:2]:
        for p in _TOPIC_TO_PROBLEMS.get(k, [])[:2]:
            if p not in rec_problems:
                rec_problems.append(p)
    for k in weak_keys[:3]:
        probs = _WEAK_TO_PROBLEMS.get(k, [])
        if probs and probs[0] not in rec_problems:
            rec_problems.append(probs[0])
    if len(rec_problems) < 4:
        for fallback in ["Two Sum (hash map pattern)", "Number of Islands (BFS/DFS)", "Coin Change (DP transition)", "Merge Intervals (sort + greedy)", "Binary Search on Rotated Array"]:
            if fallback not in rec_problems:
                rec_problems.append(fallback)
            if len(rec_problems) >= 6:
                break
    rec_problems = list(dict.fromkeys(rec_problems))[:6]

    # Problem types: distinct from rec_problems — practice categories
    prob_types: list[str] = []
    if "communication" in weak_keys:
        prob_types.append("Narration-first drills: state approach before writing any code")
    if "approach_quality" in weak_keys or "complexity_analysis" in weak_keys:
        prob_types.append("Brute-force-to-optimal transitions (Two Sum → 3Sum progression)")
    if "edge_cases" in weak_keys:
        prob_types.append("Edge-case audit: enumerate all boundaries before submitting")
    for k in topic_keys[:2]:
        if k in _TOPIC_TO_PROBLEMS:
            prob_types.append(f"{k.replace('_', ' ').title()} pattern problems")
    defaults_pt = ["Sliding Window / Two Pointer progressions", "BFS/DFS on graphs and matrices", "DP: subproblem identification practice"]
    for pt in defaults_pt:
        if len(prob_types) >= 4:
            break
        prob_types.append(pt)
    prob_types = list(dict.fromkeys(prob_types))[:4]

    # Week 1 daily goals — contextual
    week1_goals: list[str] = []
    if exchange_count <= 2:
        week1_goals.append("Commit to completing the full interview session — partial sessions generate almost zero evaluation signal. Practice until finishing is automatic.")
    if hint_count >= 2:
        week1_goals.append(f"You used {hint_count} hints this session. Practice 20-minute timed attempts with zero hints — when stuck, verbalize partial thinking: 'I know I need O(n) but I can't see how to avoid the inner loop.'")
    if "communication" in weak_keys:
        week1_goals.append("Narrate every decision as you code: 'I'm using a hash map here because lookup is O(1) and I need membership checks.' Practice until this monologue is automatic.")
    if "approach_quality" in weak_keys:
        week1_goals.append("Always state the brute-force solution first — even if you already see the optimal. This grounds your thinking and gives the interviewer a baseline to evaluate your reasoning.")
    if total and passed < total:
        week1_goals.append(f"Your code passed {passed}/{total} test cases. Before submitting, manually trace through 2 cases: one normal, one edge. Identify the exact diverging line.")
    if "complexity_analysis" in weak_keys:
        week1_goals.append("Before writing a single line, write the target Big-O as a comment. After coding, verify it by counting loops/recursion depth.")
    # Fill with contextual defaults
    ctx_defaults = [
        f"Solve 2 problems daily targeting: {', '.join(focus_w1[:2])}. State time/space complexity before writing any code.",
        "After each problem, study the optimal solution even if yours passed — understand the pattern, not just the code.",
        f"Set a 25-minute timer per problem. {difficulty_level.title()} problems are the target difficulty — practice at this level consistently.",
    ]
    for g in ctx_defaults:
        if len(week1_goals) >= 5:
            break
        week1_goals.append(g)

    # Week 2 daily goals
    weak_str = ", ".join(w.replace("_", " ") for w in known_weak[:2]) if known_weak else "your identified weak areas"
    week2_goals = [
        "Solve 3 problems daily including 1 hard. Full verbal narration throughout — no silent coding, no exceptions.",
        f"Mock interview session: focus specifically on {weak_str}. Record yourself and review the playback.",
        "For each problem: name the pattern category before touching code. Incorrect category identification is the most expensive mistake.",
        f"{'Revisit ' + weak_str + ' with targeted drills — spend 30 min daily on these specific areas.' if known_weak else 'Optimize every brute-force: ask yourself what information you can precompute to eliminate a loop.'}",
        "Review your 5 weakest recent attempts. Write down the root cause of each failure — not the fix, the cause.",
    ]

    focus_w2 = [w.replace("_", " ") for w in known_weak[:2]]
    focus_w2 += [t.replace("_", " ").title() for t in topic_keys]
    if len(focus_w2) < 3:
        focus_w2 += ["Dynamic Programming", "Graph Traversal", "Trees & Recursion"]
    focus_w2 = list(dict.fromkeys(focus_w2))[:5]

    return {
        "one_week": {
            "daily_goals": week1_goals[:5],
            "focus_topics": focus_w1,
            "problem_types": prob_types,
        },
        "two_week": {
            "daily_goals": week2_goals,
            "focus_topics": focus_w2,
            "problem_types": [
                "DP: define subproblem + recurrence before writing code",
                "Graph: BFS for shortest-path / levels, DFS for connectivity / cycles",
                "Binary Search on answer — not just on sorted arrays",
                "Monotonic Stack / Sliding Window deque patterns",
            ],
        },
        "recommended_problems": rec_problems,
    }


_WEAK_AREA_RECS: dict[str, tuple[str, str, str]] = {
    # (category, recommendation, priority)
    "approach_quality":       ("Problem Solving",     "Your session flagged approach quality as a gap. Practice stating the brute-force O(n²) solution first, then explicitly narrate the optimization step — 'I can trade space for time here using a hash map.' Interviewers score the transition, not just the final answer.", "high"),
    "complexity_analysis":    ("Complexity Analysis", "Complexity analysis was flagged as weak. Before writing any line of code, write the Big-O (time + space) as a comment. After coding, trace one example to verify the claim. Incorrect complexity claims are an immediate red flag.", "high"),
    "code_quality":           ("Code Quality",        "Code quality signals suggest rushed or unclean submissions. Practice writing clean variable names, avoiding magic numbers, and adding one-line inline comments for non-obvious logic. Reviewers read your code as a proxy for how you write production code.", "high"),
    "communication":          ("Communication",       "Communication was flagged as a weak area. Never work in silence — narrate every decision as you make it: 'I'm using a sliding window here because the constraint is contiguous subarray.' Silent coding gives interviewers nothing to evaluate.", "high"),
    "debugging":              ("Debugging",           "Debugging signals were weak. When a test fails, do not change code randomly. State the failing case, trace through your code manually for that input, identify the exact line where the value diverges, then fix it. Narrate this process out loud.", "high"),
    "edge_cases":             ("Edge Case Handling",  "Edge case handling was flagged. Before submitting, explicitly list: empty input, single element, all-same values, maximum size, and negative numbers if applicable. Then verify each with a 30-second trace. This is a practiced habit, not intuition.", "medium"),
    "dsa_knowledge":          ("DSA Knowledge",       "DSA knowledge gaps were identified. Revisit the flagged topic area with 3–5 focused problems. For each, understand why the data structure or algorithm fits — not just how to code it. Pattern recognition is built through deliberate practice, not volume.", "medium"),
    "adaptability":           ("Adaptability",        "Adaptability signals were low. When an interviewer pushes back on your approach, don't defend — explore. Say 'That's a good point; let me think about whether a different structure changes the complexity.' Flexibility is a senior-engineer signal.", "medium"),
}

_APPROACH_RECS: dict[str, str] = {
    "brute_force":        "You relied on brute-force approaches. Practice the 'optimize after brute' habit: once you have O(n²), ask yourself what additional information you can precompute (prefix sums, sorted order, hash map) to reduce one loop.",
    "no_brute_force":     "Skipping the brute-force step leaves interviewers without a baseline to measure your thinking. Always start with the naive solution even if you already see the optimal — it proves you can reason bottom-up.",
    "hash_map":           "Hash map usage is a strong pattern — keep it. Make sure to explicitly state the key/value mapping and its space cost before using it.",
    "two_pointer":        "Two-pointer approach recognized — solid pattern. Verify your pointer invariant (what condition each pointer maintains) out loud before coding.",
    "sliding_window":     "Sliding window pattern used. Practice stating the window condition explicitly: 'my window is valid when the sum is ≤ k.'",
    "recursion":          "Recursive solutions were used. Always state the base case and recurrence before writing code, and analyze the call-stack depth for stack overflow risk.",
    "dp":                 "Dynamic programming approaches attempted. Define the subproblem, the recurrence, and the base case before touching code. Top-down memoization is easier to derive; bottom-up is cleaner to present.",
}


def _build_personalized_recommendations(
    *,
    known_weak: list[str],
    known_strong: list[str],
    approach_patterns: dict[str, int],
    hint_count: int,
    passed: int,
    total: int,
    contradictions: list[Any],
    exchange_count: int,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    # 1. Weak-area recs (highest signal)
    for w in known_weak[:3]:
        key = w.lower().replace(" ", "_")
        if key in _WEAK_AREA_RECS:
            cat, rec, pri = _WEAK_AREA_RECS[key]
            recs.append({"category": cat, "recommendation": rec, "priority": pri})

    # 2. Approach-pattern recs
    for pattern, count in sorted(approach_patterns.items(), key=lambda x: -x[1]):
        key = pattern.lower().replace(" ", "_")
        if key in _APPROACH_RECS and len(recs) < 5:
            recs.append({
                "category": "Approach Patterns",
                "recommendation": _APPROACH_RECS[key],
                "priority": "medium",
            })
            break

    # 3. Hint dependency
    if hint_count >= 2 and len(recs) < 5:
        recs.append({
            "category": "Independent Problem Solving",
            "recommendation": f"You requested {hint_count} hints this session. Hint dependency is a direct negative signal in interviews. Practice 20-minute timed attempts with no hints — when stuck, speak partial thinking aloud: 'I know I need O(n) but I'm not seeing how to avoid the inner loop.' Demonstrating process is as valuable as finding the answer.",
            "priority": "high",
        })

    # 4. Failed test cases
    if total and passed < total and len(recs) < 5:
        recs.append({
            "category": "Code Correctness",
            "recommendation": f"Your code passed {passed}/{total} test cases. Trace through each failing case manually before resubmitting — identify the exact value that diverges from expected. Failing visible tests is an immediate red flag in any live interview.",
            "priority": "high",
        })

    # 5. Contradictions flagged
    if contradictions and len(recs) < 5:
        topics = list({c.get("topic", "") for c in contradictions if c.get("topic")})[:2]
        topic_str = " and ".join(topics) if topics else "your stated approach"
        recs.append({
            "category": "Consistency",
            "recommendation": f"The session detected contradictions around {topic_str}. Interviewers notice when you state one approach then code another. Before coding, write your invariant as a one-line comment — it anchors your implementation and prevents drift.",
            "priority": "medium",
        })

    # 6. No engagement at all
    if exchange_count == 0 and len(recs) < 5:
        recs.append({
            "category": "Session Engagement",
            "recommendation": "No exchanges were recorded this session. To generate a meaningful evaluation, engage with the problem: ask at least one clarifying question, state your approach, and submit code — even incomplete code provides signal.",
            "priority": "high",
        })

    # 7. Fill with targeted defaults if still empty or too short
    defaults = [
        ("Interview Habits",      "Before writing any code, state your approach, the invariant, and the time/space complexity. Interviewers score this narration as heavily as the code itself.", "high"),
        ("Optimization Strategy", "After reaching a brute-force solution, explicitly ask: 'Can I reduce time complexity by trading space?' Narrate the transition — that moment is what senior interviewers are watching for.", "medium"),
        ("Edge Case Discipline",  "Before submitting, enumerate edge cases out loud: empty input, single element, duplicates, negatives, overflow. Then trace one edge case through your code manually.", "medium"),
    ]
    for cat, rec, pri in defaults:
        if len(recs) >= 5:
            break
        recs.append({"category": cat, "recommendation": rec, "priority": pri})

    return recs[:5]


def _build_question_performance(memory: dict[str, Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = memory.get("turns") or []
    if not turns:
        return []

    # Group by question index (turn field)
    from collections import defaultdict
    groups: dict[int, list[dict]] = defaultdict(list)
    for t in turns:
        q = int(t.get("turn", 1))
        groups[q].append(t)

    result = []
    for q_idx in sorted(groups):
        q_turns = groups[q_idx]
        scores = [t.get("score", {}) for t in q_turns]

        def _avg_field(field: str) -> int:
            vals = [float(s.get(field, 0) or 0) for s in scores if s.get(field)]
            if not vals:
                return 0
            raw = sum(vals) / len(vals)
            return max(0, min(100, round(raw * 100 if raw <= 1.0 else raw)))

        overall = _avg_field("weighted_total")
        approach = _avg_field("approach_quality")
        implementation = _avg_field("implementation")
        communication = _avg_field("communication")
        debugging = _avg_field("debugging")

        # Derive a short verdict label
        if overall >= 75:
            verdict = "Strong"
        elif overall >= 55:
            verdict = "Satisfactory"
        elif overall >= 35:
            verdict = "Needs Work"
        else:
            verdict = "Weak"

        # Collect hints and followups
        hints = [t.get("hint_given") for t in q_turns if t.get("hint_given")]
        followups = [t.get("followup_asked") for t in q_turns if t.get("followup_asked")]

        problem_excerpt = q_turns[0].get("problem_excerpt", "") if q_turns else ""

        result.append({
            "question_index": q_idx,
            "problem_excerpt": problem_excerpt[:200],
            "overall_score": overall,
            "verdict": verdict,
            "turn_count": len(q_turns),
            "hints_used": len(hints),
            "metrics": {
                "approach_quality": approach,
                "implementation": implementation,
                "communication": communication,
                "debugging": debugging,
            },
            "followups_asked": followups[:3],
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# DSA HEURISTIC FALLBACK — always-available evaluation built from session data
# ─────────────────────────────────────────────────────────────────────────────

def _build_heuristic_dsa_evaluation(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Build a structured dsa_evaluation entirely from graph-produced session data.

    Used as a guaranteed fallback when the LLM is unavailable so the rich DSA report
    UI always renders. Scores are derived from TurnScores, SessionScores, test results,
    hint counts, behavioral signals, and known weak/strong areas."""

    dsa = session.get("dsa", {})
    graph_report = dsa.get("report") if isinstance(dsa.get("report"), dict) else {}
    graph_scores = graph_report.get("scores") if isinstance(graph_report.get("scores"), dict) else {}
    radar = graph_report.get("radar_data") if isinstance(graph_report.get("radar_data"), dict) else {}
    sess_scores = dsa.get("session_scores") if isinstance(dsa.get("session_scores"), dict) else {}
    latest_eval = dsa.get("latest_evaluation") if isinstance(dsa.get("latest_evaluation"), dict) else {}
    memory_raw = dsa.get("memory") if isinstance(dsa.get("memory"), dict) else {}

    code_runs = session.get("code_runs", [])
    latest_run = code_runs[-1] if code_runs else {}
    passed = int(latest_run.get("passed_testcases", 0) or 0)
    total = int(latest_run.get("total_testcases", 0) or 0)
    hint_count = int(session.get("hint_count", 0) or 0)
    signals = session.get("behavioral_signals", {})
    known_weak = (dsa.get("known_weak_areas") or [])[:4]
    known_strong = (dsa.get("known_strong_areas") or [])[:4]
    contradictions = (dsa.get("contradiction_history") or [])[-3:]
    confidence_trend = dsa.get("confidence_trend") or []

    # IMPORTANT: do not use `or 50` — a legitimate overall_score of 0 is falsy and
    # would silently become 50, inflating every derived metric. Preserve 0 exactly.
    _raw_overall = base.get("overall_score")
    overall = float(_raw_overall) if _raw_overall is not None else 50.0
    hiring_signal = str(base.get("hiring_signal", "") or "")

    # Engagement gate: a session where the candidate neither spoke meaningfully
    # nor wrote code has no signal to score. Every metric must read 0 — not an
    # estimate derived from a neutral default.
    sess_overall_raw = float(sess_scores.get("overall", 0) or 0)  # 0–1
    exchange_count = int(session.get("exchange_count", 0) or 0)
    engaged = exchange_count > 0 and (overall >= 1.0 or total > 0 or sess_overall_raw > 0.01)

    def _s(v: Any, default: float = 50.0) -> int:
        """Normalise a 0–1 float or 0–100 number to an integer 0–100."""
        try:
            f = float(v)
            return max(0, min(100, round(f * 100 if f <= 1.0 else f)))
        except (TypeError, ValueError):
            return round(default)

    def _pick(*candidates: Any, default: float = 50.0, weak_areas: tuple = ()) -> int:
        """Use first non-zero measured value; otherwise apply weak-area penalty to the default."""
        weak_set_local = {w.lower().replace(" ", "_") for w in known_weak}
        for v in candidates:
            if v is not None:
                try:
                    f = float(v)
                    if f > 0:
                        # Actual measured score — trust it, no extra penalty
                        return max(0, min(100, _s(f, default)))
                except (TypeError, ValueError):
                    pass
        # No measured data — use default with penalty for flagged weak areas
        penalty = min(20, sum(10 for a in weak_areas if a in weak_set_local))
        return max(0, min(100, round(default) - penalty))

    def _label(s: int) -> str:
        if s >= 85: return "Exceptional"
        if s >= 70: return "Strong"
        if s >= 55: return "Competent"
        if s >= 40: return "Developing"
        return "Weak"

    _weak_set = {w.lower().replace(" ", "_") for w in known_weak}

    # Score resolution: full report scores > per-turn session_scores > latest_eval > default±penalty
    ps    = _pick(graph_scores.get("problem_solving"), sess_scores.get("problem_solving"),
                  latest_eval.get("approach_quality_score"), default=overall * 0.9,
                  weak_areas=("approach_quality",))
    cod   = _pick(graph_scores.get("coding"), sess_scores.get("coding"),
                  latest_eval.get("correctness_score"), latest_eval.get("implementation_score"),
                  default=overall * 0.85, weak_areas=("code_quality",))
    comm  = _pick(graph_scores.get("communication"), sess_scores.get("communication"),
                  latest_eval.get("communication_score"), default=overall * 0.85,
                  weak_areas=("communication",))
    dbg   = _pick(graph_scores.get("debugging"), sess_scores.get("debugging"),
                  latest_eval.get("debugging_score"), default=overall * 0.75,
                  weak_areas=("debugging",))
    dsa_k = _pick(graph_scores.get("dsa_knowledge"), sess_scores.get("dsa_knowledge"),
                  default=overall * 0.9, weak_areas=("dsa_knowledge",))

    # Coding Accuracy measures whether code actually WORKED. If no code was executed
    # there is nothing to verify — it must be 0, never the implementation sub-score.
    code_acc   = round(passed / total * 100) if total else 0
    # Hint dependency is a real score only once the candidate has engaged; with zero
    # engagement "100% independent" is misleading, so it's gated below.
    hint_dep   = max(0, 100 - hint_count * 18)
    avg_conf   = _pick(sum(confidence_trend) / len(confidence_trend) if confidence_trend else None,
                       latest_eval.get("confidence_score"), default=overall * 0.85)
    # Composure must not read "exceptional" while the candidate underperformed or quit.
    # Confidence measures absence of nervousness, not skill — cap it near overall so it
    # can't wildly exceed demonstrated ability.
    avg_conf   = min(avg_conf, round(overall) + 20)
    complexity = _pick(radar.get("complexity_accuracy"), radar.get("optimisation_awareness"),
                       latest_eval.get("complexity_score"), default=max(0, ps - 8),
                       weak_areas=("complexity_analysis",))
    adapt      = _pick(radar.get("adaptability"), default=max(0, cod - 6), weak_areas=("adaptability",))
    edge_case  = _pick(radar.get("edge_case_awareness"), latest_eval.get("edge_case_handling_score"),
                       default=max(0, cod - 12), weak_areas=("edge_cases",))

    # No meaningful engagement → every metric is 0. Measured values (when present)
    # already survive above; this only collapses the estimated defaults.
    if not engaged:
        ps = cod = comm = dbg = dsa_k = code_acc = hint_dep = avg_conf = complexity = adapt = edge_case = 0

    # Reconcile strong/weak with the ACTUAL displayed skill scores so the narrative
    # (strengths, weaknesses, learning plan, company fit) can never contradict the
    # numbers shown. Behavioural metrics (confidence, hint dependency) are excluded —
    # they are not skills and inflate easily. >=70 is a real strength, <40 a real gap.
    _skill_scores = {
        "approach_quality":    ps,
        "dsa_knowledge":       dsa_k,
        "complexity_analysis": complexity,
        "code_quality":        code_acc,
        "communication":       comm,
        "debugging":           dbg,
        "edge_cases":          edge_case,
        "adaptability":        adapt,
    }
    if not engaged:
        # No engagement → don't list specific skills as "weak" (we never observed them).
        # The "No Participation" weakness below covers this case honestly.
        known_strong, known_weak = [], []
    else:
        known_strong = [k for k, v in sorted(_skill_scores.items(), key=lambda kv: -kv[1]) if v >= 70]
        known_weak   = [k for k, v in sorted(_skill_scores.items(), key=lambda kv: kv[1]) if v < 40]
    _weak_set = set(known_weak)

    _src = "per-turn session scores" if sess_scores else "heuristic session evaluation"
    _ne = " The candidate did not engage, so no signal could be measured." if not engaged else ""
    core_metrics = [
        {"name": "Problem Solving Ability",    "score": ps,        "label": _label(ps),        "note": (f"Derived from approach quality and solution strategy ({_src}). {'Known strengths: ' + ', '.join(known_strong[:2]) + '.' if known_strong else 'State your approach and brute-force before optimising for a richer signal.'}") if engaged else _ne.strip()},
        {"name": "DSA Knowledge",              "score": dsa_k,     "label": _label(dsa_k),     "note": (f"Based on data structures and patterns demonstrated ({_src}). {'Flagged gaps: ' + ', '.join(known_weak[:2]) + '.' if known_weak else 'No specific gaps flagged by the session graph.'}") if engaged else _ne.strip()},
        {"name": "Optimization Skill",         "score": complexity, "label": _label(complexity), "note": (f"Derived from complexity analysis accuracy across turns ({_src}). {'Weak area detected: complexity_analysis.' if 'complexity_analysis' in _weak_set else 'State time/space complexity before coding each turn.'}") if engaged else _ne.strip()},
        {"name": "Coding Accuracy",            "score": code_acc,  "label": _label(code_acc),  "note": (f"{'Passed ' + str(passed) + '/' + str(total) + ' runnable test cases.' if total else 'No code submission recorded — submit code for a precise correctness score.'}") if engaged else _ne.strip()},
        {"name": "Communication & Explanation","score": comm,      "label": _label(comm),      "note": (f"Based on explanation clarity and reasoning quality across turns ({_src}). {'Weak area detected: communication.' if 'communication' in _weak_set else 'Narrate your invariant and edge cases before submitting.'}") if engaged else _ne.strip()},
        {"name": "Confidence During Interview","score": avg_conf,  "label": _label(avg_conf),  "note": (f"{'Confidence trend observed: ' + str([round(c, 2) for c in confidence_trend[-4:]]) + '.' if confidence_trend else 'Confidence estimated from session turn patterns and speech signals.'}") if engaged else _ne.strip()},
        {"name": "Hint Dependency",            "score": hint_dep,  "label": _label(hint_dep),  "note": (f"Used {hint_count} hint{'s' if hint_count != 1 else ''} during the session. {'Fewer hints = higher independent problem-solving score.' if hint_count else 'No hints requested — full independence demonstrated.'}") if engaged else _ne.strip()},
        {"name": "Adaptability",               "score": adapt,     "label": _label(adapt),     "note": "Based on recovery patterns, approach switches, and response to follow-up probing." if engaged else _ne.strip()},
        {"name": "Complexity Analysis",        "score": complexity, "label": _label(complexity), "note": (f"Reflects time/space complexity claim accuracy ({_src}). {'Complexity analysis flagged as a weak area.' if 'complexity_analysis' in _weak_set else 'Always state Big-O before writing code.'}") if engaged else _ne.strip()},
        {"name": "Edge Case Awareness",        "score": edge_case, "label": _label(edge_case), "note": "Based on boundary case handling in code and discussion of edge conditions." if engaged else _ne.strip()},
    ]

    # Advanced metrics — only company fit
    advanced_metrics = {
        "company_fit": {
            "score": round(overall),
            "fit_signals": known_strong[:3],
            "concern_signals": known_weak[:3] or (["No code submission recorded."] if not total else []),
            "note": f"Company fit estimated from overall session performance ({round(overall)}/100) and identified signals.",
        },
    }

    # Company-tailored
    company = session.get("target_company", "") or "Target Company"
    bar = "Above Bar" if overall >= 82 else ("At Bar" if overall >= 68 else ("Approaching Bar" if overall >= 52 else "Below Bar"))
    # Real follow-up handling, measured per turn against the question asked. Falls back to a
    # ps/comm estimate only when no follow-up answers were recorded.
    _fu_raw = float(sess_scores.get("followup_handling", 0) or 0)  # 0–1
    if not engaged:
        fu_handling, fu_note = 0, "The candidate did not engage, so no follow-up answers could be assessed."
    elif _fu_raw > 0:
        fu_handling = _s(_fu_raw)
        fu_note = "Measured directly from how well each reply answered the specific follow-up question asked, judged against the problem."
    else:
        fu_handling = round((ps + comm) / 2)
        fu_note = "Estimated from problem-solving and communication — no follow-up answers were detected this session."
    company_tailored = {
        "company": company,
        "bar_assessment": bar,
        "optimization_quality": {"score": complexity, "note": f"Optimization signals at {company}: complexity accuracy and approach quality are key signals at this company."},
        "communication_clarity": {"score": comm, "note": f"Communication at {company}: interviewers expect clear narration of approach, invariant, and complexity."},
        "followup_handling":     {"score": fu_handling, "note": fu_note},
        "coding_speed":          {"score": code_acc, "note": f"{'No submission recorded.' if not total else f'{passed}/{total} tests passed — speed and accuracy both matter.'}"},
        "debugging_behavior":    {"score": dbg, "note": "Debugging behavior derived from error recovery signals during the session."},
        "summary": f"Overall performance at {company} maps to a {'strong' if overall >= 75 else ('borderline' if overall >= 58 else 'developing')} candidate profile. {'Focus on optimization depth and edge case reasoning to meet the bar.' if overall < 75 else 'Maintain this level and strengthen the weakest metric.'}",
    }

    # Per-area improvement text so advice is specific (not "practice communication
    # problems: start with the brute-force", which is nonsense).
    _weak_fixes = {
        "approach_quality":    "State the brute-force first, then narrate the optimization step out loud before coding. Interviewers grade the transition, not just the final answer.",
        "dsa_knowledge":       "Drill the core patterns (hash map, two-pointer, stack, BFS/DFS, DP). For each problem, name why the data structure fits before coding.",
        "complexity_analysis": "Write the target time/space Big-O as a comment before coding, then verify it by counting loops/recursion depth afterwards.",
        "code_quality":        "Write and actually RUN a complete solution. Clean names, no dead code, and verify against the examples before saying you're done.",
        "communication":       "Narrate every decision as you make it ('I'm using a stack here because I need LIFO matching'). Silent work leaves the interviewer nothing to score.",
        "debugging":           "When a test fails, trace the failing input by hand to the exact diverging line before changing anything — don't edit randomly.",
        "edge_cases":          "Before submitting, enumerate edge cases out loud (empty, single element, all-same, max size) and verify each.",
        "adaptability":        "When the interviewer pushes back, explore rather than defend — restate the trade-off and adjust your approach.",
    }
    # Weakness analysis derived from the actual low metric scores (consistent with the cards).
    weakness_analysis: list[dict[str, Any]] = [
        {
            "area": w.replace("_", " ").title(),
            "specific_issue": f"Scored {_skill_scores.get(w, 0)}/100 this session — below the bar for this skill.",
            "why_it_matters": "Interviewers probe weak signals repeatedly — an unaddressed gap will recur.",
            "improvement": _weak_fixes.get(w, f"Practice {w.replace('_', ' ')} with deliberate, focused repetition."),
        }
        for w in known_weak[:4]
    ]
    if not weakness_analysis and total and passed < total:
        weakness_analysis = [{
            "area": "Test Case Coverage",
            "specific_issue": f"Code passed {passed}/{total} test cases — some cases still failing.",
            "why_it_matters": "Failing visible tests is an immediate red flag in any coding interview.",
            "improvement": "Trace through each failing case manually. Identify whether it is a logic bug, edge case, or overflow.",
        }]
    if not weakness_analysis and not engaged:
        weakness_analysis = [{
            "area": "No Participation",
            "specific_issue": "The candidate did not speak or write any code during the session, so there is nothing to evaluate.",
            "why_it_matters": "An interview produces a signal only when the candidate engages with the problem.",
            "improvement": "Engage with the problem: ask a clarifying question, state an approach, and write code — even partial code creates evaluable signal.",
        }]

    # Strength recognition derived from the actual high metric scores (consistent with the cards).
    strength_recognition: list[dict[str, Any]] = [
        {
            "strength": s.replace("_", " ").title(),
            "evidence": f"Scored {_skill_scores.get(s, 0)}/100 this session — a demonstrated strength.",
            "interview_value": f"Strong {s.replace('_', ' ')} directly raises the interview signal for hiring managers.",
        }
        for s in known_strong[:3]
    ]
    if total and passed == total:
        strength_recognition.insert(0, {
            "strength": "Code Correctness",
            "evidence": f"Code passed all {total} runnable test cases.",
            "interview_value": "Passing all test cases is the minimum bar for any hire signal at FAANG-style interviews.",
        })
    # Improvement recommendations — built from actual session signals
    improvement_recommendations = _build_personalized_recommendations(
        known_weak=known_weak,
        known_strong=known_strong,
        approach_patterns=dsa.get("approach_patterns") or {},
        hint_count=hint_count,
        passed=passed,
        total=total,
        contradictions=contradictions,
        exchange_count=int(session.get("exchange_count", 0) or 0),
    )

    # Behavior coaching
    behavior_coaching = [
        {
            "observation": "Session ran with basic interaction evidence.",
            "impact": "Full behavioral coaching requires voice interaction, code narration, and question dialogue across multiple turns.",
            "coaching": "In your next session: ask at least 2 clarifying questions before starting, explain your brute-force approach out loud, then narrate every optimization decision. This is what interviewers are actually scoring.",
        }
    ]
    if hint_count > 1:
        behavior_coaching.append({
            "observation": f"Requested {hint_count} hints during the session.",
            "impact": "Hint dependency is a direct negative signal — it tells the interviewer the candidate cannot independently drive to a solution.",
            "coaching": f"Practice timed problems without hints. When stuck, speak your partial thinking aloud ('I know I need O(n) but I'm not seeing how to avoid the inner loop yet'). This demonstrates process even without the answer.",
        })

    # Learning plan — contextual to this candidate's actual session signals
    problem = session.get("problem", {})
    _diff = str(dsa.get("difficulty_level") or problem.get("difficulty", "medium") or "medium").lower()
    if _diff not in {"easy", "medium", "hard"}:
        _diff = "medium"
    learning_plan = _build_learning_plan(
        known_weak=known_weak,
        known_strong=known_strong,
        approach_patterns=dsa.get("approach_patterns") or {},
        topics=problem.get("topics") or [],
        difficulty_level=_diff,
        passed=passed,
        total=total,
        hint_count=hint_count,
        exchange_count=int(session.get("exchange_count", 0) or 0),
    )

    # Benchmarking
    faang_score = round(overall * 0.92)
    level = "L5/Senior" if overall >= 85 else ("L4/Mid" if overall >= 70 else ("L3/Junior" if overall >= 55 else "Below L3"))
    benchmarking = {
        "faang_readiness_score": faang_score,
        "estimated_level": level,
        "comparisons": [
            {"metric": "Problem Solving",     "candidate_score": ps,        "faang_bar": 80, "gap_note": f"{'On target.' if ps >= 80 else f'Gap of {80 - ps} pts — practice structured approach and transition to optimization.'}"},
            {"metric": "Code Correctness",    "candidate_score": code_acc,  "faang_bar": 85, "gap_note": f"{'On target.' if code_acc >= 85 else f'Gap of {85 - code_acc} pts — enumerate edge cases before submitting.'}"},
            {"metric": "Communication",       "candidate_score": comm,      "faang_bar": 75, "gap_note": f"{'On target.' if comm >= 75 else f'Gap of {75 - comm} pts — narrate every decision throughout the session.'}"},
            {"metric": "Complexity Analysis", "candidate_score": complexity, "faang_bar": 80, "gap_note": f"{'On target.' if complexity >= 80 else f'Gap of {80 - complexity} pts — always state and justify O() before coding.'}"},
            {"metric": "Hint Independence",   "candidate_score": hint_dep,  "faang_bar": 85, "gap_note": f"{'On target.' if hint_dep >= 85 else f'Gap of {85 - hint_dep} pts — practice driving to solutions without external prompts.'}"},
        ],
        "overall_readiness_note": f"Current performance places you at approximately {faang_score}/100 FAANG readiness, estimated {level} level. {'No code submission limits accuracy — always submit to generate precise signals.' if not total else f'With {passed}/{total} tests passing, the next focus should be edge case coverage and optimization narration.'}",
    }

    # Final verdict mapping
    _verdict_map = {
        "Strong hire": "Strong Hire",
        "Leaning hire": "Hire",
        "Needs targeted preparation": "Lean Reject",
        "Needs significant preparation": "Reject",
    }
    verdict_signal = _verdict_map.get(hiring_signal, "Lean Reject")
    if overall >= 82: verdict_signal = "Strong Hire"
    elif overall >= 68: verdict_signal = "Hire"
    elif overall >= 52: verdict_signal = "Lean Hire"

    final_verdict = {
        "signal": verdict_signal,
        "confidence_score": min(88, round(overall)),
        "summary": f"Session score: {round(overall)}/100. {'No code submission was recorded, limiting evaluation accuracy.' if not total else f'Code correctness ({passed}/{total} tests) and problem-solving approach were the primary evaluation signals.'} {'Focus areas: ' + ', '.join(known_weak[:2]) + '.' if known_weak else ''}",
        "biggest_strength":   known_strong[0].replace("_", " ").title() if known_strong else ("Code correctness" if total and passed == total else "Session engagement"),
        "biggest_weakness":   known_weak[0].replace("_", " ").title() if known_weak else ("No code submission — correctness cannot be evaluated" if not total else "Edge case coverage and optimization narration"),
        "most_important_next_step": "Submit a code solution in every session — even incomplete code generates evaluation signals that are otherwise missing." if not total else "Before every submission, enumerate edge cases and state the time/space complexity out loud.",
    }

    return {
        "core_metrics": core_metrics,
        "advanced_metrics": advanced_metrics,
        "company_tailored": company_tailored,
        "weakness_analysis": weakness_analysis,
        "improvement_recommendations": improvement_recommendations,
        "behavior_coaching": behavior_coaching,
        "learning_plan": learning_plan,
        "benchmarking": benchmarking,
        "strength_recognition": strength_recognition,
        "final_verdict": final_verdict,
        "question_performance": _build_question_performance(memory_raw),
        "_source": "heuristic",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CS FUNDAMENTALS DEEP EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

_SYS_CS_DEEP_EVAL = """You are a senior software engineer who has conducted 500+ technical interviews. Write a comprehensive CS Fundamentals coaching report based on THIS candidate's actual transcript.

Your job is to identify gaps the candidate doesn't know they have — misconceptions, theory-practice disconnects, shallow memorization, and communication habits that weaken answers. Every observation must be evidenced from the transcript.

BAD: "You need to practice DBMS more."
GOOD: "You correctly listed ACID properties but when asked about dirty reads under READ_COMMITTED isolation, you described REPEATABLE_READ behavior instead — suggesting the property names are memorized but their behavioral differences in transaction scheduling are not internalized."

Return ONLY valid JSON — no markdown, no prose outside JSON:

{
  "topic_profiles": [
    {
      "topic": "<actual topic discussed — only include topics that appear in the transcript>",
      "score": <int 0-100>,
      "depth_level": "Surface|Theoretical|Practical|Expert",
      "highlight": "<1 sentence on their strongest moment in this topic, citing what they said>",
      "gap": "<1 sentence on the clearest gap, citing what they said or failed to say>",
      "misconceptions_detected": ["<precise, evidence-based misconception — not generic>"],
      "coaching": "<1-2 sentences of targeted, specific coaching for this topic>"
    }
  ],
  "core_metrics": [
    {"name": "Conceptual Depth", "score": <int>, "note": "<2 sentences citing this session's evidence>"},
    {"name": "Engineering Intuition", "score": <int>, "note": "<cite whether answers tied to production systems or stayed theoretical>"},
    {"name": "Follow-Up Resilience", "score": <int>, "note": "<cite how they performed when probed deeper>"},
    {"name": "Explanation Clarity", "score": <int>, "note": "<cite structure and clarity of their explanations>"},
    {"name": "Theory-to-Practice Bridge", "score": <int>, "note": "<cite whether they connected concepts to real engineering decisions>"},
    {"name": "Breadth of Knowledge", "score": <int>, "note": "<cite range across topics covered>"},
    {"name": "Systems Thinking", "score": <int>, "note": "<cite cross-concept connections, tradeoff reasoning>"},
    {"name": "Communication Under Pressure", "score": <int>, "note": "<cite how clarity changed during deeper probing>"}
  ],
  "misconceptions": [
    {
      "concept": "<specific concept>",
      "what_was_said": "<exactly what the candidate said or clearly implied>",
      "what_is_correct": "<accurate explanation in 1-2 sentences>",
      "severity": "Critical|Moderate|Minor",
      "interview_impact": "<1 sentence: how this reads to a real interviewer>"
    }
  ],
  "follow_up_analysis": {
    "score": <int 0-100>,
    "pattern": "Consistently_Strong|Improved_Under_Pressure|Degraded_Under_Pressure|Collapsed",
    "observations": ["<specific follow-up exchange observation, citing the exchange>"],
    "coaching": "<1 actionable sentence on follow-up handling>"
  },
  "engineering_intuition": {
    "score": <int 0-100>,
    "balance": "Heavy_Theory|Theory_Leaning|Balanced|Practice_Leaning|Heavy_Practice",
    "strong_practical_areas": ["<specific topic/concept where they showed engineering intuition>"],
    "theory_only_areas": ["<specific topic where answer was definition-only with no practical reasoning>"],
    "coaching": "<1-2 sentences on closing the theory-practice gap for THIS candidate>"
  },
  "explanation_coaching": [
    {
      "topic": "<topic>",
      "pattern_observed": "<what their explanation pattern looked like — cite the specific behavior>",
      "coaching": "<specific, actionable advice for improving explanations in this topic>"
    }
  ],
  "improvement_recommendations": [
    {
      "category": "Conceptual Gaps|Engineering Intuition|Explanation Technique|Follow-Up Handling|Systems Thinking|Breadth",
      "recommendation": "<specific, actionable — referencing this candidate's actual gaps>",
      "priority": "high|medium|low"
    }
  ],
  "benchmarking": {
    "readiness_score": <int 0-100>,
    "level_estimate": "Strong Intern|New Grad|Junior Engineer|Mid-Level Engineer|Senior Engineer",
    "comparisons": [
      {"topic": "<specific topic or skill>", "candidate_score": <int>, "expectation": <int>, "gap_note": "<1 sentence>"}
    ],
    "overall_note": "<2 sentences comparing to FAANG-style CS fundamentals bar>"
  },
  "final_verdict": {
    "signal": "Strong Hire|Hire|Lean Hire|Lean Reject|Reject",
    "confidence_score": <int 0-100>,
    "summary": "<2-3 sentences on this specific candidate's CS fundamentals performance>",
    "biggest_strength": "<1 sentence>",
    "biggest_gap": "<1 sentence>",
    "most_important_next_step": "<1 concrete actionable sentence>"
  }
}

Constraints:
- topic_profiles: only topics actually discussed in the transcript — 2 to 6 items
- misconceptions: only genuine misconceptions evidenced in this transcript — 0 to 4 items; never invent
- core_metrics: exactly 8 items in the listed order
- explanation_coaching: 2-4 items based on observable explanation patterns
- improvement_recommendations: 4-6 items
- benchmarking comparisons: 3-5 items
- All scores 0-100
- Theoretical/memorized answers score lower on Engineering Intuition than equivalent practical reasoning
- Score conservatively when transcript evidence is thin — note it explicitly"""


def _build_cs_deep_context(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    cs = session.get("cs_fundamentals", {})
    section = base.get("round_breakdown", {})
    questions = cs.get("questions_asked", [])
    question_summary = [
        {
            "topic": q.get("topic", ""),
            "question_type": q.get("question_type", ""),
            "answer_excerpt": str(q.get("answer_excerpt", ""))[:300],
            "scores": q.get("scores", {}),
            "flags": (q.get("flags") or [])[:4],
        }
        for q in questions[-8:]
    ]
    return {
        "company": session.get("target_company", "Unknown"),
        "role": session.get("job_role", "Software Engineer"),
        "experience_level": session.get("experience_level", "mid"),
        "topics_covered": (cs.get("topics_covered") or [])[:8],
        "strong_topics": (cs.get("strong_topics") or [])[:5],
        "weak_topics": (cs.get("weak_topics") or [])[:5],
        "scratchpad_observations": (cs.get("scratchpad_history") or [])[-4:],
        "questions_summary": question_summary,
        "heuristic_signals": {
            "strengths": (section.get("strengths") or [])[:4],
            "weak_areas": (section.get("weak_areas") or [])[:4],
            "latest_flags": (cs.get("latest_flags") or [])[:5],
        },
        "transcript": _build_transcript(session, max_turns=25, per_msg=500),
    }


async def _run_cs_deep_eval(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    ctx = _build_cs_deep_context(session, base)
    if not ctx.get("transcript"):
        return None
    raw = await generate_text(
        _SYS_CS_DEEP_EVAL,
        json.dumps(ctx, ensure_ascii=False, default=str),
        temperature=0.25,
        max_tokens=2500,
    )
    if not raw:
        return None
    try:
        data = json.loads(extract_json_object(clean_json_response(raw)))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ─────────────────────────────────────────────────────────────────────────────
# PROJECT + BEHAVIORAL DEEP EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

_SYS_PB_DEEP_EVAL = """You are a senior engineering manager and interview coach evaluating a Project + Behavioral interview. Your job is to see past performance and find the real candidate.

For projects: determine if they truly built what they claim, understand the system deeply, or are reciting a rehearsed pitch with surface knowledge.
For behavioral: determine if stories are authentic or scripted, if leadership is genuine or claimed, if engineering maturity is real or just vocabulary.

BAD: "Your behavioral answers lacked specificity."
GOOD: "In the conflict resolution story, you described what happened and what you said, but skipped your decision-making process entirely — that's the part interviewers actually evaluate. You went straight from tension to outcome without ever explaining your reasoning, which reads as a rehearsed story rather than a genuine reflection."

Return ONLY valid JSON — no markdown, no prose outside JSON:

{
  "project_evaluation": {
    "ownership_score": <int 0-100>,
    "ownership_analysis": {
      "strong_signals": ["<specific moment from transcript showing genuine ownership>"],
      "weak_signals": ["<specific moment suggesting surface knowledge or rehearsed pitch>"],
      "overall_note": "<2 sentences on genuine vs presented ownership>"
    },
    "architecture_understanding": {
      "score": <int>,
      "depth": "Feature_Knowledge|Structural|Design_Aware|Systems_Expert",
      "strong_areas": ["<specific area they understood architecturally>"],
      "weak_areas": ["<specific area where understanding broke down when probed>"],
      "note": "<2 sentences>"
    },
    "engineering_maturity": {
      "score": <int>,
      "production_thinking": <int 0-100>,
      "scalability_awareness": <int 0-100>,
      "failure_handling": <int 0-100>,
      "monitoring_observability": <int 0-100>,
      "optimization_thinking": <int 0-100>,
      "note": "<2 sentences citing specific evidence from this session>"
    },
    "authenticity": {
      "score": <int>,
      "overclaiming_detected": <bool>,
      "buzzword_without_depth": ["<specific instance where a buzzword or technology lacked substance when probed>"],
      "genuine_technical_moments": ["<specific moment of real technical depth that couldn't be rehearsed>"],
      "note": "<2 sentences on authenticity assessment>"
    },
    "technical_depth_topics": [
      {"topic": "<specific technology or design decision from their project>", "depth_score": <int>, "note": "<1 sentence on depth shown>"}
    ]
  },
  "behavioral_evaluation": {
    "star_analysis": {
      "overall_score": <int>,
      "situation": {"score": <int>, "note": "<1 sentence — clear context or vague setup?>"},
      "task": {"score": <int>, "note": "<1 sentence — was their role and personal ownership clear?>"},
      "action": {"score": <int>, "note": "<1 sentence — did they say what THEY specifically did vs 'we'?>"},
      "result": {"score": <int>, "note": "<1 sentence — was impact quantified and attributed clearly?>"},
      "coaching": "<2 sentences on overall STAR quality and biggest improvement area>"
    },
    "leadership_ownership": {
      "score": <int>,
      "initiative_signals": ["<specific moment showing initiative>"],
      "accountability_signals": ["<specific moment of clear personal accountability>"],
      "pattern": "Strong_Ownership|Shared_Credit|Passive|Avoidant",
      "note": "<2 sentences>"
    },
    "conflict_resolution": {
      "score": <int>,
      "maturity_level": "Avoidant|Diplomatic|Assertive|Strategic",
      "note": "<2 sentences on how they handled conflict scenarios, citing specifics from transcript>"
    },
    "decision_quality": {
      "score": <int>,
      "reasoning_quality": "Strong|Adequate|Weak|Missing",
      "ambiguity_handling": <int 0-100>,
      "note": "<2 sentences on decision reasoning depth>"
    },
    "emotional_intelligence": {
      "score": <int>,
      "note": "<2 sentences on empathy, self-awareness, and interpersonal signals from this session>"
    },
    "authenticity": {
      "score": <int>,
      "scripted_indicators": ["<specific signal of a rehearsed response — cite what they said>"],
      "authentic_moments": ["<specific moment of genuine insight that couldn't be rehearsed>"],
      "generic_leadership_detected": <bool>,
      "note": "<2 sentences on behavioral authenticity>"
    }
  },
  "communication_profile": {
    "score": <int>,
    "storytelling_quality": <int>,
    "clarity_under_probing": <int>,
    "confidence_score": <int>,
    "structure_score": <int>,
    "key_observation": "<2 sentences on their overall communication pattern in this session>"
  },
  "coaching": {
    "project_coaching": ["<2-4 specific, actionable project explanation improvements>"],
    "behavioral_coaching": ["<2-4 specific behavioral story improvements referencing this session>"],
    "communication_coaching": ["<1-3 specific communication improvements>"]
  },
  "improvement_recommendations": [
    {
      "category": "Project Depth|Ownership Narrative|STAR Structure|Leadership Storytelling|Authenticity|Engineering Maturity|Communication",
      "recommendation": "<specific and actionable, referencing this candidate's actual interview>",
      "priority": "high|medium|low"
    }
  ],
  "benchmarking": {
    "readiness_score": <int 0-100>,
    "level_estimate": "New Grad|L3/Junior|L4/Mid|L5/Senior",
    "comparisons": [
      {"dimension": "<e.g. 'Project ownership depth'>", "candidate_score": <int>, "expectation": <int>, "gap_note": "<1 sentence>"}
    ],
    "note": "<2 sentences comparing to FAANG behavioral and project interview bar>"
  },
  "final_verdict": {
    "signal": "Strong Hire|Hire|Lean Hire|Lean Reject|Reject",
    "confidence_score": <int 0-100>,
    "summary": "<2-3 sentences on this specific candidate's project + behavioral performance>",
    "biggest_strength": "<1 sentence>",
    "biggest_gap": "<1 sentence>",
    "most_important_next_step": "<1 concrete actionable sentence>"
  }
}

Constraints:
- technical_depth_topics: only technologies/decisions actually discussed — 2 to 5 items
- scripted_indicators and authentic_moments: cite specific phrases or moments from transcript
- improvement_recommendations: 4-6 items
- benchmarking comparisons: 3-5 items
- All scores 0-100
- star_analysis applies across all behavioral turns, not a single story
- Generic observations that could describe any candidate are unacceptable
- Score conservatively when session evidence is thin"""


def _build_pb_deep_context(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    pb = session.get("project_behavioral", {})
    section = base.get("round_breakdown", {})
    turns = pb.get("turns", [])
    turn_summary = [
        {
            "phase": t.get("phase", ""),
            "answer_excerpt": str(t.get("answer_excerpt", ""))[:300],
            "scores": t.get("scores", {}),
            "flags": (t.get("flags") or [])[:4],
            "star_components": t.get("star_components", {}),
            "exaggeration_risk": t.get("exaggeration_risk", False),
        }
        for t in turns[-8:]
    ]
    return {
        "company": session.get("target_company", "Unknown"),
        "role": session.get("job_role", "Software Engineer"),
        "experience_level": session.get("experience_level", "mid"),
        "company_style": pb.get("company_style", ""),
        "resume_project": (pb.get("resume_focus") or {}).get("selected_project", ""),
        "jd_skills": (pb.get("jd_signals") or {}).get("skills", [])[:6],
        "star_breakdown": section.get("star_breakdown", {}),
        "star_completeness_pct": section.get("star_completeness_pct", 0),
        "exaggeration_turns": section.get("exaggeration_turns", 0),
        "contradiction_history": (pb.get("contradiction_history") or [])[-3:],
        "turns_summary": turn_summary,
        "heuristic_signals": {
            "strengths": (section.get("strengths") or [])[:4],
            "weak_areas": (section.get("weak_areas") or [])[:4],
            "latest_flags": (pb.get("latest_flags") or [])[:5],
        },
        "transcript": _build_transcript(session, max_turns=25, per_msg=500),
    }


async def _run_pb_deep_eval(session: dict[str, Any], base: dict[str, Any]) -> dict[str, Any] | None:
    ctx = _build_pb_deep_context(session, base)
    if not ctx.get("transcript"):
        return None
    raw = await generate_text(
        _SYS_PB_DEEP_EVAL,
        json.dumps(ctx, ensure_ascii=False, default=str),
        temperature=0.25,
        max_tokens=2500,
    )
    if not raw:
        return None
    try:
        data = json.loads(extract_json_object(clean_json_response(raw)))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
