from typing import TypedDict
from typing import List
from typing import Dict
from typing import Any


class InterviewState(
    TypedDict
):

    # CORE

    session_id: str

    interview_mode: str

    current_phase: str

    # CANDIDATE

    candidate_profile: Dict[
        str,
        Any,
    ]

    # CONVERSATION

    messages: List[Dict]

    # MEMORY

    memory_summary: str

    verified_strengths: List[str]

    weak_areas: List[str]

    # SCORING

    technical_scores: Dict

    behavioral_scores: Dict

    communication_scores: Dict

    dsa_scores: Dict

    # SIGNALS

    contradiction_log: List[str]

    suspected_bluffs: List[str]

    pressure_signals: List[str]

    confidence_indicators: List[str]

    proctor_flags: List[str]

    # STRATEGY

    interview_strategy: Dict

    # DSA ANALYTICS

    coding_observations: List[str]

    algorithmic_strengths: List[str]

    algorithmic_weaknesses: List[str]

    # RUNTIME

    latest_candidate_response: str

    latest_interviewer_prompt: str

    active_question_id: str

    # FINAL

    final_recommendation: str