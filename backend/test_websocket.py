import asyncio
import json
import websockets

from app.realtime.sessions.session_manager import (
    session_manager
)


session_manager.create_session(

    "test",

    {

        "session_id": "test",

        "candidate_profile": {},

        "messages": [],

        "runtime": {

            "current_phase": "dsa",

            "next_action": "",

            "latest_candidate_response": "",

            "latest_interviewer_prompt": "",

            "active_question_id": "",

            "interview_mode": "dsa",
        },

        "scores": {

            "technical": {},

            "behavioral": {},

            "communication": {},

            "dsa": {},
        },

        "signals": {

            "contradictions": [],

            "suspected_bluffs": [],

            "pressure_signals": [],

            "confidence_indicators": [],

            "proctor_flags": [],
        },

        "memory": {

            "summary": "",

            "verified_strengths": [],

            "weak_areas": [],

            "topic_history": [],

            "important_claims": [],
        },

        "strategy": {

            "pressure_level": 0,

            "skepticism_level": 0,

            "follow_up_intensity": 0,

            "next_focus": [],

            "should_probe_deeper": False,

            "should_switch_topic": False,
        },

        "final_recommendation": "",
    }
)


async def main():

    uri = (
        "ws://localhost:8000/ws/test"
    )

    async with websockets.connect(
        uri
    ) as websocket:

        await websocket.send(

            json.dumps(

                {

                    "event_type":
                        "candidate_message",

                    "payload": {

                        "message":
                            "Redis replication is asynchronous."
                    },
                }
            )
        )

        response = await (
            websocket.recv()
        )

        print(response)


asyncio.run(main())