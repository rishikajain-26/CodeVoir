from typing import TypedDict
from typing import List


class InterviewState(TypedDict):

    candidate_response: str

    technical_evaluation: dict

    contradiction_analysis: dict

    strategy: dict

    memory_summary: dict

    next_action: str

    interview_history: List[str]