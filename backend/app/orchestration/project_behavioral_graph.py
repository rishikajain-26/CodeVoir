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
    """Run one Project + Behavioural interview turn through a LangGraph workflow."""
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
    return {
        **state,
        "company_profile": profile,
        "jd_signals": jd_signals,
        "resume_signals": resume_signals,
    }


def _evaluation_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state.get("session", {})
    turn = int(session.get("question_count", 0) or 0)
    phase = _phase_for_turn(turn)
    if _is_project_switch_request(state.get("user_text", "")):
        evaluation = _project_switch_evaluation(state.get("resume_signals", {}))
        return {**state, "answer_evaluation": evaluation}
    if _is_greeting_only(state.get("user_text", "")):
        evaluation = _greeting_evaluation(state.get("resume_signals", {}))
        return {**state, "answer_evaluation": evaluation}

    llm_evaluation = evaluate_project_behavioral_with_llm(
        session=session,
        memory=session.get("project_behavioral", {}),
        company_profile=state.get("company_profile", {}),
        jd_signals=state.get("jd_signals", {}),
        resume_signals=state.get("resume_signals", {}),
        user_text=state.get("user_text", ""),
        phase=phase,
    )
    evaluation = llm_evaluation or _evaluate_answer(
        state.get("user_text", ""),
        state.get("strategy", {}),
        state.get("resume_signals", {}),
        state.get("jd_signals", {}),
        state.get("company_profile", {}),
        state.get("session", {}),
    )
    evaluation = _ground_project_behavioral_score(
        evaluation,
        state.get("user_text", ""),
        state.get("session", {}),
        phase,
    )
    return {**state, "answer_evaluation": evaluation}


def _strategy_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    turn = int(session.get("question_count", 0) or 0)
    profile = state.get("company_profile", {})
    evaluation = state.get("answer_evaluation", {})

    phase = _phase_for_turn(turn)
    goal = _goal_for_phase(phase)

    if evaluation.get("flags") and phase not in {"closing", "pressure_validation"}:
        goal = f"{goal}; repair weak evidence from the previous answer"

    followup_intent = evaluation.get("followup_intent") or _select_followup_intent(
        evaluation,
        session.get("project_behavioral", {}),
    )
    strategy = {
        "turn": turn,
        "phase": phase,
        "goal": goal,
        "company_style": profile.get("interview_style", "balanced"),
        "theme": _pick_theme(profile.get("focus_areas", []), turn),
        "followup_intent": followup_intent,
    }
    return {**state, "strategy": strategy, "phase": phase}


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


def _goal_for_phase(phase: str) -> str:
    goals = {
        "resume_walkthrough": "connect resume, job description, and strongest project",
        "project_deep_dive": "validate project ownership, architecture, and tradeoffs",
        "technical_tradeoffs": "probe scaling, reliability, failure modes, and redesign thinking",
        "behavioural_star": "collect STAR evidence for collaboration, conflict, pressure, or ambiguity",
        "pressure_validation": "stress-test weak areas and company-specific expectations",
        "closing": "wrap up and prepare feedback",
    }
    return goals.get(phase, goals["project_deep_dive"])


_BEHAVIORAL_SYSTEM_PROMPT = """You are a sharp, realistic Project + Behavioural interviewer. Your job is to extract evidence, not make the candidate feel good.

Response rules:
1. React to what the candidate just said in ONE sentence (acknowledge, correct, or push back).
2. Ask exactly ONE focused follow-up question — never two.
3. If STAR components are missing, name which one is absent and ask for it directly.
4. If exaggeration_risk is true, challenge the claim: "You said X — can you give me a specific number or a concrete example?"
5. If accountability_gap is true, push: "You said 'we' a lot — what did YOU personally own in that?"
6. In pressure_validation phase: be direct, do not soften pushback.
7. In behavioural_star phase: require all 4 STAR components before moving on.

Anti-patterns (never do these):
- Do not summarize what the candidate said.
- Do not give encouragement like "Great answer!" or "That's impressive."
- Do not ask multiple questions.
- Do not answer on behalf of the candidate.

Plain text only. Maximum 3 sentences."""


def _response_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    fallback = _fallback_question(state)
    evaluation = state.get("answer_evaluation", {})
    ai_text = evaluation.get("next_question") or fallback
    return {**state, "ai_text": ai_text}


def _detect_claim_contradiction(previous_turns: list[dict], current_text: str) -> dict | None:
    """Heuristic contradiction detection for behavioral answers."""
    if not previous_turns or not current_text:
        return None
    current_lower = current_text.lower()
    for past_turn in reversed(previous_turns[-4:]):
        past_excerpt = (past_turn.get("answer_excerpt") or "").lower()
        # Detect metric flip: claimed 50% before, now claiming 20%
        past_numbers = re.findall(r"\b(\d+)\s*(%|x|users?|ms|seconds?|engineers?)", past_excerpt)
        curr_numbers = re.findall(r"\b(\d+)\s*(%|x|users?|ms|seconds?|engineers?)", current_lower)
        if past_numbers and curr_numbers:
            for pn, pu in past_numbers:
                for cn, cu in curr_numbers:
                    if pu == cu and abs(int(pn) - int(cn)) / max(int(pn), 1) > 0.5:
                        return {
                            "claim_before": f"{pn}{pu}",
                            "claim_now": f"{cn}{cu}",
                            "topic": "metrics",
                        }
    return None


def _memory_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    previous = session.get("project_behavioral", {})
    evaluation = state.get("answer_evaluation", {})
    strategy = state.get("strategy", {})
    profile = state.get("company_profile", {})
    resume_signals = state.get("resume_signals", {})
    is_switch_request = evaluation.get("followup_intent") == "switch_project"

    turns = previous.get("turns", [])
    contradiction = None
    if state.get("user_text"):
        contradiction = _detect_claim_contradiction(turns, state.get("user_text", ""))
        turns = [
            *turns,
            {
                "phase": strategy.get("phase", state.get("phase", "projects")),
                "answer_text": _clip(state.get("user_text", ""), 3000),
                "answer_excerpt": _clip(state.get("user_text", ""), 900),
                "scores": evaluation.get("scores", {}),
                "evaluation_source": evaluation.get("evaluation_source", "local_fallback"),
                "flags": evaluation.get("flags", []),
                "evidence": evaluation.get("evidence", []),
                "strengths": evaluation.get("strengths", []),
                "weak_areas": evaluation.get("weak_areas", []),
                "star_components": evaluation.get("star_components", {}),
                "exaggeration_risk": evaluation.get("exaggeration_risk", False),
                "accountability_gap": evaluation.get("accountability_gap", False),
                "project_discussed": evaluation.get("project_discussed", False),
                "jd_skill_hits": evaluation.get("jd_skill_hits", []),
                "resume_skill_hits": evaluation.get("resume_skill_hits", []),
                "company_focus_hits": evaluation.get("company_focus_hits", []),
                "role_alignment_hits": evaluation.get("role_alignment_hits", []),
                "followup_intent": strategy.get("followup_intent", ""),
                "next_question": state.get("ai_text", ""),
                "next_question_reason": evaluation.get("next_question_reason", ""),
            },
        ][-20:]

    contradiction_history = previous.get("contradiction_history", [])
    if contradiction:
        contradiction_history = [*contradiction_history, contradiction][-10:]

    weak_areas = _weak_areas_from_eval(evaluation)
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
        "pending_project_switch": is_switch_request,
        "turns": turns,
        "latest_scores": evaluation.get("scores", {}),
        "latest_flags": evaluation.get("flags", []),
        "latest_star": evaluation.get("star_components", {}),
        "latest_context_alignment": evaluation.get("context_alignment", {}),
        "exaggeration_risk": evaluation.get("exaggeration_risk", False),
        "accountability_gap": evaluation.get("accountability_gap", False),
        "contradiction_history": contradiction_history,
        "current_goal": strategy.get("goal", ""),
    }
    return {**state, "project_behavioral": project_behavioral, "weak_areas": weak_areas}


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
    seniority = "senior" if re.search(r"\bsenior|lead|mentor|architect\b", text, re.I) else "early-career"
    return {
        "skills": skills[:10],
        "responsibilities": responsibilities[:8],
        "seniority": seniority,
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
    project_text = " ".join(str(value) for value in selected_project.values()) if selected_project else ""
    jd_skills = {skill.lower() for skill in jd_signals.get("skills", [])}
    resume_skill_matches = [skill for skill in skills if skill.lower() in jd_skills]
    selected_name = selected_project.get("name") or "your strongest resume project"
    selected_source = (selected_project_choice or {}).get("source") or ("resume" if selected_project else "fallback")
    return {
        "selected_project": selected_name,
        "selected_project_source": selected_source,
        "candidate_selected_project": selected_name if selected_source in {"candidate", "resume_match"} else "",
        "project_summary": _clip(project_text, 420),
        "resume_skill_matches": resume_skill_matches[:10],
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
    pending_project_switch = bool(previous.get("pending_project_switch")) if isinstance(previous, dict) else False

    explicit_name = _extract_explicit_project_name(text)
    if explicit_name:
        matched_project = _best_matching_resume_project(explicit_name, projects)
        if matched_project:
            return {
                "name": matched_project.get("name") or explicit_name,
                "source": "resume_match",
                "resume_project": matched_project,
                "summary": _project_summary(matched_project),
            }
        return {
            "name": explicit_name,
            "source": "candidate",
            "summary": _clip(text, 420),
        }

    if pending_project_switch and not _is_project_switch_request(text):
        matched_project = _best_matching_resume_project(text, projects, min_score=1)
        if matched_project:
            return {
                "name": matched_project.get("name") or "selected resume project",
                "source": "resume_match",
                "resume_project": matched_project,
                "summary": _project_summary(matched_project),
            }
        candidate_name = _clean_project_choice(text)
        if _looks_like_project_name(candidate_name):
            return {
                "name": candidate_name,
                "source": "candidate",
                "summary": _clip(text, 420),
            }

    if isinstance(previous_choice, dict) and previous_choice.get("name"):
        return {
            "name": previous_choice.get("name"),
            "source": previous_choice.get("source", "candidate"),
            "summary": previous_choice.get("summary", ""),
        }

    matched_project = _best_matching_resume_project(text, projects, min_score=3)
    if matched_project:
        return {
            "name": matched_project.get("name") or "selected resume project",
            "source": "resume_match",
            "resume_project": matched_project,
            "summary": _project_summary(matched_project),
        }

    return None


def _extract_explicit_project_name(user_text: str) -> str:
    text = re.sub(r"\s+", " ", user_text or "").strip()
    if not text:
        return ""

    project_context_pattern = re.search(
        r"\bmy\s+(?:strongest\s+|main\s+|best\s+)?(?P<context>[a-zA-Z0-9+.#&' -]{2,45}?)\s+project\s+"
        r"(?:which\s+is|that\s+is|called|named|is|was)\s+(?:an?\s+|the\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,90})",
        text,
        re.I,
    )
    if project_context_pattern:
        return _clean_project_choice(project_context_pattern.group("name"))

    talk_pattern = re.search(
        r"\b(?:i(?:'ll| will| would like to| want to| am going to)?|let me|i can)\s+"
        r"(?:be\s+)?(?:talk(?:ing)?\s+about|explain(?:ing)?|walk(?:ing)?\s+through|discuss(?:ing)?|choose|pick|present(?:ing)?)\s+"
        r"(?:my\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,110})",
        text,
        re.I,
    )
    if talk_pattern:
        return _clean_project_choice(talk_pattern.group("name"))

    strongest_pattern = re.search(
        r"\b(?:my\s+)?(?:strongest|main|best)\s+project\s+(?:is|was|would\s+be|will\s+be)\s+"
        r"(?:an?\s+|the\s+)?(?P<name>[a-zA-Z0-9+.#&' -]{3,90})",
        text,
        re.I,
    )
    if strongest_pattern:
        return _clean_project_choice(strongest_pattern.group("name"))

    return ""


def _clean_project_choice(value: str) -> str:
    value = re.split(r"[.!?;]|\s+(?:because|where|which|that|and then|so then)\b", value or "", maxsplit=1, flags=re.I)[0]
    value = re.sub(r"^(?:my|the|a|an|on|about|for)\s+", "", value.strip(), flags=re.I)
    value = re.sub(r"^(?:the|a|an)\s+", "", value.strip(), flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" ,:-")
    return _clip(value, 90)


def _best_matching_resume_project(
    text: str,
    projects: list[dict[str, Any]],
    min_score: int = 2,
) -> dict[str, Any] | None:
    if not text or not projects:
        return None
    lower = text.lower()
    text_tokens = {
        token
        for token in re.findall(r"[a-zA-Z0-9+.#-]+", lower)
        if len(token) >= 3 and token not in {"project", "about", "explain", "talking", "strongest"}
    }
    best_project = None
    best_score = 0
    for project in projects:
        project_text = _project_summary(project).lower()
        name = str(project.get("name") or "").lower()
        if name and (name in lower or lower in name):
            return project
        project_tokens = {
            token
            for token in re.findall(r"[a-zA-Z0-9+.#-]+", project_text)
            if len(token) >= 3
        }
        score = len(text_tokens & project_tokens)
        if score > best_score:
            best_score = score
            best_project = project
    return best_project if best_score >= min_score else None


def _project_from_choice(choice: dict[str, Any] | None, projects: list[dict[str, Any]]) -> dict[str, Any]:
    if choice:
        resume_project = choice.get("resume_project")
        if isinstance(resume_project, dict) and resume_project:
            return resume_project
        name = _clean_project_choice(str(choice.get("name") or "").strip())
        if name:
            matched_project = _best_matching_resume_project(name, projects)
            if matched_project:
                return matched_project
            return {"name": name, "description": choice.get("summary") or name}
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


def _is_project_switch_request(user_text: str) -> bool:
    lower = (user_text or "").lower().strip()
    if not lower:
        return False
    return bool(re.search(
        r"\b(?:can|could|may|should|let'?s|i\s+want\s+to|i'?d\s+like\s+to)\b.*\b(?:another|different|other|new|second)\s+project\b"
        r"|\b(?:switch|change|move)\b.*\bproject\b"
        r"|\b(?:discuss|talk\s+about|explain)\b.*\b(?:another|different|other|new|second)\s+project\b",
        lower,
    ))


def _project_switch_evaluation(resume_signals: dict[str, Any]) -> dict[str, Any]:
    current_project = _clean_project_choice(resume_signals.get("selected_project") or "this project")
    return {
        "evaluation_source": "local_control_intent",
        "scores": {},
        "flags": [],
        "evidence": [],
        "technical_terms": [],
        "has_metric": True,
        "context_alignment": {
            "has_resume_project": resume_signals.get("project_count", 0) > 0,
            "has_jd": False,
            "project_discussed": True,
            "jd_skill_hits": [],
            "jd_responsibility_hits": [],
            "resume_skill_hits": [],
            "company_focus_hits": [],
            "role_alignment_hits": [],
        },
        "project_discussed": True,
        "jd_skill_hits": [],
        "resume_skill_hits": [],
        "company_focus_hits": [],
        "role_alignment_hits": [],
        "star_components": {
            "situation": True,
            "task": True,
            "action": True,
            "result": True,
        },
        "exaggeration_risk": False,
        "accountability_gap": False,
        "followup_intent": "switch_project",
        "next_question": f"Yes. Which project do you want to switch to instead of {current_project}? Give me the project name and one-line context.",
        "next_question_reason": "Candidate asked to change the project focus.",
    }


def _is_greeting_only(user_text: str) -> bool:
    lower = re.sub(r"[^a-z\s]", "", (user_text or "").lower()).strip()
    return lower in {"hi", "hello", "hey", "hello hi", "hi hello"}


def _greeting_evaluation(resume_signals: dict[str, Any]) -> dict[str, Any]:
    current_project = _clean_project_choice(resume_signals.get("selected_project") or "your selected project")
    return {
        **_project_switch_evaluation(resume_signals),
        "followup_intent": "phase_default",
        "next_question": f"Hi. Let us continue with {current_project}: what exactly did you personally build, change, or own?",
        "next_question_reason": "Candidate sent a greeting instead of an interview answer.",
    }


def _looks_like_project_name(value: str) -> bool:
    tokens = re.findall(r"[a-zA-Z0-9+.#-]+", value or "")
    if not 1 <= len(tokens) <= 10:
        return False
    filler = {"yes", "yeah", "okay", "ok", "sure", "project", "another", "different"}
    return any(token.lower() not in filler and len(token) >= 3 for token in tokens)


def _project_summary(project: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in project.values():
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    return " ".join(parts)


def _evaluate_answer(
    user_text: str,
    strategy: dict[str, Any],
    resume_signals: dict[str, Any],
    jd_signals: dict[str, Any],
    company_profile: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    text = user_text.strip()
    lower = text.lower()
    words = re.findall(r"[a-zA-Z0-9+.#-]+", text)
    project_discussed = _candidate_referenced_resume_project(lower, resume_signals, len(words))
    jd_skill_hits = _keyword_hits(lower, jd_signals.get("skills", []))
    jd_responsibility_hits = _keyword_hits(lower, jd_signals.get("responsibilities", []))
    resume_skill_hits = _keyword_hits(lower, resume_signals.get("resume_skill_matches", []))
    company_focus_hits = _keyword_hits(lower, company_profile.get("focus_areas", []))
    role_alignment_hits = _role_alignment_hits(lower, session.get("job_role", ""))
    has_metric = bool(re.search(
        r"\b\d+%|\b\d+\s*percent\b|\b\d+x|\b\d+\+|\b\d+\s*(users|ms|seconds|requests|apis|features|tests|people|days|weeks|engineers?)\b",
        lower,
    ))
    first_person = len(re.findall(r"\bi\b|\bmy\b|\bme\b|\bbuilt\b|\bimplemented\b|\bdesigned\b|\bowned\b", lower))
    technical_terms = _keyword_hits(lower, [
        "api", "database", "cache", "latency", "scale", "architecture", "frontend", "backend",
        "react", "fastapi", "docker", "redis", "postgres", "testing", "security", "deployment",
        "tradeoff", "complexity", "failure", "monitoring", "microservices", "distributed",
        "schema", "index", "query", "throughput", "async", "concurrent",
    ])

    # STAR component detection
    situation_signals = _keyword_hits(lower, ["situation", "context", "background", "was working on", "we were", "the team"])
    task_signals = _keyword_hits(lower, ["task", "responsibility", "assigned", "challenge", "goal", "needed to"])
    action_signals = _keyword_hits(lower, ["i decided", "i implemented", "i refactored", "i built", "i changed", "i proposed", "my approach", "i wrote"])
    result_signals = _keyword_hits(lower, ["result", "outcome", "reduced", "improved", "increased", "shipped", "deployed", "learned", "prevented", "saved"])
    observable_result_signals = _observable_result_hits(lower)
    has_observable_result = bool(result_signals or observable_result_signals)

    star_score = min(10, (
        (3 if situation_signals else 0) +
        (3 if task_signals else 0) +
        (2 if action_signals else 1) +
        (3 if result_signals else 0) +
        (1 if has_metric else 0)
    ))

    # Exaggeration / inflation signals
    vague_superlatives = _keyword_hits(lower, [
        "best in class", "revolutionary", "completely redesigned", "10x engineer",
        "saved millions", "single-handedly", "entirely alone", "nobody else",
        "state of the art", "world-class",
    ])
    unsupported_claims = _keyword_hits(lower, [
        "10x", "saved millions", "zero downtime", "millions of users", "100% accurate",
        "never failed", "completely secure", "fully scalable", "production grade",
    ])
    accountability_gap = bool(
        re.search(r"\bwe\b", lower) and not re.search(r"\bi\b|\bmy\b|\bmy role\b|\bmy contribution\b", lower)
    )
    credibility_risk = bool(vague_superlatives or (unsupported_claims and not has_metric))

    scores = {
        "specificity": _score(len(words), [35, 80, 140]),
        "ownership": min(10, 3 + first_person),
        "technical_depth": min(10, 3 + len(technical_terms)),
        "impact": 9 if (has_metric and has_observable_result) else (7 if has_observable_result else (6 if has_metric else 3)),
        "star_completeness": star_score,
        "reflection": min(10, 3 + len(result_signals) + len(observable_result_signals)),
        "context_alignment": min(
            10,
            2
            + (2 if project_discussed else 0)
            + min(3, len(jd_skill_hits) + len(jd_responsibility_hits))
            + min(2, len(resume_skill_hits) + len(company_focus_hits))
            + min(1, len(role_alignment_hits)),
        ),
    }
    if accountability_gap:
        scores["ownership"] = min(scores["ownership"], 4)
    if credibility_risk:
        scores["impact"] = min(scores["impact"], 4)
        scores["specificity"] = min(scores["specificity"], 5)
    if resume_signals.get("project_count", 0) > 0 and not project_discussed:
        scores["context_alignment"] = min(scores["context_alignment"], 4)
    if jd_signals.get("has_jd") and not (jd_skill_hits or jd_responsibility_hits):
        scores["context_alignment"] = min(scores["context_alignment"], 5)

    flags = []
    if len(words) < 35:
        flags.append("Answer is too brief for a realistic Project + Behavioural interview.")
    if resume_signals.get("project_count", 0) > 0 and not project_discussed:
        flags.append(
            f"Resume project evidence is unclear; explicitly connect the answer to {resume_signals.get('selected_project', 'the selected project')}."
        )
    if jd_signals.get("has_jd") and not (jd_skill_hits or jd_responsibility_hits):
        flags.append("Job description connection is missing; tie the answer to at least one required skill or responsibility.")
    if company_profile.get("focus_areas") and not company_focus_hits:
        flags.append("Company-specific focus is not evident; connect the answer to the round's expected focus areas.")
    if first_person < 2 or accountability_gap:
        flags.append("Personal ownership is unclear; explain what YOU specifically did, not just 'we'.")
    if not has_metric and not has_observable_result:
        flags.append("Impact is unclear; add honest metrics or observable outcomes.")
    elif not has_metric:
        flags.append("Impact is observable but not quantified; a real interviewer may still ask how you validated it.")
    if len(technical_terms) < 2:
        flags.append("Technical depth is thin; include architecture, tradeoffs, or failure modes.")
    if not has_observable_result:
        flags.append("STAR result is missing; end with a concrete outcome and what you learned.")
    if not action_signals:
        flags.append("Your specific action is vague; say explicitly what you built or decided.")
    if vague_superlatives:
        flags.append(
            f"Possible exaggeration detected ({', '.join(vague_superlatives[:2])}); "
            "use precise, verifiable claims."
        )
    if unsupported_claims and not has_metric:
        flags.append(
            f"Unsupported high-impact claim detected ({', '.join(unsupported_claims[:2])}); interviewers need verifiable context before giving credit."
        )

    return {
        "evaluation_source": "local_fallback",
        "scores": scores,
        "flags": flags,
        "evidence": _extract_evidence_sentences(text),
        "technical_terms": technical_terms[:8],
        "has_metric": has_metric,
        "has_observable_result": has_observable_result,
        "observable_result_hits": observable_result_signals[:8],
        "context_alignment": {
            "has_resume_project": resume_signals.get("project_count", 0) > 0,
            "has_jd": jd_signals.get("has_jd", False),
            "project_discussed": project_discussed,
            "jd_skill_hits": jd_skill_hits[:8],
            "jd_responsibility_hits": jd_responsibility_hits[:8],
            "resume_skill_hits": resume_skill_hits[:8],
            "company_focus_hits": company_focus_hits[:8],
            "role_alignment_hits": role_alignment_hits[:6],
        },
        "project_discussed": project_discussed,
        "jd_skill_hits": jd_skill_hits[:8],
        "resume_skill_hits": resume_skill_hits[:8],
        "company_focus_hits": company_focus_hits[:8],
        "role_alignment_hits": role_alignment_hits[:6],
        "star_components": {
            "situation": bool(situation_signals),
            "task": bool(task_signals),
            "action": bool(action_signals),
            "result": has_observable_result,
        },
        "exaggeration_risk": credibility_risk,
        "accountability_gap": accountability_gap,
    }


def _ground_project_behavioral_score(
    evaluation: dict[str, Any],
    user_text: str,
    session: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    """Make PB scoring depend on whether the answer satisfies the actual prompt.

    Project + Behavioural questions do not have one fixed answer, but each prompt
    has expected evidence. A reply that does not answer that prompt should not
    receive credit just because it contains confident words or resume keywords.
    """
    scores = dict(evaluation.get("scores") or {})
    if not scores:
        return evaluation

    text = (user_text or "").strip()
    words = re.findall(r"[a-zA-Z0-9+.#-]+", text)
    prior_turns = (session.get("project_behavioral", {}) or {}).get("turns", [])
    current_question = ""
    if prior_turns:
        current_question = str(prior_turns[-1].get("next_question") or "")
    alignment = _project_answer_alignment_score(text, current_question, phase)

    weighted = (
        _score_to_ten(scores.get("ownership")) * 0.20
        + _score_to_ten(scores.get("technical_depth")) * 0.20
        + _score_to_ten(scores.get("impact")) * 0.18
        + _score_to_ten(scores.get("star_completeness")) * 0.16
        + _score_to_ten(scores.get("context_alignment")) * 0.16
        + _score_to_ten(scores.get("communication", scores.get("specificity"))) * 0.10
    )
    question_score = min(weighted, alignment)

    if len(words) < 8:
        question_score = 0
    elif len(words) < 18:
        question_score = min(question_score, 2)
    elif len(words) < 35:
        question_score = min(question_score, 4)

    if alignment <= 1:
        cap = 0
    elif alignment <= 3:
        cap = 3
    elif alignment <= 5:
        cap = 5
    else:
        cap = 10

    if cap < 10:
        for key, value in list(scores.items()):
            if isinstance(value, (int, float)):
                scores[key] = min(_score_to_ten(value), cap)

    scores["question_alignment"] = round(alignment, 2)
    scores["question_score"] = round(question_score, 2)
    flags = list(evaluation.get("flags") or [])
    if alignment <= 3:
        flags.append("Answer did not directly satisfy the interviewer question, so this turn receives little or no credit.")
    elif question_score <= 5:
        flags.append("Answer partially addressed the question but missed expected evidence such as ownership, tradeoffs, result, or STAR detail.")

    return {**evaluation, "scores": scores, "flags": _dedupe(flags)}


def _score_to_ten(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    score = float(value)
    if 0 <= score <= 1:
        return score * 10
    if score > 10:
        return score / 10
    return max(0.0, min(10.0, score))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = str(item).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _project_answer_alignment_score(text: str, current_question: str, phase: str) -> float:
    lower = (text or "").lower()
    q = (current_question or "").lower()
    words = re.findall(r"[a-zA-Z0-9+.#-]+", lower)
    if len(words) < 8:
        return 0.0

    ownership = bool(re.search(r"\bi\b|\bmy\b|\bme\b|\bbuilt\b|\bimplemented\b|\bdesigned\b|\bowned\b|\bchanged\b|\bdecided\b", lower))
    technical = bool(_keyword_hits(lower, [
        "architecture", "api", "database", "cache", "latency", "scale", "backend", "frontend",
        "model", "pipeline", "deployment", "tradeoff", "failure", "monitoring", "schema",
        "algorithm", "optimization", "testing", "security", "distributed",
    ]))
    result = bool(_observable_result_hits(lower) or re.search(r"\b\d+%|\b\d+x|\b\d+\+|\busers\b|\baccuracy\b|\blatency\b|\bsaved\b|\breduced\b|\bimproved\b|\bshipped\b|\bdeployed\b", lower))
    alternatives = bool(re.search(r"\balternative|rejected|instead|tradeoff|chose|decision|because|hardest\b", lower))
    star_parts = sum(bool(token) for token in [
        re.search(r"\bsituation|context|background|when\b", lower),
        re.search(r"\btask|goal|needed|responsibility|challenge\b", lower),
        re.search(r"\bi\s+(built|implemented|designed|changed|decided|led|wrote|created|owned)\b", lower),
        re.search(r"\bresult|outcome|learned|improved|reduced|increased|shipped|deployed\b", lower),
    ])

    score = 0.0
    if "personally" in q or "own" in q or "build" in q or "change" in q:
        score += 4 if ownership else 0
        score += 2 if technical else 0
        score += 2 if result else 0
        score += min(2, len(words) / 35 * 2)
        return round(min(10, score), 2)
    if "technical decision" in q or "alternatives" in q or "reject" in q:
        score += 3 if technical else 0
        score += 3 if alternatives else 0
        score += 2 if ownership else 0
        score += 2 if result else 0
        return round(min(10, score), 2)
    if "measurable" in q or "observable result" in q or "impact" in q:
        score += 5 if result else 0
        score += 2 if ownership else 0
        score += 2 if technical else 0
        score += min(1, len(words) / 40)
        return round(min(10, score), 2)
    if "star" in q or phase == "behavioural_star":
        return round(min(10, star_parts * 2.5), 2)
    if "10x" in q or "redesign" in q or "break first" in q:
        score += 3 if technical else 0
        score += 3 if re.search(r"\bscale|bottleneck|latency|database|cache|queue|load|throughput|failure\b", lower) else 0
        score += 2 if result else 0
        score += 2 if alternatives else 0
        return round(min(10, score), 2)

    score += 2 if ownership else 0
    score += 2 if technical else 0
    score += 2 if result else 0
    score += min(2, star_parts * 0.5)
    score += min(2, len(words) / 50 * 2)
    return round(min(10, score), 2)


def _fallback_question(state: ProjectBehavioralState) -> str:
    session = state["session"]
    strategy = state.get("strategy", {})
    profile = state.get("company_profile", {})
    resume = state.get("resume_signals", {})
    jd = state.get("jd_signals", {})
    evaluation = state.get("answer_evaluation", {})
    company = profile.get("company", session.get("target_company") or "this company")
    project = _clean_project_choice(resume.get("selected_project", "your strongest resume project"))
    role = session.get("job_role", "the role")
    theme = strategy.get("theme", "ownership")
    phase = strategy.get("phase", "project_deep_dive")
    intent = strategy.get("followup_intent", "phase_default")

    targeted = _targeted_followup(intent, evaluation, resume, jd, company, project, role)
    if targeted:
        return targeted

    if phase == "resume_walkthrough":
        jd_hint = ""
        if jd.get("skills"):
            jd_hint = f" Tie it to these JD signals: {', '.join(jd['skills'][:4])}."
        return f"Let us start the Project + Behavioural round for {role} at {company}. Walk me through {project}: what problem it solved, your exact ownership, and why it is relevant to this role.{jd_hint}"

    if phase == "project_deep_dive":
        repair = _repair_instruction(evaluation)
        return f"Go deeper on {project}. What was the hardest technical decision you personally made, what alternatives did you reject, and what result did that decision create? {repair}".strip()

    if phase == "technical_tradeoffs":
        return f"Now think like a {company} interviewer. If {project} had to support 10x more users or data, what would break first, how would you redesign it, and what metric would prove the redesign worked?"

    if phase == "behavioural_star":
        return f"Answer this in STAR format: tell me about a time you handled {theme} while building or shipping a project. I need the situation, your action, the result, and what you would do differently now."

    if phase == "pressure_validation":
        weak = evaluation.get("flags", ["your weakest previous answer"])[0]
        return f"I am going to pressure-test one area: {weak} Give a sharper version of that answer with one concrete example, one tradeoff, and one measurable outcome."

    return "We are near the end. Give me a concise closing pitch: why your resume, project experience, and behavioral evidence make you a strong fit for this job description?"


def _build_llm_payload(state: ProjectBehavioralState) -> dict[str, Any]:
    session = state["session"]
    evaluation = state.get("answer_evaluation", {})
    return {
        "round": "Project + Behavioural",
        "role": session.get("job_role"),
        "experience": session.get("experience_level"),
        "target_company": session.get("target_company"),
        "strategy": state.get("strategy", {}),
        "company_profile": state.get("company_profile", {}),
        "jd_signals": state.get("jd_signals", {}),
        "resume_signals": state.get("resume_signals", {}),
        "latest_evaluation": evaluation,
        "star_components": evaluation.get("star_components", {}),
        "exaggeration_risk": evaluation.get("exaggeration_risk", False),
        "accountability_gap": evaluation.get("accountability_gap", False),
        "candidate_answer": state.get("user_text", "")[-1200:],
        "contradiction_history": (state.get("session", {}).get("project_behavioral", {}) or {}).get("contradiction_history", [])[-3:],
    }


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = (text or "").lower()
    return [keyword for keyword in keywords if keyword.lower() in lower]


def _observable_result_hits(lower_answer: str) -> list[str]:
    return _keyword_hits(lower_answer, [
        "unbiased",
        "bias-free",
        "free from bias",
        "personal bias",
        "fair",
        "fairness",
        "consistent judging",
        "objective judging",
        "less subjective",
        "reliable evaluation",
        "better evaluation",
        "clearer feedback",
        "working prototype",
        "playable",
        "usable",
        "completed",
        "launched",
        "validated",
    ])


def _candidate_referenced_resume_project(lower_answer: str, resume_signals: dict[str, Any], word_count: int) -> bool:
    if int(resume_signals.get("project_count", 0) or 0) <= 0:
        return False

    project_name = str(resume_signals.get("selected_project", "") or "")
    project_tokens = [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9]+", project_name)
        if len(token) >= 4 and token.lower() not in {"your", "strongest", "resume", "project"}
    ]
    if project_tokens and any(token in lower_answer for token in project_tokens):
        return True

    project_summary = str(resume_signals.get("project_summary", "") or "")
    project_terms = [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9+.#-]+", project_summary)
        if len(token) >= 4 and token.lower() not in {"with", "using", "built", "project", "system", "application"}
    ]
    overlap = sum(1 for token in set(project_terms) if token in lower_answer)
    if overlap >= 2:
        return True

    project_language = _keyword_hits(lower_answer, ["project", "app", "application", "platform", "system", "dashboard", "api", "service"])
    return word_count >= 45 and len(project_language) >= 1


def _role_alignment_hits(lower_answer: str, job_role: str) -> list[str]:
    role_tokens = [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9+.#-]+", job_role or "")
        if len(token) >= 4 and token.lower() not in {"software", "engineer", "developer"}
    ]
    hits = [token for token in role_tokens if token in lower_answer]
    if "backend" in lower_answer:
        hits.append("backend")
    if "frontend" in lower_answer:
        hits.append("frontend")
    if "full stack" in lower_answer or "fullstack" in lower_answer:
        hits.append("full stack")
    return list(dict.fromkeys(hits))


def _pick_theme(themes: list[str], turn: int) -> str:
    if not themes:
        return "ownership"
    return themes[(max(1, turn) - 1) % len(themes)]


def _score(count: int, bands: list[int]) -> int:
    if count < bands[0]:
        return 3
    if count < bands[1]:
        return 6
    if count < bands[2]:
        return 8
    return 10


def _extract_evidence_sentences(text: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    useful = [sentence for sentence in sentences if len(sentence.split()) >= 8]
    return [_clip(sentence, 220) for sentence in useful[:3]]


def _weak_areas_from_eval(evaluation: dict[str, Any]) -> list[str]:
    return [*evaluation.get("flags", []), *evaluation.get("weak_areas", [])][:3]


def _repair_instruction(evaluation: dict[str, Any]) -> str:
    flags = evaluation.get("flags", [])
    if not flags:
        return ""
    return f"Also fix this gap from your previous answer: {flags[0]}"


def _select_followup_intent(evaluation: dict[str, Any], previous: dict[str, Any] | None = None) -> str:
    if not evaluation:
        return "phase_default"

    alignment = evaluation.get("context_alignment", {}) or {}
    star = evaluation.get("star_components", {}) or {}
    scores = evaluation.get("scores", {}) or {}
    previous = previous or {}

    if alignment.get("has_resume_project") and not alignment.get("project_discussed"):
        return _avoid_repeated_intent("anchor_resume_project", previous, ["clarify_ownership", "technical_depth"])
    if alignment.get("has_jd") and not (alignment.get("jd_skill_hits") or alignment.get("jd_responsibility_hits")):
        return _avoid_repeated_intent("connect_jd", previous, ["clarify_ownership", "technical_depth"])
    if evaluation.get("accountability_gap"):
        return _avoid_repeated_intent("clarify_ownership", previous, ["technical_depth", "quantify_impact"])
    if evaluation.get("exaggeration_risk"):
        return _avoid_repeated_intent("verify_claim", previous, ["clarify_ownership", "technical_depth"])
    if not evaluation.get("has_metric") and not evaluation.get("has_observable_result"):
        return _avoid_repeated_intent("quantify_impact", previous, ["clarify_ownership", "technical_depth"])
    if scores.get("technical_depth", 10) < 6:
        return _avoid_repeated_intent("technical_depth", previous, ["clarify_ownership", "quantify_impact"])
    if not evaluation.get("has_metric"):
        return _avoid_repeated_intent("quantify_impact", previous, ["technical_depth", "clarify_ownership"])

    missing_star = [name for name, present in star.items() if not present]
    if missing_star:
        return f"star_{missing_star[0]}"

    return "phase_default"


def _avoid_repeated_intent(intent: str, previous: dict[str, Any], alternatives: list[str]) -> str:
    recent_intents = [
        turn.get("followup_intent")
        for turn in (previous.get("turns", []) if isinstance(previous, dict) else [])[-2:]
        if turn.get("followup_intent")
    ]
    recent_questions = [
        str(turn.get("next_question") or "").lower()
        for turn in (previous.get("turns", []) if isinstance(previous, dict) else [])[-2:]
    ]
    repeated_by_question = intent == "quantify_impact" and any("measurable or observable result" in question for question in recent_questions)
    if intent not in recent_intents and not repeated_by_question:
        return intent
    for alternative in alternatives:
        if alternative not in recent_intents:
            return alternative
    return "phase_default"


def _targeted_followup(
    intent: str,
    evaluation: dict[str, Any],
    resume: dict[str, Any],
    jd: dict[str, Any],
    company: str,
    project: str,
    role: str,
) -> str:
    if intent == "phase_default":
        return ""

    if intent == "anchor_resume_project":
        return f"Anchor this to {project}. What exactly did you personally build, change, or own in that project?"

    if intent == "switch_project":
        return f"Yes. Which project do you want to switch to instead of {project}? Give me the project name and one-line context."

    if intent == "connect_jd":
        jd_targets = [*jd.get("skills", [])[:3], *jd.get("responsibilities", [])[:2]]
        target_text = ", ".join(jd_targets) if jd_targets else f"the {role} requirements"
        return f"Tie this answer to the job description. Which required skill or responsibility does {project} prove: {target_text}?"

    if intent == "clarify_ownership":
        return "You used broad team language. What did you personally own, what decision did you make, and what would have failed without your contribution?"

    if intent == "verify_claim":
        return "That claim needs verification. Give one concrete number, before-and-after comparison, or specific incident that proves the impact without exaggerating."

    if intent == "quantify_impact":
        return f"What measurable or observable result came from your work on {project}: latency, accuracy, users, time saved, defects reduced, or another honest outcome?"

    if intent == "technical_depth":
        return f"Go deeper technically on {project}. What architecture tradeoff, failure mode, scaling limit, or redesign decision did you personally handle?"

    if intent.startswith("star_"):
        missing = intent.replace("star_", "", 1)
        prompts = {
            "situation": "Give the Situation clearly: what was happening, who was involved, and why did it matter?",
            "task": "Give the Task clearly: what responsibility or goal was specifically assigned to you?",
            "action": "Give the Action clearly: what did you personally do step by step?",
            "result": "Give the Result clearly: what changed, what metric or outcome proved it, and what did you learn?",
        }
        return prompts.get(missing, "Complete the missing STAR component with specific evidence.")

    return ""


def _clip(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()
