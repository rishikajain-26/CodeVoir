from pydantic import BaseModel

from typing import List


class CodeRevision(BaseModel):

    revision_id: int

    code: str

    execution_result: str

    passed_testcases: int

    total_testcases: int

    execution_time_ms: float

    timestamp: float


class CodingBehaviorAnalysis(BaseModel):

    debugging_style: str

    optimization_awareness: str

    persistence_level: float

    panic_signals: List[str]

    brute_force_attempted: bool

    systematic_debugging: bool

    improvement_trajectory: str

    confidence_score: float

    reasoning: str