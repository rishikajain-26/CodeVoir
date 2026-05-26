from __future__ import annotations

import random
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.orchestration.cs_fundamentals_llm import evaluate_cs_answer_with_llm
from app.services.interview_data_service import get_cs_fundamentals_config


class CSFundamentalsState(TypedDict, total=False):
    session: dict[str, Any]
    user_text: str
    scratchpad: dict[str, Any]
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


def run_cs_fundamentals_turn(session: dict[str, Any], user_text: str, scratchpad: dict[str, Any] | None = None) -> dict[str, Any]:
    result = CS_FUNDAMENTALS_GRAPH.invoke({"session": session, "user_text": user_text, "scratchpad": scratchpad or {}})
    session["phase"] = result.get("phase", session.get("phase", "cs_fundamentals"))
    session["cs_fundamentals"] = result.get("cs_fundamentals", session.get("cs_fundamentals", {}))
    for area in result.get("weak_areas", []):
        if area not in session["weak_areas"]:
            session["weak_areas"].append(area)
    return result


def _context_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    config = get_cs_fundamentals_config(session.get("target_company", ""))
    topics = config.get("topics") or [{"topic": topic, "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0} for topic in config.get("fallback_topics", [])]
    if not topics:
        topics = [{"topic": topic, "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0} for topic in ["DBMS", "OOP", "Operating Systems", "Computer Networks"]]
    topics = [_normalize_topic_item(topic) for topic in topics]
    return {**state, "cs_config": config, "topic_plan": topics}


def _select_topic_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    memory = session.get("cs_fundamentals", {})
    topics = state.get("topic_plan", [])
    pending = memory.get("pending_question") or {}
    pending_topic = pending.get("topic")

    selected = _topic_by_name(topics, pending_topic) if pending_topic else None
    if not selected:
        selected = _choose_next_topic(topics, memory, int(session.get("question_count", 0) or 0))

    return {**state, "current_topic": selected}


def _evaluate_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    memory = session.get("cs_fundamentals", {})
    llm_evaluation = evaluate_cs_answer_with_llm(
        session=session,
        memory=memory,
        topic=state.get("current_topic", {}),
        answered_question=memory.get("pending_question") or {},
        user_text=state.get("user_text", ""),
        scratchpad=state.get("scratchpad", {}),
    )
    evaluation = llm_evaluation or _evaluate_answer(
        state.get("user_text", ""),
        state.get("scratchpad", {}),
        state.get("current_topic", {}),
    )
    return {**state, "evaluation": evaluation}


def _strategy_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    turn = int(session.get("question_count", 0) or 0)
    evaluation = state.get("evaluation", {})
    scratchpad = state.get("scratchpad", {})
    topic = state.get("current_topic", {}).get("topic", "CS Fundamentals")
    topics = state.get("topic_plan", [])
    memory = session.get("cs_fundamentals", {})

    if evaluation.get("flags"):
        question_type = "repair"
        goal = "repair the weakest concept gap before moving on"
    elif scratchpad.get("content", "").strip():
        question_type = "scratchpad_followup"
        goal = "evaluate the candidate's written reasoning and ask a targeted follow-up"
    elif turn <= 1:
        question_type = "concept"
        goal = f"establish baseline clarity in {topic}"
    elif turn % 3 == 0:
        question_type = "scenario"
        goal = "test practical application in a real system"
    elif turn % 2 == 0:
        question_type = "comparison"
        goal = "test comparison and tradeoff reasoning"
    else:
        question_type = "applied_followup"
        goal = "connect the concept to backend/project behavior"

    if evaluation.get("flags"):
        next_topic = state.get("current_topic", {})
    else:
        next_topic = _choose_next_topic(topics, memory, turn, exclude=topic)
    next_subtopic = _pick_subtopic(next_topic)

    return {
        **state,
        "phase": "cs_fundamentals",
        "next_topic": next_topic,
        "next_subtopic": next_subtopic,
        "strategy": {"turn": turn, "question_type": question_type, "goal": goal, "topic": topic},
    }


def _response_node(state: CSFundamentalsState) -> CSFundamentalsState:
    fallback = _fallback_question(state)
    evaluation = state.get("evaluation", {})
    ai_text = evaluation.get("next_question") or fallback
    return {**state, "ai_text": ai_text}


def _memory_node(state: CSFundamentalsState) -> CSFundamentalsState:
    session = state["session"]
    previous = session.get("cs_fundamentals", {})
    turn = int(session.get("question_count", 0) or 0)
    topic = state.get("current_topic", {})
    next_topic = state.get("next_topic") or topic
    topic_name = topic.get("topic", "CS Fundamentals")
    next_topic_name = next_topic.get("topic", topic_name)
    evaluation = state.get("evaluation", {})
    strategy = state.get("strategy", {})
    scratchpad = state.get("scratchpad", {})
    answered_question = previous.get("pending_question") or {}

    questions = [
        *previous.get("questions_asked", []),
        {
            "topic": topic_name,
            "asked_subtopic": answered_question.get("subtopic", ""),
            "asked_question_type": answered_question.get("question_type", ""),
            "asked_question": answered_question.get("question", ""),
            "answered_turn": answered_question.get("turn", turn),
            "question_type": strategy.get("question_type", "concept"),
            "answer_text": _clip(state.get("user_text", ""), 1200),
            "answer_excerpt": _clip(state.get("user_text", ""), 280),
            "scratchpad_mode": scratchpad.get("mode", ""),
            "scratchpad_excerpt": _clip(scratchpad.get("content", ""), 320),
            "scores": evaluation.get("scores", {}),
            "evaluation_source": evaluation.get("evaluation_source", "local_fallback"),
            "flags": evaluation.get("flags", []),
            "misconceptions": evaluation.get("misconceptions", []),
            "keyword_hits": evaluation.get("keyword_hits", []),
            "strengths": evaluation.get("strengths", []),
            "missing_concepts": evaluation.get("missing_concepts", []),
            "next_question_reason": evaluation.get("next_question_reason", ""),
        },
    ][-30:]

    scores_by_topic = dict(previous.get("scores_by_topic", {}))
    scores_by_topic.setdefault(topic_name, [])
    scores_by_topic[topic_name] = [*scores_by_topic[topic_name], evaluation.get("scores", {})][-8:]

    weak_topics = list(previous.get("weak_topics", []))
    strong_topics = list(previous.get("strong_topics", []))
    avg_score = _avg_score(evaluation.get("scores", {}))
    if avg_score < 5.5 and topic_name not in weak_topics:
        weak_topics.append(topic_name)
    if avg_score >= 7.5 and topic_name not in strong_topics:
        strong_topics.append(topic_name)

    scratchpad_history = previous.get("scratchpad_history", [])
    if scratchpad.get("content", "").strip():
        scratchpad_history = [
            *scratchpad_history,
            {"topic": topic_name, "mode": scratchpad.get("mode", "text"), "content": _clip(scratchpad.get("content", ""), 600)},
        ][-12:]

    memory = {
        **previous,
        "current_topic": next_topic_name,
        "pending_question": {
            "topic": next_topic_name,
            "subtopic": state.get("next_subtopic") or _pick_subtopic(next_topic),
            "question_type": strategy.get("question_type", "concept"),
            "question": state.get("ai_text", ""),
            "turn": turn,
        },
        "last_answered_topic": topic_name,
        "current_question_type": strategy.get("question_type", "concept"),
        "topic_plan": [item.get("topic", "") for item in state.get("topic_plan", [])],
        "topics_covered": list(dict.fromkeys([*previous.get("topics_covered", []), topic_name])),
        "questions_asked": questions,
        "scores_by_topic": scores_by_topic,
        "weak_topics": weak_topics[-8:],
        "strong_topics": strong_topics[-8:],
        "scratchpad_history": scratchpad_history,
        "latest_scores": evaluation.get("scores", {}),
        "latest_flags": evaluation.get("flags", []),
        "current_goal": strategy.get("goal", ""),
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


def _evaluate_answer(user_text: str, scratchpad: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
    combined = f"{user_text}\n{scratchpad.get('content', '')}".strip()
    lower = combined.lower()
    words = re.findall(r"[a-zA-Z0-9_+.#-]+", combined)
    topic_name = topic.get("topic", "")
    subtopics = [str(item).lower() for item in topic.get("subtopics", [])]
    keyword_hits = [item for item in subtopics if item and item in lower]
    example_terms = _hits(lower, ["example", "for instance", "in a backend", "real system", "query", "api", "database", "thread", "request"])
    comparison_terms = _hits(lower, ["versus", "vs", "difference", "compare", "tradeoff", "pros", "cons"])
    correctness_terms = _topic_terms(topic_name, lower)
    misconception_hits = _misconception_hits(topic_name, lower)
    evidence_signals = len(correctness_terms) + len(keyword_hits)
    correctness_score = min(10, 2 + evidence_signals * 2)
    if misconception_hits:
        correctness_score = min(correctness_score, 3)
    elif evidence_signals == 0:
        correctness_score = 2

    scores = {
        "clarity": _score(len(words), [25, 55, 100]),
        "correctness": correctness_score,
        "application": min(10, 3 + len(example_terms) * 2),
        "depth": min(10, 3 + len(comparison_terms) * 2 + len(keyword_hits)),
        "communication": 8 if len(words) >= 35 and not _is_rambling(words) else 5,
    }
    if scores["correctness"] <= 3:
        # Real interviews do not reward fluent explanations that are technically wrong.
        scores["application"] = min(scores["application"], 4)
        scores["depth"] = min(scores["depth"], 4)

    flags = []
    if len(words) < 25:
        flags.append("Answer is too brief for a CS fundamentals interview.")
    for misconception in misconception_hits:
        flags.append(f"Incorrect concept: {misconception}.")
    if not correctness_terms and not keyword_hits:
        flags.append(f"Core {topic_name or 'CS'} concept signals are weak or missing.")
    if not example_terms:
        flags.append("Answer needs a practical example or system-level application.")
    if scratchpad.get("content", "").strip() and len(scratchpad.get("content", "").split()) < 4:
        flags.append("Scratchpad is present but too thin to evaluate clearly.")
    return {
        "evaluation_source": "local_fallback",
        "scores": scores,
        "flags": flags,
        "keyword_hits": keyword_hits[:8],
        "misconceptions": misconception_hits,
        "evidence": _extract_sentences(combined),
    }


def _fallback_question(state: CSFundamentalsState) -> str:
    topic = state.get("next_topic") or state.get("current_topic", {})
    topic_name = topic.get("topic", "CS Fundamentals")
    subtopic = state.get("next_subtopic") or _pick_subtopic(topic)
    strategy = state.get("strategy", {})
    qtype = strategy.get("question_type", "concept")
    evaluation = state.get("evaluation", {})
    scratchpad = state.get("scratchpad", {})

    if qtype == "concept":
        return f"Let's start {topic_name}. Explain {subtopic}: what it means, why it matters, and one real system where it appears."
    if qtype == "scratchpad_followup":
        return f"I see your {scratchpad.get('mode', 'text')} scratchpad. Walk me through it step by step, then tell me one edge case or tradeoff it does not cover."
    if qtype == "repair":
        gap = evaluation.get("flags", ["the missing core concept"])[0]
        return f"Let's fix this first: {gap} Give a sharper explanation of {subtopic} with one concrete example."
    if qtype == "comparison":
        return _comparison_question(topic_name, subtopic)
    if qtype == "scenario":
        return _scenario_question(topic_name, subtopic)
    return f"Good. Now apply {subtopic} to a backend project: where would it affect performance, correctness, reliability, or maintainability?"


def _build_llm_payload(state: CSFundamentalsState) -> dict[str, Any]:
    session = state["session"]
    return {
        "round": "CS Fundamentals",
        "role": session.get("job_role"),
        "experience": session.get("experience_level"),
        "target_company": session.get("target_company"),
        "answered_topic": state.get("current_topic", {}),
        "next_topic": state.get("next_topic") or state.get("current_topic", {}),
        "strategy": state.get("strategy", {}),
        "evaluation": state.get("evaluation", {}),
        "candidate_answer": state.get("user_text", "")[-1200:],
        "scratchpad": state.get("scratchpad", {}),
        "memory": session.get("cs_fundamentals", {}),
    }


def _pick_subtopic(topic: dict[str, Any]) -> str:
    subtopics = topic.get("subtopics") or []
    if subtopics:
        return str(random.choice(subtopics))
    fallbacks = {
        "DBMS": "transactions or indexing",
        "OOP": "polymorphism or interfaces",
        "Operating Systems": "processes, threads, or deadlock",
        "Computer Networks": "HTTP, HTTPS, or TCP",
    }
    return fallbacks.get(topic.get("topic", ""), topic.get("topic", "this concept"))


def _topic_by_name(topics: list[dict[str, Any]], topic_name: str | None) -> dict[str, Any] | None:
    if not topic_name:
        return None
    return next((normalised for topic in topics if (normalised := _normalize_topic_item(topic)).get("topic") == topic_name), None)


def _choose_next_topic(
    topics: list[dict[str, Any]],
    memory: dict[str, Any],
    turn: int,
    exclude: str | None = None,
) -> dict[str, Any]:
    if not topics:
        return {"topic": "CS Fundamentals", "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0}

    candidates = [topic for topic in topics if topic.get("topic") != exclude] or topics
    covered = memory.get("topics_covered", [])
    weak_topics = memory.get("weak_topics", [])

    if weak_topics and turn % 3 == 0:
        weak_match = _topic_by_name(candidates, weak_topics[-1])
        if weak_match:
            return weak_match

    uncovered = [topic for topic in candidates if topic.get("topic") not in covered]
    return random.choice(uncovered) if uncovered else random.choice(candidates)


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


def _comparison_question(topic_name: str, subtopic: str) -> str:
    if topic_name == "DBMS":
        return "Compare normalization and indexing. Which one improves data quality, which one improves lookup speed, and what tradeoff can each introduce?"
    if topic_name == "Operating Systems":
        return "Compare process and thread. How do memory isolation, scheduling, and crash impact differ?"
    if topic_name == "OOP":
        return "Compare abstract classes and interfaces. When would you choose each in a real codebase?"
    if topic_name == "Computer Networks":
        return "Compare HTTP and HTTPS. What does TLS add, and where does certificate validation fit?"
    return f"Compare {subtopic} with a related concept and explain the practical tradeoff."


def _scenario_question(topic_name: str, subtopic: str) -> str:
    if topic_name == "DBMS":
        return "A backend API becomes slow because one table has millions of rows. What DBMS concepts would you inspect first, and what would you write in the scratchpad if a query helps?"
    if topic_name == "Operating Systems":
        return "Two worker tasks freeze while waiting for shared resources. Explain the likely OS concept and sketch the wait relationship if the scratchpad helps."
    if topic_name == "OOP":
        return "A codebase has repeated conditional logic for different payment types. Which OOP concept would improve this design, and why?"
    if topic_name == "Computer Networks":
        return "Users report intermittent request failures. What network layers or protocol steps would you check first?"
    return f"Give a real debugging scenario where {subtopic} matters, then explain your reasoning."


def _topic_terms(topic_name: str, lower: str) -> list[str]:
    terms = {
        "DBMS": ["sql", "transaction", "index", "normalization", "join", "acid", "lock", "query"],
        "OOP": ["class", "object", "inheritance", "polymorphism", "interface", "abstraction", "encapsulation"],
        "Operating Systems": ["process", "thread", "deadlock", "memory", "scheduler", "mutex", "semaphore", "race"],
        "Computer Networks": ["http", "https", "tcp", "udp", "dns", "tls", "packet", "latency", "request"],
    }
    return _hits(lower, terms.get(topic_name, []))


def _misconception_hits(topic_name: str, lower: str) -> list[str]:
    patterns = {
        "DBMS": [
            (r"\bindex(es)?\s+always\s+make(s)?\s+(queries|writes)\s+faster\b", "indexes are not always faster; they add write/storage cost and depend on query shape"),
            (r"\bnormalization\s+(is|means)\s+index", "normalization and indexing solve different problems"),
            (r"\btransaction(s)?\s+(is|are)\s+only\s+select\b", "transactions group one or more operations with commit/rollback semantics"),
            (r"\bacid\b.*\b(speed|performance)\b", "ACID is about correctness guarantees, not raw speed"),
        ],
        "OOP": [
            (r"\binterface(s)?\s+can\s+store\s+state\b", "interfaces define contracts; instance state belongs in implementing classes"),
            (r"\bpolymorphism\s+(is|means)\s+copy", "polymorphism is substitutable behavior through a common interface/type"),
            (r"\binheritance\s+always\s+better\b", "inheritance is not always better than composition"),
        ],
        "Operating Systems": [
            (r"\bthread(s)?\s+do\s+not\s+share\s+memory\b", "threads in a process share address space"),
            (r"\bprocess(es)?\s+share\s+the\s+same\s+memory\b", "separate processes are memory-isolated by default"),
            (r"\bdeadlock\s+(is|means)\s+slow\b", "deadlock is circular waiting for resources, not just slowness"),
        ],
        "Computer Networks": [
            (r"\bhttps\s+(is|means)\s+faster\s+http\b", "HTTPS adds TLS security; it is not defined as faster HTTP"),
            (r"\btcp\s+does\s+not\s+guarantee\s+order\b", "TCP provides ordered reliable byte-stream delivery"),
            (r"\budp\s+guarantee(s)?\s+delivery\b", "UDP does not guarantee delivery or ordering"),
            (r"\bdns\s+(encrypts|encryption)\b", "DNS resolves names; encryption is handled by protocols such as TLS or encrypted DNS variants"),
        ],
    }
    return [message for pattern, message in patterns.get(topic_name, []) if re.search(pattern, lower)]


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term in text]


def _score(count: int, bands: list[int]) -> int:
    if count < bands[0]:
        return 3
    if count < bands[1]:
        return 6
    if count < bands[2]:
        return 8
    return 10


def _is_rambling(words: list[str]) -> bool:
    return len(words) > 180


def _extract_sentences(text: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if len(sentence.split()) >= 6]
    return [_clip(sentence, 220) for sentence in sentences[:3]]


def _weak_areas(evaluation: dict[str, Any], topic_name: str) -> list[str]:
    items = [*evaluation.get("flags", []), *evaluation.get("weak_areas", [])]
    return [f"{topic_name}: {flag}" for flag in items[:3]]


def _avg_score(scores: dict[str, int]) -> float:
    values = list(scores.values())
    return sum(values) / len(values) if values else 0


def _clip(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit].rstrip()
