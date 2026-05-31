from app.runtime.schemas.telemetry import (
    EditorEvent
)

import time


class TelemetryTracker:

    def __init__(self):

        self.events = []

    def add_event(

        self,

        event_type: str,

        content_delta: str,

        cursor_position: int,

    ):

        event = EditorEvent(

            timestamp=time.time(),

            event_type=event_type,

            content_delta=content_delta,

            cursor_position=cursor_position,
        )

        self.events.append(event)

    def get_events(self):

        return self.events