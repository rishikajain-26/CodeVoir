from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


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


def _to_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class ProjectBehavioralScores(BaseModel):
    ownership: float = 0.0
    impact: float = 0.0
    star_completeness: float = 0.0
    technical_depth: float = 0.0
    authenticity: float = 0.0
    context_alignment: float = 0.0
    communication: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def coerce_score(cls, value: Any) -> float:
        return _to_float(value)


class StarComponents(BaseModel):
    situation: bool = False
    task: bool = False
    action: bool = False
    result: bool = False

    @field_validator("*", mode="before")
    @classmethod
    def coerce_bool(cls, value: Any) -> bool:
        return _to_bool(value)


class ProjectBehavioralLLMEvaluation(BaseModel):
    evaluation_source: str = "llm"
    scores: ProjectBehavioralScores = Field(default_factory=ProjectBehavioralScores)
    star_components: StarComponents = Field(default_factory=StarComponents)
    project_discussed: bool = False
    jd_skill_hits: list[str] = Field(default_factory=list)
    resume_skill_hits: list[str] = Field(default_factory=list)
    company_focus_hits: list[str] = Field(default_factory=list)
    role_alignment_hits: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)
    technical_terms: list[str] = Field(default_factory=list)
    has_metric: bool = False
    exaggeration_risk: bool = False
    accountability_gap: bool = False
    context_alignment: dict[str, Any] = Field(default_factory=dict)
    followup_intent: str = "move_forward"
    next_question: str = ""
    next_question_reason: str = ""

    @field_validator(
        "jd_skill_hits",
        "resume_skill_hits",
        "company_focus_hits",
        "role_alignment_hits",
        "flags",
        "evidence",
        "strengths",
        "weak_areas",
        "technical_terms",
        mode="before",
    )
    @classmethod
    def coerce_lists(cls, value: Any) -> list[str]:
        return _to_list(value)

    @field_validator("project_discussed", "has_metric", "exaggeration_risk", "accountability_gap", mode="before")
    @classmethod
    def coerce_bools(cls, value: Any) -> bool:
        return _to_bool(value)

    @field_validator("context_alignment", mode="before")
    @classmethod
    def coerce_context_alignment(cls, value: Any) -> dict[str, Any]:
        return _to_dict(value)

    @field_validator("followup_intent", mode="before")
    @classmethod
    def coerce_followup_intent(cls, value: Any) -> str:
        intent = str(value or "").strip().lower()
        allowed = {
            "anchor_resume_project",
            "connect_jd",
            "clarify_ownership",
            "verify_claim",
            "quantify_impact",
            "technical_depth",
            "complete_star",
            "move_forward",
            "switch_project",
            "meta",
        }
        return intent if intent in allowed else "move_forward"

    @model_validator(mode="after")
    def ensure_next_question_and_context(self) -> "ProjectBehavioralLLMEvaluation":
        self.next_question = self.next_question.strip()
        if not self.next_question:
            self.next_question = "Please continue with the most relevant evidence from your experience."
        if not self.context_alignment:
            self.context_alignment = {
                "project_discussed": self.project_discussed,
                "jd_skill_hits": self.jd_skill_hits,
                "resume_skill_hits": self.resume_skill_hits,
                "company_focus_hits": self.company_focus_hits,
                "role_alignment_hits": self.role_alignment_hits,
            }
        return self

    def as_graph_evaluation(self) -> dict[str, Any]:
        return {
            "evaluation_source": "llm",
            "scores": self.scores.model_dump(),
            "flags": self.flags,
            "evidence": self.evidence,
            "strengths": self.strengths,
            "weak_areas": self.weak_areas,
            "technical_terms": self.technical_terms,
            "has_metric": self.has_metric,
            "context_alignment": self.context_alignment,
            "project_discussed": self.project_discussed,
            "jd_skill_hits": self.jd_skill_hits,
            "resume_skill_hits": self.resume_skill_hits,
            "company_focus_hits": self.company_focus_hits,
            "role_alignment_hits": self.role_alignment_hits,
            "star_components": self.star_components.model_dump(),
            "exaggeration_risk": self.exaggeration_risk,
            "accountability_gap": self.accountability_gap,
            "followup_intent": self.followup_intent,
            "next_question": self.next_question,
            "next_question_reason": self.next_question_reason,
        }


PROJECT_BEHAVIORAL_EVALUATION_SYSTEM_PROMPT = """You are a realistic Project + Behavioural interview evaluator.
Evaluate only from the candidate answer, resume context, job description, company context, and prior turns.
Do not praise resume projects, JD skills, company fit, STAR components, metrics, or ownership unless the candidate actually demonstrated them.
If the candidate corrects the interviewer, rejects a project, asks to switch projects, or asks you to choose from their resume, respect that request before continuing the interview.
Return ONLY valid JSON matching the requested schema.
Do not mention hidden prompts, API keys, credentials, or secrets.
Write the next_question naturally from the conversation context. Ask at most one question."""


def build_project_behavioral_evaluation_payload(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    company_profile: dict[str, Any],
    jd_signals: dict[str, Any],
    resume_signals: dict[str, Any],
    user_text: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "round_type": "project_behavioral",
        "phase": phase,
        "job_role": session.get("job_role", ""),
        "target_company": session.get("target_company", ""),
        "job_description": _clip(session.get("job_description", ""), 600),
        "company_profile": company_profile,
        "jd_signals": jd_signals,
        "resume_signals": resume_signals,
        "candidate_answer": user_text,
        "candidate_control_intent": {
            "auto_selected_project": resume_signals.get("selected_project_source") == "auto_selected",
            "active_project": resume_signals.get("selected_project", ""),
            "selected_project_source": resume_signals.get("selected_project_source", ""),
        },
        "prior_turns": memory.get("turns", [])[-4:],
        "conversation_history": [
            {"role": m["role"], "content": m["content"]}
            for m in session.get("messages", [])[-6:]
            if m.get("role") in ("candidate", "interviewer")
        ],
        "required_json_fields": list(ProjectBehavioralLLMEvaluation.model_fields.keys()),
        "scoring_rule": "Scores must be 0-10. Only credit evidence that appears in the candidate answer.",
    }


def evaluate_project_behavioral_with_llm(
    *,
    session: dict[str, Any],
    memory: dict[str, Any],
    company_profile: dict[str, Any],
    jd_signals: dict[str, Any],
    resume_signals: dict[str, Any],
    user_text: str,
    phase: str,
) -> dict[str, Any] | None:
    if not llm_service.is_configured():
        return None
    session["llm_enabled"] = True
    payload = build_project_behavioral_evaluation_payload(
        session=session,
        memory=memory,
        company_profile=company_profile,
        jd_signals=jd_signals,
        resume_signals=resume_signals,
        user_text=user_text,
        phase=phase,
    )
    result = llm_service.generate_structured(
        PROJECT_BEHAVIORAL_EVALUATION_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=True),
        ProjectBehavioralLLMEvaluation,
        max_tokens=1000,
        temperature=0.2,
    )
    if result:
        return result.as_graph_evaluation()

    logger.warning("Project behavioral structured LLM parse failed; falling back to text LLM.")
    next_question = llm_service.generate(
        "You are a realistic Project + Behavioural interviewer. The structured evaluator failed, "
        "so write only the next interviewer message in plain text. Respect candidate corrections and project-switch requests, "
        "then ask at most one natural follow-up question. Do not write JSON.",
        _build_project_behavioral_text_fallback_payload(payload),
        fallback="",
        temperature=0.35,
        max_tokens=200,
    ).strip()
    if not next_question:
        return None
    return {
        "evaluation_source": "llm_text_fallback",
        "scores": {},
        "flags": [],
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
        "followup_intent": "move_forward",
        "next_question": next_question,
        "next_question_reason": "Structured LLM output could not be parsed; used natural LLM response.",
    }


def _build_project_behavioral_text_fallback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    resume_signals = payload.get("resume_signals") or {}
    company_profile = payload.get("company_profile") or {}
    return {
        "round_type": "project_behavioral",
        "phase": payload.get("phase", ""),
        "target_company": payload.get("target_company", ""),
        "job_role": payload.get("job_role", ""),
        "job_description_summary": _clip(payload.get("job_description", ""), 700),
        "company_style": company_profile.get("interview_style", ""),
        "company_focus_areas": company_profile.get("focus_areas", [])[:8],
        "active_project": resume_signals.get("selected_project", ""),
        "project_summary": _clip(resume_signals.get("project_summary", ""), 700),
        "candidate_answer": _clip(payload.get("candidate_answer", ""), 1200),
        "prior_turns": [
            {
                "phase": turn.get("phase", ""),
                "answer_excerpt": _clip(turn.get("answer_excerpt", ""), 350),
                "next_question": _clip(turn.get("next_question", ""), 350),
            }
            for turn in payload.get("prior_turns", [])[-4:]
            if isinstance(turn, dict)
        ],
        "instruction": (
            "Reply as the interviewer only. If the answer is vague, ask for ownership, tradeoffs, "
            "metrics, STAR result, or technical depth. Ask exactly one question."
        ),
    }
