from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.orchestration.project_behavioral_llm import evaluate_project_behavioral_with_llm
from app.services.interview_data_service import get_project_behavioral_config


class ProjectBehavioralState(TypedDict, total=False):
    session: dict[str, Any]
    user_text: str
    company_profile: dict[str, Any]
    jd_signals: dict[str, Any]
    resume_signals: dict[str, Any]
    answer_evaluation: dict[str, Any]
    strategy: dict[str, Any]
    ai_text: str
    phase: str
    project_behavioral: dict[str, Any]
    weak_areas: list[str]


def run_project_behavioral_turn(session: dict[str, Any], user_text: str) -> dict[str, Any]:
    result = PROJECT_BEHAVIORAL_GRAPH.invoke({"session": session, "user_text": user_text})
    session["phase"] = result.get("phase", session.get("phase", "projects"))
    session["project_behavioral"] = result.get("project_behavioral", session.get("project_behavioral", {}))
    for area in result.get("weak_areas", []):
        if area not in session["weak_areas"]:
            session["weak_areas"].append(area)
    return result


def _context_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    profile = get_project_behavioral_config(session.get("target_company", ""))
    jd_signals = _extract_jd_signals(session.get("job_description", ""))
    selected_project = _detect_candidate_project_choice(
        state.get("user_text", ""),
        session.get("resume_data", {}),
        session.get("project_behavioral", {}),
    )
    resume_signals = _extract_resume_signals(session.get("resume_data", {}), jd_signals, selected_project)
    return {**state, "company_profile": profile, "jd_signals": jd_signals, "resume_signals": resume_signals}


def _evaluation_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state.get("session", {})
    phase = _phase_for_turn(int(session.get("question_count", 0) or 0))
    evaluation = evaluate_project_behavioral_with_llm(
        session=session,
        memory=session.get("project_behavioral", {}),
        company_profile=state.get("company_profile", {}),
        jd_signals=state.get("jd_signals", {}),
        resume_signals=state.get("resume_signals", {}),
        user_text=state.get("user_text", ""),
        phase=phase,
    ) or _llm_unavailable_evaluation(state.get("resume_signals", {}))
    return {**state, "answer_evaluation": evaluation}


def _strategy_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    evaluation = state.get("answer_evaluation", {})
    phase = _phase_for_turn(int(session.get("question_count", 0) or 0))
    return {
        **state,
        "phase": phase,
        "strategy": {
            "turn": int(session.get("question_count", 0) or 0),
            "phase": phase,
            "goal": evaluation.get("next_question_reason") or "continue a natural project and behavioural interview",
            "company_style": state.get("company_profile", {}).get("interview_style", "balanced"),
            "followup_intent": evaluation.get("followup_intent", "move_forward"),
        },
    }


def _response_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    evaluation = state.get("answer_evaluation", {})
    return {**state, "ai_text": evaluation.get("next_question") or _llm_unavailable_message()}


def _memory_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    previous = session.get("project_behavioral", {})
    evaluation = state.get("answer_evaluation", {})
    strategy = state.get("strategy", {})
    profile = state.get("company_profile", {})
    resume_signals = state.get("resume_signals", {})

    turns = [
        *previous.get("turns", []),
        {
            "phase": strategy.get("phase", state.get("phase", "projects")),
            "answer_text": _clip(state.get("user_text", ""), 3000),
            "answer_excerpt": _clip(state.get("user_text", ""), 900),
            "scores": evaluation.get("scores", {}),
            "evaluation_source": evaluation.get("evaluation_source", "llm_unavailable"),
            "flags": evaluation.get("flags", []),
            "evidence": evaluation.get("evidence", []),
            "strengths": evaluation.get("strengths", []),
            "weak_areas": evaluation.get("weak_areas", []),
            "star_components": evaluation.get("star_components", {}),
            "project_discussed": evaluation.get("project_discussed", False),
            "followup_intent": strategy.get("followup_intent", ""),
            "next_question": state.get("ai_text", ""),
            "next_question_reason": evaluation.get("next_question_reason", ""),
        },
    ][-20:]

    project_behavioral = {
        **previous,
        "company_profile": profile.get("company", session.get("target_company") or "General Product Engineering"),
        "company_style": profile.get("interview_style", "balanced"),
        "round_config": {
            "project_depth": profile.get("project_depth"),
            "behavioral_depth": profile.get("behavioral_depth"),
            "technical_depth": profile.get("technical_depth"),
            "pressure_level": profile.get("pressure_level"),
            "focus_areas": profile.get("focus_areas", []),
            "evaluation_signals": profile.get("evaluation_signals", []),
            "red_flags": profile.get("red_flags", []),
        },
        "jd_signals": state.get("jd_signals", {}),
        "resume_focus": resume_signals,
        "candidate_selected_project": _selected_project_memory(resume_signals, previous),
        "pending_project_switch": False,
        "turns": turns,
        "latest_scores": evaluation.get("scores", {}),
        "latest_flags": evaluation.get("flags", []),
        "latest_star": evaluation.get("star_components", {}),
        "latest_context_alignment": evaluation.get("context_alignment", {}),
        "exaggeration_risk": evaluation.get("exaggeration_risk", False),
        "accountability_gap": evaluation.get("accountability_gap", False),
        "current_goal": strategy.get("goal", ""),
    }
    return {**state, "project_behavioral": project_behavioral, "weak_areas": _weak_areas_from_eval(evaluation)}


def build_project_behavioral_graph():
    graph = StateGraph(ProjectBehavioralState)
    graph.add_node("load_context", _context_node)
    graph.add_node("evaluate_answer", _evaluation_node)
    graph.add_node("choose_strategy", _strategy_node)
    graph.add_node("generate_question", _response_node)
    graph.add_node("update_memory", _memory_node)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "evaluate_answer")
    graph.add_edge("evaluate_answer", "choose_strategy")
    graph.add_edge("choose_strategy", "generate_question")
    graph.add_edge("generate_question", "update_memory")
    graph.add_edge("update_memory", END)
    return graph.compile()


PROJECT_BEHAVIORAL_GRAPH = build_project_behavioral_graph()


def _phase_for_turn(turn: int) -> str:
    if turn <= 1:
        return "resume_walkthrough"
    if turn <= 3:
        return "project_deep_dive"
    if turn <= 5:
        return "technical_tradeoffs"
    if turn <= 8:
        return "behavioural_star"
    if turn <= 10:
        return "pressure_validation"
    return "closing"


def _llm_unavailable_evaluation(resume_signals: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_source": "llm_unavailable",
        "scores": {},
        "flags": ["LLM response was unavailable; no local interview fallback was used."],
        "evidence": [],
        "strengths": [],
        "weak_areas": [],
        "technical_terms": [],
        "has_metric": False,
        "context_alignment": {},
        "project_discussed": False,
        "jd_skill_hits": [],
        "resume_skill_hits": [],
        "company_focus_hits": [],
        "role_alignment_hits": [],
        "star_components": {},
        "exaggeration_risk": False,
        "accountability_gap": False,
        "followup_intent": "llm_unavailable",
        "next_question": _llm_unavailable_message(),
        "next_question_reason": "LLM unavailable.",
        "active_project": resume_signals.get("selected_project", ""),
    }


def _llm_unavailable_message() -> str:
    return "The AI model is unavailable for this turn, so I will not continue with a scripted local interview response. Please retry once the LLM connection is healthy."


def _extract_jd_signals(job_description: str) -> dict[str, Any]:
    text = job_description or ""
    skills = _keyword_hits(text, [
        "react", "fastapi", "python", "java", "c++", "sql", "postgres", "redis", "docker",
        "aws", "gcp", "azure", "api", "microservices", "machine learning", "llm", "testing",
        "security", "scalability", "distributed systems",
    ])
    responsibilities = _keyword_hits(text, [
        "design", "build", "deploy", "optimize", "collaborate", "debug", "own", "lead",
        "mentor", "monitor", "scale", "automate",
    ])
    return {
        "skills": skills[:10],
        "responsibilities": responsibilities[:8],
        "seniority": "senior" if re.search(r"\bsenior|lead|mentor|architect\b", text, re.I) else "early-career",
        "has_jd": bool(text.strip()),
        "summary": _clip(re.sub(r"\s+", " ", text).strip(), 420),
    }


def _extract_resume_signals(
    resume_data: dict[str, Any],
    jd_signals: dict[str, Any],
    selected_project_choice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projects = resume_data.get("projects", []) if isinstance(resume_data, dict) else []
    skills = resume_data.get("skills", []) if isinstance(resume_data, dict) else []
    selected_project = _project_from_choice(selected_project_choice, projects)
    project_text = _project_summary(selected_project) if selected_project else ""
    jd_skills = {skill.lower() for skill in jd_signals.get("skills", [])}
    selected_source = (selected_project_choice or {}).get("source") or ("resume" if selected_project else "fallback")
    selected_name = selected_project.get("name") or "your strongest resume project"
    return {
        "selected_project": selected_name,
        "selected_project_source": selected_source,
        "candidate_selected_project": selected_name if selected_source in {"candidate", "resume_match", "auto_selected"} else "",
        "project_summary": _clip(project_text, 420),
        "resume_skill_matches": [skill for skill in skills if skill.lower() in jd_skills][:10],
        "project_count": max(len(projects), 1 if selected_project else 0),
        "skill_count": len(skills),
    }


def _detect_candidate_project_choice(
    user_text: str,
    resume_data: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, Any] | None:
    text = _clip(user_text, 700)
    projects = resume_data.get("projects", []) if isinstance(resume_data, dict) else []
    previous_choice = previous.get("candidate_selected_project") if isinstance(previous, dict) else None

    if _candidate_asks_interviewer_to_choose_project(text):
        chosen_project = _choose_alternative_resume_project(text, projects, previous_choice)
        if chosen_project:
            return {"name": chosen_project.get("name") or "selected resume project", "source": "auto_selected", "resume_project": chosen_project}

    explicit_name = _extract_explicit_project_name(text)
    if explicit_name:
        matched_project = _best_matching_resume_project(explicit_name, projects)
        if matched_project:
            return {"name": matched_project.get("name") or explicit_name, "source": "resume_match", "resume_project": matched_project}
        return {"name": explicit_name, "source": "candidate", "summary": _clip(text, 420)}

    if isinstance(previous_choice, dict) and previous_choice.get("name"):
        return {
            "name": previous_choice.get("name"),
            "source": previous_choice.get("source", "candidate"),
            "summary": previous_choice.get("summary", ""),
        }

    matched_project = _best_matching_resume_project(text, projects, min_score=3)
    if matched_project:
        return {"name": matched_project.get("name") or "selected resume project", "source": "resume_match", "resume_project": matched_project}
    return None


def _extract_explicit_project_name(user_text: str) -> str:
    text = re.sub(r"\s+", " ", user_text or "").strip()
    if not text:
        return ""
    patterns = [
        r"\b(?:i(?:'ll| will| would like to| want to| am going to)?|let me|i can)\s+(?:be\s+)?(?:talk(?:ing)?\s+about|explain(?:ing)?|walk(?:ing)?\s+through|discuss(?:ing)?|choose|pick|present(?:ing)?)\s+(?:my\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,110})",
        r"\b(?:my\s+)?(?:strongest|main|best)\s+project\s+(?:is|was|would\s+be|will\s+be)\s+(?:an?\s+|the\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,90})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_project_choice(match.group("name"))
    return ""


def _project_from_choice(choice: dict[str, Any] | None, projects: list[dict[str, Any]]) -> dict[str, Any]:
    if choice:
        resume_project = choice.get("resume_project")
        if isinstance(resume_project, dict) and resume_project:
            return resume_project
        name = _clean_project_choice(str(choice.get("name") or ""))
        if name:
            return _best_matching_resume_project(name, projects) or {"name": name, "description": choice.get("summary") or name}
    return projects[0] if projects else {}


def _selected_project_memory(resume_signals: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    selected = _clean_project_choice(resume_signals.get("candidate_selected_project") or "")
    if not selected:
        prior = previous.get("candidate_selected_project") if isinstance(previous, dict) else None
        return prior if isinstance(prior, dict) else {}
    return {
        "name": selected,
        "source": resume_signals.get("selected_project_source") or "candidate",
        "summary": resume_signals.get("project_summary") or selected,
    }


def _best_matching_resume_project(text: str, projects: list[dict[str, Any]], min_score: int = 2) -> dict[str, Any] | None:
    if not text or not projects:
        return None
    lower = text.lower()
    text_tokens = {token for token in re.findall(r"[a-zA-Z0-9+.#-]+", lower) if len(token) >= 3}
    best_project = None
    best_score = 0
    for project in projects:
        project_text = _project_summary(project).lower()
        name = str(project.get("name") or "").lower()
        if name and (name in lower or lower in name):
            return project
        project_tokens = {token for token in re.findall(r"[a-zA-Z0-9+.#-]+", project_text) if len(token) >= 3}
        score = len(text_tokens & project_tokens)
        if score > best_score:
            best_score = score
            best_project = project
    return best_project if best_score >= min_score else None


def _candidate_asks_interviewer_to_choose_project(user_text: str) -> bool:
    lower = (user_text or "").lower()
    return bool(lower and re.search(
        r"\b(?:you|interviewer|ai)\s+(?:can\s+|could\s+|should\s+)?(?:choose|pick|select)\b.*\b(?:project|resume)\b"
        r"|\b(?:choose|pick|select)\s+(?:any\s+)?(?:random\s+|other\s+|different\s+|another\s+)?project\b.*\b(?:resume|for\s+me)\b"
        r"|\bany\s+(?:random\s+|other\s+|different\s+|another\s+)?project\s+from\s+my\s+resume\b",
        lower,
    ))


def _choose_alternative_resume_project(user_text: str, projects: list[dict[str, Any]], previous_choice: Any) -> dict[str, Any] | None:
    if not projects:
        return None
    excluded_names = _excluded_project_names(user_text, previous_choice)
    for project in projects:
        searchable = f"{project.get('name', '')} {_project_summary(project)}".lower()
        if not any(excluded and excluded in searchable for excluded in excluded_names):
            return project
    return projects[0]


def _excluded_project_names(user_text: str, previous_choice: Any) -> list[str]:
    excluded: list[str] = []
    lower = (user_text or "").lower()
    for pattern in (
        r"\b(?:except|besides|apart\s+from|other\s+than)\s+(?:the\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,90})",
        r"\b(?:not|don't|do\s+not)\s+(?:the\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,90})",
    ):
        for match in re.finditer(pattern, lower, re.I):
            name = _clean_project_choice(match.group("name"))
            if name:
                excluded.append(name.lower())
    if isinstance(previous_choice, dict) and previous_choice.get("name"):
        excluded.append(_clean_project_choice(str(previous_choice["name"])).lower())
    return [name for name in dict.fromkeys(excluded) if name]


def _project_summary(project: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in project.values():
        parts.extend(str(item) for item in value) if isinstance(value, list) else parts.append(str(value))
    return " ".join(parts)


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = (text or "").lower()
    return [keyword for keyword in keywords if keyword.lower() in lower]


def _weak_areas_from_eval(evaluation: dict[str, Any]) -> list[str]:
    return [*evaluation.get("flags", []), *evaluation.get("weak_areas", [])][:3]


def _clean_project_choice(value: str) -> str:
    value = re.split(r"[.!?;]|\s+(?:because|where|which|that|and then|so then)\b", value or "", maxsplit=1, flags=re.I)[0]
    value = re.sub(r"^(?:my|the|a|an|on|about|for)\s+", "", value.strip(), flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" ,:-")
    return _clip(value, 90)


def _clip(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()
