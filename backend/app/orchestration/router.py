from typing import Literal

from app.orchestration.state import (
    InterviewState
)


def phase_router(
    state: InterviewState,
) -> Literal[
    "dsa",
    "behavioral",
    "project",
    "pressure",
    "final"
]:

    strategy = state["strategy"]

    runtime = state["runtime"]

    signals = state["signals"]

    if len(
        signals["suspected_bluffs"]
    ) >= 2:

        return "pressure"

    if runtime["interview_mode"] == "dsa":

        return "dsa"

    return "behavioral"