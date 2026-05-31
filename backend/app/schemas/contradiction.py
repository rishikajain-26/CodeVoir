from pydantic import BaseModel

from typing import List


class ContradictionAnalysis(BaseModel):

    contradiction_detected: bool

    contradiction_reason: str

    severity_score: float

    suspected_bluffing: bool

    follow_up_question: str

    confidence_score: float

    related_topics: List[str]