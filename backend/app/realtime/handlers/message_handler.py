from app.realtime.sessions.session_manager import (
    session_manager
)

from app.orchestration.graph import (
    graph
)


async def handle_candidate_message(

    session_id: str,

    payload: dict,

):

    session = (
        session_manager.get_session(
            session_id
        )
    )

    if not session:

        return {

            "error":
                "Session not found"
        }

    candidate_message = (
        payload.get(
            "message",
            ""
        )
    )

    session[
        "latest_candidate_response"
    ] = candidate_message

    session["messages"].append(

        {

            "role": "candidate",

            "content":
                candidate_message,
        }
    )

    updated_state = await (
        graph.ainvoke(session)
    )

    session_manager.update_session(

        session_id,

        updated_state,
    )

    return {

        "type":
            "strategy_update",

        "payload": {

            "strategy":
                updated_state.get(
                    "interview_strategy",
                    {},
                ),

            "memory_summary":
                updated_state.get(
                    "memory_summary",
                    "",
                ),

            "suspected_bluffs":
                updated_state.get(
                    "suspected_bluffs",
                    [],
                ),

            "pressure_signals":
                updated_state.get(
                    "pressure_signals",
                    [],
                ),
        },
    }
