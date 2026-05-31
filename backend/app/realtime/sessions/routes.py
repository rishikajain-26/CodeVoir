from fastapi import APIRouter

from app.realtime.sessions.session_manager import (
    session_manager
)

from app.orchestration.state import (
    InterviewState
)


router = APIRouter()


@router.post("/session/create")
async def create_session():

    session_id = "test"

    initial_state: InterviewState = {

        "session_id": session_id,

        "interview_mode": "dsa",

        "current_phase": "introduction",

        "candidate_profile": {},

        "messages": [],

        "memory_summary": "",

        "technical_scores": {},

        "behavioral_scores": {},

        "communication_scores": {},

        "dsa_scores": {},

        "verified_strengths": [],

        "weak_areas": [],

        "contradiction_log": [],

        "suspected_bluffs": [],

        "pressure_signals": [],

        "confidence_indicators": [],

        "proctor_flags": [],

        "interview_strategy": {

            "pressure_level": 0,

            "skepticism_level": 0,

            "follow_up_intensity": 0,

            "next_focus": [],

            "should_probe_deeper": False,

            "should_switch_topic": False,
        },

        "coding_observations": [],

        "algorithmic_strengths": [],

        "algorithmic_weaknesses": [],

        "latest_candidate_response": "",

        "latest_interviewer_prompt": "",

        "active_question_id": "",

        "final_recommendation": "",
    }

    session_manager.create_session(

        session_id,

        initial_state,
    )

    return {

        "session_id": session_id
    }