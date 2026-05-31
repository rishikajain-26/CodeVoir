from pydantic import BaseModel

from typing import List


class InterviewStrategy(BaseModel):

    pressure_level: float

    skepticism_level: float

    follow_up_intensity: float

    next_question_difficulty: str

    should_probe_deeper: bool

    should_switch_topic: bool

    focus_topics: List[str]

    reasoning: str