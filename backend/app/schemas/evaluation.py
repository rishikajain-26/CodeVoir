from pydantic import BaseModel

from typing import List


class TechnicalEvaluation(BaseModel):

    technical_depth_score: float

    system_design_score: float

    problem_solving_score: float

    detected_strengths: List[str]

    detected_weaknesses: List[str]

    follow_up_topics: List[str]

    confidence_score: float

    suspected_bluffing: bool

    reasoning: str


class BehavioralEvaluation(BaseModel):

    communication_score: float

    leadership_score: float

    ownership_score: float

    collaboration_score: float

    confidence_score: float

    detected_strengths: List[str]

    detected_weaknesses: List[str]

    behavioral_signals: List[str]

    reasoning: str


class DSAEvaluation(BaseModel):

    correctness_score: float

    optimization_score: float

    debugging_score: float

    communication_score: float

    edge_case_handling_score: float

    detected_strengths: List[str]

    detected_weaknesses: List[str]

    follow_up_questions: List[str]

    confidence_score: float

    reasoning: str


class DSAComparison(BaseModel):

    alignment_score: float

    expected_alignment_score: float

    missing_concepts: List[str]

    extra_risk_flags: List[str]

    recommended_improvements: List[str]

    confidence_score: float

    reasoning: str


class DSAFollowUp(BaseModel):

    follow_up_question: str