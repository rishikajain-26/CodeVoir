from pydantic import BaseModel

from typing import List


class EditorEvent(BaseModel):

    timestamp: float

    event_type: str

    content_delta: str

    cursor_position: int


class TelemetryAnalysis(BaseModel):

    hesitation_score: float

    panic_score: float

    confidence_score: float

    suspected_copy_paste: bool

    debugging_maturity: str

    behavioral_signals: List[str]

    reasoning: str