from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _to_bool(v: Any) -> bool:
    """Coerce truthy LLM strings ('Unknown', 'null', etc.) to bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"true", "yes", "1"}
    return False


def _to_str(v: Any) -> str:
    """Coerce None / non-string to empty string."""
    if v is None:
        return ""
    return str(v)


def _to_list(v: Any) -> list:
    """Coerce a scalar or mixed-type value to a list of non-empty strings.

    Every list field in these schemas is typed ``list[str]``. LLMs frequently
    emit booleans, numbers, or nulls inside these lists (e.g.
    ``edge_cases_identified_early: [true]``). Pydantic then rejects the element
    and the whole evaluation falls back to a keyword heuristic. Coercing each
    element to a string (and dropping stray bools/nulls) keeps the LLM's
    intelligent output instead of silently discarding it.
    """
    if v is None or v is False or v == "":
        return []
    items = v if isinstance(v, list) else [v]
    result: list[str] = []
    for item in items:
        if item is None or isinstance(item, bool):
            continue  # stray boolean/null is a format error, not list content
        text = str(item).strip()
        if text:
            result.append(text)
    return result


class UnderstandingLLM(BaseModel):
    time_to_first_clarification_s: float = 0.0
    clarifying_questions: list[str] = Field(default_factory=list)
    constraint_interpretation_correct: bool = True
    edge_cases_identified_early: list[str] = Field(default_factory=list)
    misunderstood_constraints: list[str] = Field(default_factory=list)
    score: float = 0.5
    # 0–1: how directly + correctly the reply answers the follow-up that was asked.
    # -1 means "no follow-up was pending, not applicable".
    answer_relevance: float = -1.0

    @field_validator("edge_cases_identified_early", "clarifying_questions", "misunderstood_constraints", mode="before")
    @classmethod
    def coerce_to_list(cls, v: Any) -> list:
        return _to_list(v)

    @field_validator("constraint_interpretation_correct", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("score", "time_to_first_clarification_s", "answer_relevance", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0


class ApproachLLM(BaseModel):
    brute_force_identified: bool = False
    brute_force_time: str = ""
    optimised_identified: bool = False
    approaches_attempted: int = 1
    final_optimal: bool = False
    data_structures: list[str] = Field(default_factory=list)
    patterns_recognised: list[str] = Field(default_factory=list)
    pattern_recognition_score: float = 0.0
    approach_quality_score: float = 0.0

    @field_validator("brute_force_time", mode="before")
    @classmethod
    def coerce_brute_force_time(cls, v: Any) -> str:
        return _to_str(v)

    @field_validator("brute_force_identified", "optimised_identified", "final_optimal", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("data_structures", "patterns_recognised", mode="before")
    @classmethod
    def coerce_to_list(cls, v: Any) -> list:
        return _to_list(v)

    @field_validator("pattern_recognition_score", "approach_quality_score", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @field_validator("approaches_attempted", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 1
        except (TypeError, ValueError):
            return 1


class ComplexityLLM(BaseModel):
    stated_time: str = ""
    stated_space: str = ""
    actual_time: str = ""
    actual_space: str = ""
    time_correct: bool = False
    space_correct: bool = False
    optimisation_awareness: bool = False
    tradeoff_discussion_quality: float = 0.0
    accuracy_score: float = 0.0

    @field_validator("stated_time", "stated_space", "actual_time", "actual_space", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return _to_str(v)

    @field_validator("time_correct", "space_correct", "optimisation_awareness", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("tradeoff_discussion_quality", "accuracy_score", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0


class ImplementationLLM(BaseModel):
    compilation_success: bool = False
    syntax_errors: int = 0
    runtime_errors: int = 0
    logical_bugs: int = 0
    code_complete: bool = False
    modular_score: float = 0.0
    naming_quality: float = 0.0
    readability_score: float = 0.0
    comment_quality: float = 0.0
    dead_code: bool = False
    redundant_loops: bool = False
    repeated_logic: bool = False
    boundary_checks: bool = False
    null_empty_checks: bool = False
    overflow_handling: bool = False

    @field_validator(
        "compilation_success", "code_complete", "dead_code", "redundant_loops",
        "repeated_logic", "boundary_checks", "null_empty_checks", "overflow_handling",
        mode="before",
    )
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("syntax_errors", "runtime_errors", "logical_bugs", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    @field_validator("modular_score", "naming_quality", "readability_score", "comment_quality", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0


class TestingLLM(BaseModel):
    test_cases_written: int = 0
    edge_case_coverage: float = 0.0
    adversarial_tests: int = 0
    visible_test_pass_pct: float = 0.0

    @field_validator("test_cases_written", "adversarial_tests", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    @field_validator("edge_case_coverage", "visible_test_pass_pct", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0


class DebugLLM(BaseModel):
    time_to_first_success_s: float = 0.0
    iterations: int = 0
    localisation_quality: float = 0.0
    strategy: Literal["print_debug", "systematic", "random", "none"] = "none"
    fixes_root_cause: bool = True
    uses_logging_well: bool = False

    @field_validator("fixes_root_cause", "uses_logging_well", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("strategy", mode="before")
    @classmethod
    def coerce_strategy(cls, v: Any) -> str:
        allowed = {"print_debug", "systematic", "random", "none"}
        if isinstance(v, str) and v.strip().lower() in allowed:
            return v.strip().lower()
        return "none"

    @field_validator("time_to_first_success_s", "localisation_quality", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @field_validator("iterations", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0


class PlagiarismLLM(BaseModel):
    plagiarism_likelihood: float = 0.0
    reasons: list[str] = Field(default_factory=list)

    @field_validator("plagiarism_likelihood", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @field_validator("reasons", mode="before")
    @classmethod
    def coerce_to_list(cls, v: Any) -> list:
        return _to_list(v)


class StrengthsLLM(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def coerce_to_list(cls, v: Any) -> list:
        return _to_list(v)


class CandidateIntentLLM(BaseModel):
    """What the candidate is trying to do this turn — drives routing, hints, and question advances."""

    primary_intent: Literal[
        "continue",
        "request_hint",
        "clarify_problem",
        "discuss_approach",
        "discuss_complexity",
        "review_submission",
        "advance_question",
        "end_interview",
        "express_stuck",
    ] = "continue"
    should_give_hint: bool = False
    should_advance_question: bool = False
    should_end_round: bool = False
    should_clarify_problem: bool = False
    interviewer_focus: str = ""
    reasoning: str = ""

    @field_validator("should_give_hint", "should_advance_question", "should_end_round", "should_clarify_problem", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("interviewer_focus", "reasoning", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return _to_str(v)

    @field_validator("primary_intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: Any) -> str:
        allowed = {
            "continue", "request_hint", "clarify_problem", "discuss_approach",
            "discuss_complexity", "review_submission", "advance_question",
            "end_interview", "express_stuck",
        }
        if isinstance(v, str) and v.strip().lower() in allowed:
            return v.strip().lower()
        return "continue"


class CandidateTurnIntentLLM(BaseModel):
    """Conversation-first classifier for what the candidate actually did this turn."""

    intent: Literal[
        "explaining_approach",
        "asking_clarification",
        "asking_hint",
        "submitting_code",
        "answering_followup",
        "meta_complaint",
        "change_topic",
        "idle",
    ] = "idle"
    summary: str = ""
    approach_correct: bool | None = None
    question_asked: str | None = None
    frustration_level: int = 0
    confidence: float = 0.7

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: Any) -> str:
        allowed = {
            "explaining_approach", "asking_clarification", "asking_hint",
            "submitting_code", "answering_followup", "meta_complaint",
            "change_topic", "idle",
        }
        if isinstance(v, str) and v.strip().lower() in allowed:
            return v.strip().lower()
        return "idle"

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v))) if v is not None else 0.7
        except (TypeError, ValueError):
            return 0.7

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return _to_str(v)

    @field_validator("frustration_level", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0


class SkillFeedbackItemLLM(BaseModel):
    """Per-skill feedback block used in the final report."""

    score: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def coerce_float(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v))) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @field_validator("strengths", "weaknesses", "recommendations", mode="before")
    @classmethod
    def coerce_to_list(cls, v: Any) -> list:
        return _to_list(v)


class SkillFeedbackLLM(BaseModel):
    """Four-skill weighted feedback (Comm 25%, Tech 30%, Problem-Solving 25%, Code Quality 20%)."""

    communication: SkillFeedbackItemLLM = Field(default_factory=SkillFeedbackItemLLM)
    technical: SkillFeedbackItemLLM = Field(default_factory=SkillFeedbackItemLLM)
    problem_solving: SkillFeedbackItemLLM = Field(default_factory=SkillFeedbackItemLLM)
    code_quality: SkillFeedbackItemLLM = Field(default_factory=SkillFeedbackItemLLM)


class RecommendationLLM(BaseModel):
    recommendation: Literal[
        "strong_hire",
        "hire",
        "lean_hire",
        "lean_reject",
        "reject",
        "insufficient_data",
    ] = "insufficient_data"
    rationale: str = ""

    @field_validator("recommendation", mode="before")
    @classmethod
    def coerce_recommendation(cls, v: Any) -> str:
        allowed = {"strong_hire", "hire", "lean_hire", "lean_reject", "reject", "insufficient_data"}
        if isinstance(v, str) and v.strip().lower() in allowed:
            return v.strip().lower()
        return "insufficient_data"

    @field_validator("rationale", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> str:
        return _to_str(v)
