from fastapi import APIRouter
from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from app.realtime.websocket.manager import (
    manager
)

from app.realtime.events.router import (
    EVENT_HANDLERS
)


router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(

    websocket: WebSocket,

    session_id: str,

):

    await manager.connect(
        session_id,
        websocket,
    )

    try:

        while True:

            data = await (
                websocket.receive_json()
            )

            event_type = data.get(
                "event_type"
            )

            handler = EVENT_HANDLERS.get(
                event_type
            )

            if handler:

                response = await handler(

                    session_id,

                    data.get(
                        "payload",
                        {},
                    ),
                )

                await manager.send_message(

                    session_id,

                    response,
                )

            else:

                await manager.send_message(

                    session_id,

                    {
                        "type": "error",

                        "payload": {
                            "message":
                                f"Unknown event type: {event_type}"
                        },
                    },
                )

    except WebSocketDisconnect:

        manager.disconnect(
            session_id
        )