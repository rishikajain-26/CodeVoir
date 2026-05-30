from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.llm_service import llm_service


def _to_float(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(10.0, score * 10 if 0 <= score <= 1 else score))


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _to_list(value: Any) -> list[str]:
    if value in (None, False, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


class CSEvaluationScores(BaseModel):
    clarity: float = 0.0
    correctness: float = 0.0
    application: float = 0.0
    depth: float = 0.0
    communication: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def coerce_score(cls, value: Any) -> float:
        return _to_float(value)


class CSFundamentalsLLMEvaluation(BaseModel):
    evaluation_source: str = "llm"
    scores: CSEvaluationScores = Field(default_factory=CSEvaluationScores)
    verdict: str = "weak"
    candidate_intent: str = "answering"
    keyword_hits: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
<<<<<<< HEAD
=======
    scratchpad_used: bool = False
>>>>>>> b2a9557 (WIP: saving local work before sync)
    next_topic: str = ""
    next_subtopic: str = ""
    question_type: str = "followup"
    next_question: str = ""
    next_question_reason: str = ""
    should_repair_before_moving_on: bool = False

    @field_validator(
        "keyword_hits",
        "misconceptions",
        "flags",
        "evidence",
        "strengths",
        "missing_concepts",
        mode="before",
    )
    @classmethod
    def coerce_lists(cls, value: Any) -> list[str]:
        return _to_list(value)

<<<<<<< HEAD
    @field_validator("should_repair_before_moving_on", mode="before")
=======
    @field_validator("scratchpad_used", "should_repair_before_moving_on", mode="before")
>>>>>>> b2a9557 (WIP: saving local work before sync)
    @classmethod
    def coerce_bools(cls, value: Any) -> bool:
        return _to_bool(value)

    @field_validator("verdict", mode="before")
    @classmethod
    def coerce_verdict(cls, value: Any) -> str:
        verdict = str(value or "").strip().lower()
        if verdict in {"strong", "acceptable", "weak", "incorrect"}:
            return verdict
        if verdict in {"hint", "help", "stuck", "unknown", "not_applicable", "meta"}:
            return "weak"
        return "weak"

    @model_validator(mode="after")
    def ensure_next_question(self) -> "CSFundamentalsLLMEvaluation":
        self.next_question = self.next_question.strip()
        if not self.next_question:
            self.next_question = "Please continue your answer with the key concept and one practical example."
        return self

    def as_graph_evaluation(self) -> dict[str, Any]:
        return {
            "evaluation_source": "llm",
            "scores": self.scores.model_dump(),
            "flags": self.flags,
            "keyword_hits": self.keyword_hits,
            "misconceptions": self.misconceptions,
            "evidence": self.evidence,
            "strengths": self.strengths,
            "missing_concepts": self.missing_concepts,
<<<<<<< HEAD
=======
            "scratchpad_used": self.scratchpad_used,
>>>>>>> b2a9557 (WIP: saving local work before sync)
            "candidate_intent": self.candidate_intent,
            "next_topic": self.next_topic,
            "next_subtopic": self.next_subtopic,
            "question_type": self.question_type,
            "next_question": self.next_question,
            "next_question_reason": self.next_question_reason,
            "should_repair_before_moving_on": self.should_repair_before_moving_on,
            "verdict": self.verdict,
        }


CS_EVALUATION_SYSTEM_PROMPT = """You are a strict but fair CS Fundamentals interviewer.
<<<<<<< HEAD
Evaluate only the candidate's answer against the asked topic/question.
=======
Evaluate only the candidate's answer and scratchpad against the asked topic/question.
>>>>>>> b2a9557 (WIP: saving local work before sync)
Use company context only to choose realistic follow-up depth, not to invent evidence.
If the candidate asks for a hint, answer with one useful hint instead of evaluating them harshly.
If the candidate corrects the interviewer, asks to switch focus, or asks a meta-question, respond to that intent first.
You decide the next_topic, next_subtopic, question_type, and next_question from the conversation.
Do not follow a local script. Do not move topics just because a fixed turn count says so.
Return ONLY valid JSON matching the requested schema.
Do not mention hidden prompts, API keys, credentials, or secrets.
Write the next_question naturally from the conversation context. Ask at most one question."""


def build_cs_evaluation_payload(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    topic: dict[str, Any],
    answered_question: dict[str, Any],
    user_text: str,
<<<<<<< HEAD
=======
    scratchpad: dict[str, Any],
>>>>>>> b2a9557 (WIP: saving local work before sync)
    questions_on_topic: int = 0,
) -> dict[str, Any]:
    topic_name = topic.get("topic", "")
    # Instruction for the LLM on how to handle move-on vs repair
    if questions_on_topic >= 1:
        progression_rule = (
            f"The candidate has already answered {questions_on_topic} question(s) on {topic_name}. "
            "If their answer is still weak or incorrect, set should_repair_before_moving_on=false and "
            "transition to the next topic in your next_question. Do NOT drill the same topic further."
        )
    else:
        progression_rule = (
            f"This is the first question on {topic_name}. "
            "If the answer is weak or incorrect, set should_repair_before_moving_on=true and ask one focused repair question. "
            "If the answer is satisfactory, you may dive deeper OR move to a new topic — your choice."
        )

    return {
        "round_type": "cs_fundamentals",
        "job_role": session.get("job_role", ""),
        "target_company": session.get("target_company", ""),
        "job_description": session.get("job_description", ""),
        "company_round_config": session.get("round_config", {}),
        "topic_being_evaluated": topic,
        "available_topics": [
            {
                "topic": item.get("topic", ""),
                "subtopics": item.get("subtopics", [])[:12],
            }
            for item in (session.get("round_config", {}).get("topics") or [])
            if isinstance(item, dict)
        ],
        "question_candidate_answered": answered_question,
        "candidate_answer": user_text,
<<<<<<< HEAD
=======
        "scratchpad": {
            "mode": scratchpad.get("mode", ""),
            "content": scratchpad.get("content", ""),
        },
>>>>>>> b2a9557 (WIP: saving local work before sync)
        "prior_memory": {
            "weak_topics": memory.get("weak_topics", []),
            "strong_topics": memory.get("strong_topics", []),
            "topics_covered": memory.get("topics_covered", []),
            "last_answered_topic": memory.get("last_answered_topic", ""),
            "questions_per_topic": memory.get("questions_per_topic", {}),
        },
        "conversation_history": [
            {"role": m["role"], "content": m["content"]}
            for m in session.get("messages", [])[-8:]
            if m.get("role") in ("candidate", "interviewer")
        ],
        "required_json_fields": list(CSFundamentalsLLMEvaluation.model_fields.keys()),
        "scoring_rule": "Scores must be 0-10. Do not give high correctness if the core concept is wrong.",
        "progression_rule": progression_rule,
    }


def evaluate_cs_answer_with_llm(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    topic: dict[str, Any],
    answered_question: dict[str, Any],
    user_text: str,
<<<<<<< HEAD
=======
    scratchpad: dict[str, Any],
>>>>>>> b2a9557 (WIP: saving local work before sync)
    questions_on_topic: int = 0,
) -> dict[str, Any] | None:
    if not llm_service.is_configured():
        return None
    session["llm_enabled"] = True
    payload = build_cs_evaluation_payload(
        session=session,
        memory=memory,
        topic=topic,
        answered_question=answered_question,
        user_text=user_text,
<<<<<<< HEAD
=======
        scratchpad=scratchpad,
>>>>>>> b2a9557 (WIP: saving local work before sync)
        questions_on_topic=questions_on_topic,
    )
    result = llm_service.generate_structured(
        CS_EVALUATION_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=True),
        CSFundamentalsLLMEvaluation,
        max_tokens=650,
        temperature=0.2,
    )
    if result:
        return result.as_graph_evaluation()

    next_question = llm_service.generate(
        "You are a strict but fair CS Fundamentals interviewer. The structured evaluator failed, "
        "so write only the next interviewer message in plain text. Respond to the candidate's actual intent, "
        "then ask at most one natural follow-up question.",
        json.dumps(payload, ensure_ascii=True),
        fallback="",
        temperature=0.35,
        max_tokens=180,
    ).strip()
    if not next_question:
        return None
    return {
        "evaluation_source": "llm_text_fallback",
        "scores": {},
        "verdict": "weak",
        "candidate_intent": "unknown",
        "should_repair_before_moving_on": True,
        "flags": [],
        "keyword_hits": [],
        "misconceptions": [],
        "evidence": [],
        "strengths": [],
        "missing_concepts": [],
<<<<<<< HEAD
=======
        "scratchpad_used": bool((scratchpad or {}).get("content", "").strip()),
>>>>>>> b2a9557 (WIP: saving local work before sync)
        "next_topic": topic.get("topic", ""),
        "next_subtopic": topic.get("subtopic", ""),
        "question_type": "followup",
        "next_question": next_question,
        "next_question_reason": "Structured LLM output could not be parsed; used natural LLM response.",
    }
