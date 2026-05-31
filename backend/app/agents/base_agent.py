from abc import ABC, abstractmethod

from app.orchestration.state import InterviewState


class BaseAgent(ABC):

    agent_name: str = "base"

    @abstractmethod
    async def run(
        self,
        state: InterviewState,
    ) -> InterviewState:
        pass