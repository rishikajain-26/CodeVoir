from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services.interview_data_service import get_project_behavioral_config
from app.services.llm_service import llm_service


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
    resume_signals = _extract_resume_signals(session.get("resume_data", {}), jd_signals)
    return {
        **state,
        "company_profile": profile,
        "jd_signals": jd_signals,
        "resume_signals": resume_signals,
    }


def _evaluation_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    evaluation = _evaluate_answer(state.get("user_text", ""), state.get("strategy", {}))
    return {**state, "answer_evaluation": evaluation}


def _strategy_node(state: ProjectBehavioralState) -> ProjectBehavioralState:
    session = state["session"]
    turn = int(session.get("question_count", 0) or 0)
    profile = state.get("company_profile", {})
    evaluation = state.get("answer_evaluation", {})

    if turn <= 1:
        phase = "resume_walkthrough"
        goal = "connect resume, job description, and strongest project"
    elif turn <= 3:
        phase = "project_deep_dive"
        goal = "validate project ownership, architecture, and tradeoffs"
    elif turn <= 5:
        phase = "technical_tradeoffs"
        goal = "probe scaling, reliability, failure modes, and redesign thinking"
    elif turn <= 8:
        phase = "behavioural_star"
        goal = "collect STAR evidence for collaboration, conflict, pressure, or ambiguity"
    elif turn <= 10:
        phase = "pressure_validation"
        goal = "stress-test weak areas and company-specific expectations"
    else:
        phase = "closing"
        goal = "wrap up and prepare feedback"

    if evaluation.get("flags") and phase not in {"closing", "pressure_validation"}:
        goal = f"{goal}; repair weak evidence from the previous answer"

    strategy = {
        "turn": turn,
        "phase": phase,
        "goal": goal,
        "company_style": profile.get("interview_style", "balanced"),
        "theme": _pick_theme(profile.get("focus_areas", []), turn),
    }
    return {**state, "strategy": strategy, "phase": phase}


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
    ai_text = fallback
    if state["session"].get("llm_enabled"):
        ai_text = llm_service.generate(
            _BEHAVIORAL_SYSTEM_PROMPT,
            _build_llm_payload(state),
            fallback=fallback,
            temperature=0.4,
            max_tokens=240,
        )
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

    turns = previous.get("turns", [])
    contradiction = None
    if state.get("user_text"):
        contradiction = _detect_claim_contradiction(turns, state.get("user_text", ""))
        turns = [
            *turns,
            {
                "phase": strategy.get("phase", state.get("phase", "projects")),
                "answer_excerpt": _clip(state.get("user_text", ""), 320),
                "scores": evaluation.get("scores", {}),
                "flags": evaluation.get("flags", []),
                "evidence": evaluation.get("evidence", []),
                "star_components": evaluation.get("star_components", {}),
                "exaggeration_risk": evaluation.get("exaggeration_risk", False),
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
        "resume_focus": state.get("resume_signals", {}),
        "turns": turns,
        "latest_scores": evaluation.get("scores", {}),
        "latest_flags": evaluation.get("flags", []),
        "latest_star": evaluation.get("star_components", {}),
        "exaggeration_risk": evaluation.get("exaggeration_risk", False),
        "accountability_gap": evaluation.get("accountability_gap", False),
        "contradiction_history": contradiction_history,
        "current_goal": strategy.get("goal", ""),
    }
    return {**state, "project_behavioral": project_behavioral, "weak_areas": weak_areas}


def build_project_behavioral_graph():
    graph = StateGraph(ProjectBehavioralState)
    graph.add_node("context", _context_node)
    graph.add_node("evaluate_answer", _evaluation_node)
    graph.add_node("choose_strategy", _strategy_node)
    graph.add_node("compose_response", _response_node)
    graph.add_node("update_memory", _memory_node)

    graph.set_entry_point("context")
    graph.add_edge("context", "evaluate_answer")
    graph.add_edge("evaluate_answer", "choose_strategy")
    graph.add_edge("choose_strategy", "compose_response")
    graph.add_edge("compose_response", "update_memory")
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


def _extract_resume_signals(resume_data: dict[str, Any], jd_signals: dict[str, Any]) -> dict[str, Any]:
    projects = resume_data.get("projects", []) if isinstance(resume_data, dict) else []
    skills = resume_data.get("skills", []) if isinstance(resume_data, dict) else []
    selected_project = projects[0] if projects else {}
    project_text = " ".join(str(value) for value in selected_project.values()) if selected_project else ""
    jd_skills = {skill.lower() for skill in jd_signals.get("skills", [])}
    resume_skill_matches = [skill for skill in skills if skill.lower() in jd_skills]
    return {
        "selected_project": selected_project.get("name") or "your strongest resume project",
        "project_summary": _clip(project_text, 420),
        "resume_skill_matches": resume_skill_matches[:10],
        "project_count": len(projects),
        "skill_count": len(skills),
    }


def _evaluate_answer(user_text: str, strategy: dict[str, Any]) -> dict[str, Any]:
    text = user_text.strip()
    lower = text.lower()
    words = re.findall(r"[a-zA-Z0-9+.#-]+", text)
    has_metric = bool(re.search(
        r"\b\d+%|\b\d+x|\b\d+\+|\b\d+\s*(users|ms|seconds|requests|apis|features|tests|people|days|weeks|engineers?)\b",
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
    accountability_gap = bool(
        re.search(r"\bwe\b", lower) and not re.search(r"\bi\b|\bmy\b|\bmy role\b|\bmy contribution\b", lower)
    )

    scores = {
        "specificity": _score(len(words), [35, 80, 140]),
        "ownership": min(10, 3 + first_person),
        "technical_depth": min(10, 3 + len(technical_terms)),
        "impact": 9 if (has_metric and result_signals) else (6 if has_metric else (5 if result_signals else 3)),
        "star_completeness": star_score,
        "reflection": min(10, 3 + len(result_signals)),
    }
    flags = []
    if len(words) < 35:
        flags.append("Answer is too brief for a realistic Project + Behavioural interview.")
    if first_person < 2 or accountability_gap:
        flags.append("Personal ownership is unclear; explain what YOU specifically did, not just 'we'.")
    if not has_metric:
        flags.append("Impact is not quantified; add honest metrics or observable outcomes.")
    if len(technical_terms) < 2:
        flags.append("Technical depth is thin; include architecture, tradeoffs, or failure modes.")
    if not result_signals:
        flags.append("STAR result is missing; end with a concrete outcome and what you learned.")
    if not action_signals:
        flags.append("Your specific action is vague; say explicitly what you built or decided.")
    if vague_superlatives:
        flags.append(
            f"Possible exaggeration detected ({', '.join(vague_superlatives[:2])}); "
            "use precise, verifiable claims."
        )

    return {
        "scores": scores,
        "flags": flags,
        "evidence": _extract_evidence_sentences(text),
        "technical_terms": technical_terms[:8],
        "has_metric": has_metric,
        "star_components": {
            "situation": bool(situation_signals),
            "task": bool(task_signals),
            "action": bool(action_signals),
            "result": bool(result_signals),
        },
        "exaggeration_risk": len(vague_superlatives) > 0,
        "accountability_gap": accountability_gap,
    }


def _fallback_question(state: ProjectBehavioralState) -> str:
    session = state["session"]
    strategy = state.get("strategy", {})
    profile = state.get("company_profile", {})
    resume = state.get("resume_signals", {})
    jd = state.get("jd_signals", {})
    evaluation = state.get("answer_evaluation", {})
    company = profile.get("company", session.get("target_company") or "this company")
    project = resume.get("selected_project", "your strongest resume project")
    role = session.get("job_role", "the role")
    theme = strategy.get("theme", "ownership")
    phase = strategy.get("phase", "project_deep_dive")

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
    return evaluation.get("flags", [])[:3]


def _repair_instruction(evaluation: dict[str, Any]) -> str:
    flags = evaluation.get("flags", [])
    if not flags:
        return ""
    return f"Also fix this gap from your previous answer: {flags[0]}"


def _clip(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()
