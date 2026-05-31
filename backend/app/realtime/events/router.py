from app.realtime.handlers.message_handler import (
    handle_candidate_message
)

from app.realtime.handlers.code_handler import (
    handle_code_event
)

from app.realtime.handlers.telemetry_handler import (
    handle_telemetry_event
)


EVENT_HANDLERS = {

    "candidate_message":
        handle_candidate_message,

    "code_change":
        handle_code_event,

    "telemetry":
        handle_telemetry_event,
}