from pydantic import BaseModel

from typing import Dict
from typing import Any


class InterviewEvent(BaseModel):

    event_type: str

    session_id: str

    payload: Dict[str, Any]

    timestamp: float