from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.orchestration.cs_fundamentals_llm import evaluate_cs_answer_with_llm
from app.services.interview_data_service import get_cs_fundamentals_config


class CSFundamentalsState(TypedDict, total=False):
    session: dict[str, Any]
    user_text: str
    cs_config: dict[str, Any]
    topic_plan: list[dict[str, Any]]
    current_topic: dict[str, Any]
    next_topic: dict[str, Any]
    next_subtopic: str
    evaluation: dict[str, Any]
    strategy: dict[str, Any]
    ai_text: str
    phase: str
    cs_fundamentals: dict[str, Any]
    weak_areas: list[str]


def run_cs_fundamentals_turn(
    session: dict[str, Any],
    user_text: str,
) -> dict[str, Any]:
    result = CS_FUNDAMENTALS_GRAPH.invoke(
        {"session": session, "user_text": user_text}
    )
    session["phase"] = result.get("phase", session.get("phase", "cs_fundamentals"))
    session["cs_fundamentals"] = result.get("cs_fundamentals", session.get("cs_fundamentals", {}))
    for area in result.get("weak_areas", []):
        if area not in session["weak_areas"]:
            session["weak_areas"].append(area)
    return result


def _context_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    config = get_cs_fundamentals_config(session.get("target_company", ""))
    topics = config.get("topics") or [
        {"topic": topic, "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0}
        for topic in config.get("fallback_topics", [])
    ]
    if not topics:
        topics = [
            {"topic": topic, "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0}
            for topic in ["DBMS", "OOP", "Operating Systems", "Computer Networks"]
        ]
    return {**state, "cs_config": config, "topic_plan": [_normalize_topic_item(topic) for topic in topics]}


def _select_topic_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    memory = session.get("cs_fundamentals", {})
    topics = state.get("topic_plan", [])
    pending_topic = (memory.get("pending_question") or {}).get("topic")
    selected = _topic_by_name(topics, pending_topic) if pending_topic else None
    return {**state, "current_topic": selected or _choose_next_topic(topics, memory)}


def _evaluate_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    memory = session.get("cs_fundamentals", {})
    topic = state.get("current_topic", {})
    topic_name = topic.get("topic", "")
    questions_on_topic = (memory.get("questions_per_topic") or {}).get(topic_name, 0)

    evaluation = evaluate_cs_answer_with_llm(
        session=session,
        memory=memory,
        topic=topic,
        answered_question=memory.get("pending_question") or {},
        user_text=state.get("user_text", ""),
        questions_on_topic=questions_on_topic,
    ) or _llm_unavailable_evaluation(topic)
    return {**state, "evaluation": evaluation}


def _strategy_node(state: CSFundamentalsState) -> CSFundamentalsState:
    evaluation = state.get("evaluation", {})
    topic = state.get("current_topic", {})
    topics = state.get("topic_plan", [])
    next_topic = _topic_by_name(topics, evaluation.get("next_topic")) or topic
    next_subtopic = evaluation.get("next_subtopic") or _pick_subtopic(next_topic)
    return {
        **state,
        "phase": "cs_fundamentals",
        "next_topic": next_topic,
        "next_subtopic": next_subtopic,
        "strategy": {
            "turn": int(state["session"].get("question_count", 0) or 0),
            "question_type": evaluation.get("question_type") or "followup",
            "goal": evaluation.get("next_question_reason") or "continue the CS fundamentals conversation",
            "topic": topic.get("topic", "CS Fundamentals"),
            "intent": evaluation.get("candidate_intent") or "answering",
        },
    }


def _response_node(state: CSFundamentalsState) -> CSFundamentalsState:
    evaluation = state.get("evaluation", {})
    return {**state, "ai_text": evaluation.get("next_question") or _llm_unavailable_message()}


def _memory_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    previous = session.get("cs_fundamentals", {})
    evaluation = state.get("evaluation", {})
    strategy = state.get("strategy", {})
    topic = state.get("current_topic", {})
    next_topic = state.get("next_topic") or topic
    topic_name = topic.get("topic", "CS Fundamentals")
    next_topic_name = next_topic.get("topic", topic_name)
    turn = int(session.get("question_count", 0) or 0)
    answered_question = previous.get("pending_question") or {}

    questions = [
        *previous.get("questions_asked", []),
        {
            "topic": topic_name,
            "asked_subtopic": answered_question.get("subtopic", ""),
            "asked_question_type": answered_question.get("question_type", ""),
            "asked_question": answered_question.get("question", ""),
            "answered_turn": answered_question.get("turn", turn),
            "question_type": strategy.get("question_type", "followup"),
            "answer_text": _clip(state.get("user_text", ""), 1200),
            "answer_excerpt": _clip(state.get("user_text", ""), 280),
            "scores": evaluation.get("scores", {}),
            "evaluation_source": evaluation.get("evaluation_source", "llm_unavailable"),
            "flags": evaluation.get("flags", []),
            "misconceptions": evaluation.get("misconceptions", []),
            "keyword_hits": evaluation.get("keyword_hits", []),
            "strengths": evaluation.get("strengths", []),
            "missing_concepts": evaluation.get("missing_concepts", []),
            "next_question_reason": evaluation.get("next_question_reason", ""),
            "intent": strategy.get("intent", ""),
        },
    ][-30:]

    scores_by_topic = dict(previous.get("scores_by_topic", {}))
    scores_by_topic.setdefault(topic_name, [])
    scores_by_topic[topic_name] = [*scores_by_topic[topic_name], evaluation.get("scores", {})][-8:]

    questions_per_topic = dict(previous.get("questions_per_topic", {}))
    questions_per_topic[topic_name] = questions_per_topic.get(topic_name, 0) + 1

    memory = {
        **previous,
        "current_topic": next_topic_name,
        "pending_question": {
            "topic": next_topic_name,
            "subtopic": state.get("next_subtopic") or _pick_subtopic(next_topic),
            "question_type": strategy.get("question_type", "followup"),
            "question": state.get("ai_text", ""),
            "turn": turn,
        },
        "last_answered_topic": topic_name,
        "current_question_type": strategy.get("question_type", "followup"),
        "topic_plan": [item.get("topic", "") for item in state.get("topic_plan", [])],
        "topics_covered": list(dict.fromkeys([*previous.get("topics_covered", []), topic_name])),
        "questions_asked": questions,
        "scores_by_topic": scores_by_topic,
        "weak_topics": _merge_topic(previous.get("weak_topics", []), topic_name, _avg_score(evaluation.get("scores", {})) < 5.5),
        "strong_topics": _merge_topic(previous.get("strong_topics", []), topic_name, _avg_score(evaluation.get("scores", {})) >= 7.5),
        "questions_per_topic": questions_per_topic,
        "latest_scores": evaluation.get("scores", {}),
        "latest_flags": evaluation.get("flags", []),
        "current_goal": strategy.get("goal", ""),
        "last_intent": strategy.get("intent", ""),
    }
    return {**state, "cs_fundamentals": memory, "weak_areas": _weak_areas(evaluation, topic_name)}


def build_cs_fundamentals_graph():
    graph = StateGraph(CSFundamentalsState)
    graph.add_node("load_context", _context_node)
    graph.add_node("select_topic", _select_topic_node)
    graph.add_node("evaluate_answer", _evaluate_node)
    graph.add_node("choose_strategy", _strategy_node)
    graph.add_node("generate_question", _response_node)
    graph.add_node("update_memory", _memory_node)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "select_topic")
    graph.add_edge("select_topic", "evaluate_answer")
    graph.add_edge("evaluate_answer", "choose_strategy")
    graph.add_edge("choose_strategy", "generate_question")
    graph.add_edge("generate_question", "update_memory")
    graph.add_edge("update_memory", END)
    return graph.compile()


CS_FUNDAMENTALS_GRAPH = build_cs_fundamentals_graph()


def _llm_unavailable_evaluation(topic: dict[str, Any]) -> dict[str, Any]:
    topic_name = topic.get("topic", "CS Fundamentals")
    return {
        "evaluation_source": "llm_unavailable",
        "scores": {},
        "verdict": "unavailable",
        "candidate_intent": "unknown",
        "flags": ["LLM response was unavailable; no local interview fallback was used."],
        "keyword_hits": [],
        "misconceptions": [],
        "evidence": [],
        "strengths": [],
        "missing_concepts": [],
        "next_topic": topic_name,
        "next_subtopic": _pick_subtopic(topic),
        "question_type": "unavailable",
        "next_question": _llm_unavailable_message(),
        "next_question_reason": "LLM unavailable.",
        "should_repair_before_moving_on": False,
    }


def _llm_unavailable_message() -> str:
    return "The AI model is unavailable for this turn, so I will not continue with a scripted local interview response. Please retry once the LLM connection is healthy."


def _normalize_topic_item(topic: Any) -> dict[str, Any]:
    if isinstance(topic, dict):
        return {
            "topic": str(topic.get("topic", "") or "CS Fundamentals"),
            "subtopics": topic.get("subtopics", []) or [],
            "matched_keywords": topic.get("matched_keywords", []) or [],
            "source_urls": topic.get("source_urls", []) or [],
            "evidence_count": topic.get("evidence_count", 0) or 0,
        }
    return {"topic": str(topic), "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0}


def _topic_by_name(topics: list[dict[str, Any]], topic_name: str | None) -> dict[str, Any] | None:
    if not topic_name:
        return None
    wanted = topic_name.strip().lower()
    return next((topic for topic in topics if str(topic.get("topic", "")).strip().lower() == wanted), None)


def _choose_next_topic(topics: list[dict[str, Any]], memory: dict[str, Any]) -> dict[str, Any]:
    if not topics:
        return {"topic": "CS Fundamentals", "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0}
    covered = set(memory.get("topics_covered", []))
    return next((topic for topic in topics if topic.get("topic") not in covered), topics[0])


def _pick_subtopic(topic: dict[str, Any]) -> str:
    subtopics = topic.get("subtopics") or []
    return str(subtopics[0]) if subtopics else topic.get("topic", "this concept")


def _merge_topic(existing: list[str], topic: str, include: bool) -> list[str]:
    return [*existing, topic][-8:] if include and topic not in existing else existing[-8:]


def _weak_areas(evaluation: dict[str, Any], topic_name: str) -> list[str]:
    items = [*evaluation.get("flags", []), *evaluation.get("weak_areas", [])]
    return [f"{topic_name}: {flag}" for flag in items[:3]]


def _avg_score(scores: dict[str, int | float]) -> float:
    values = list(scores.values())
    return sum(float(value) for value in values) / len(values) if values else 0.0


def _clip(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()
