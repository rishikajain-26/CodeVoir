from app.runtime.execution.telemetry_tracker import (
    TelemetryTracker
)


tracker = TelemetryTracker()


async def handle_telemetry_event(

    session_id: str,

    payload: dict,

):

    tracker.add_event(

        event_type=payload.get(
            "event_type"
        ),

        content_delta=payload.get(
            "content_delta"
        ),

        cursor_position=payload.get(
            "cursor_position",
            0,
        ),
    )

    return {

        "type":
            "telemetry_ack",

        "payload": {

            "events_recorded":
                len(
                    tracker.get_events()
                )
        },
    }