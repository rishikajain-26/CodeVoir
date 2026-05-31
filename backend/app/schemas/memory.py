from pydantic import BaseModel

from typing import List


class MemorySummary(BaseModel):

    candidate_strengths: List[str]

    candidate_weaknesses: List[str]

    important_claims: List[str]

    contradictions_detected: List[str]

    behavioral_signals: List[str]

    technical_topics_covered: List[str]

    overall_interview_direction: str

    recommended_focus_areas: List[str]

    summary: str