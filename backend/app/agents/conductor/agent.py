from app.agents.base_agent import BaseAgent

from app.orchestration.state import InterviewState


class ConductorAgent(BaseAgent):

    agent_name = "conductor"

    async def run(
        self,
        state: InterviewState,
    ) -> InterviewState:

        interview_mode = state.get(
    "interview_mode",
    "dsa",
)

        if interview_mode == "dsa":

            state["current_phase"] = (
                "problem_introduction"
            )

            state["interview_strategy"] = {
                "focus": "problem_solving",
                "difficulty": "medium",
                "pressure_level": 0,
            }

        elif interview_mode == "behavioral_project":

            state["current_phase"] = (
                "introduction"
            )

            state["interview_strategy"] = {
                "focus": "resume_validation",
                "difficulty": "medium",
                "pressure_level": 0,
            }

        return state