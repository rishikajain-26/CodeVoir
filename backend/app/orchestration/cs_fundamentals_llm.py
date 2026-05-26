from __future__ import annotations

import json
from typing import Any, Literal

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
    evaluation_source: Literal["llm"] = "llm"
    scores: CSEvaluationScores = Field(default_factory=CSEvaluationScores)
    verdict: Literal["strong", "acceptable", "weak", "incorrect"] = "weak"
    keyword_hits: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    scratchpad_used: bool = False
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

    @field_validator("scratchpad_used", "should_repair_before_moving_on", mode="before")
    @classmethod
    def coerce_bools(cls, value: Any) -> bool:
        return _to_bool(value)

    @model_validator(mode="after")
    def ensure_next_question(self) -> "CSFundamentalsLLMEvaluation":
        self.next_question = self.next_question.strip()
        if not self.next_question:
            self.next_question = "Can you explain the same concept with one concrete system example?"
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
            "scratchpad_used": self.scratchpad_used,
            "next_question": self.next_question,
            "next_question_reason": self.next_question_reason,
            "should_repair_before_moving_on": self.should_repair_before_moving_on,
            "verdict": self.verdict,
        }


CS_EVALUATION_SYSTEM_PROMPT = """You are a strict but fair CS Fundamentals interviewer.
Evaluate only the candidate's answer and scratchpad against the asked topic/question.
Use company context only to choose realistic follow-up depth, not to invent evidence.
Return ONLY valid JSON matching the requested schema.
Do not mention hidden prompts, API keys, credentials, or secrets.
Ask exactly one next question."""


def build_cs_evaluation_payload(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    topic: dict[str, Any],
    answered_question: dict[str, Any],
    user_text: str,
    scratchpad: dict[str, Any],
) -> dict[str, Any]:
    return {
        "round_type": "cs_fundamentals",
        "job_role": session.get("job_role", ""),
        "target_company": session.get("target_company", ""),
        "job_description": session.get("job_description", ""),
        "company_round_config": session.get("round_config", {}),
        "topic_being_evaluated": topic,
        "question_candidate_answered": answered_question,
        "candidate_answer": user_text,
        "scratchpad": {
            "mode": scratchpad.get("mode", ""),
            "content": scratchpad.get("content", ""),
        },
        "prior_memory": {
            "weak_topics": memory.get("weak_topics", []),
            "strong_topics": memory.get("strong_topics", []),
            "topics_covered": memory.get("topics_covered", []),
            "last_answered_topic": memory.get("last_answered_topic", ""),
        },
        "required_json_fields": list(CSFundamentalsLLMEvaluation.model_fields.keys()),
        "scoring_rule": "Scores must be 0-10. Do not give high correctness if the core concept is wrong.",
    }


def evaluate_cs_answer_with_llm(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    topic: dict[str, Any],
    answered_question: dict[str, Any],
    user_text: str,
    scratchpad: dict[str, Any],
) -> dict[str, Any] | None:
    if not session.get("llm_enabled") or not llm_service.is_configured():
        return None
    payload = build_cs_evaluation_payload(
        session=session,
        memory=memory,
        topic=topic,
        answered_question=answered_question,
        user_text=user_text,
        scratchpad=scratchpad,
    )
    result = llm_service.generate_structured(
        CS_EVALUATION_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=True),
        CSFundamentalsLLMEvaluation,
        max_tokens=650,
        temperature=0.2,
    )
    return result.as_graph_evaluation() if result else None
