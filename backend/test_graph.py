import asyncio

from app.orchestration.graph import graph


async def main():

    initial_state = {

        "session_id": "session_001",

        "interview_mode": "dsa",

        "current_phase": "",

        "candidate_profile": {},

        "messages": [],

        "memory_summary": "",

        "dsa_scores": {},

        "coding_observations": [],

        "algorithmic_strengths": [],

        "algorithmic_weaknesses": [],

        "technical_scores": {},

        "behavioral_scores": {},

        "communication_scores": {},

        "verified_strengths": [],

        "weak_areas": [],

        "contradiction_log": [],

        "suspected_bluffs": [],

        "pressure_signals": [],

        "confidence_indicators": [],

        "proctor_flags": [],

        "interview_strategy": {},

        "final_recommendation": "",
    }

    result = await graph.ainvoke(
        initial_state
    )

    print(result)


asyncio.run(main())