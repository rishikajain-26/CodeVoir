from langgraph.graph import StateGraph, END

from app.orchestration.state import InterviewState

from app.agents.conductor.agent import ConductorAgent
from app.orchestration.state import (
    InterviewState
)


conductor_agent = ConductorAgent()


async def conductor_node(state: InterviewState):

    return await conductor_agent.run(state)


def build_graph():

    workflow = StateGraph(InterviewState)

    workflow.add_node(
        "conductor",
        conductor_node,
    )

    workflow.set_entry_point("conductor")

    workflow.add_edge(
        "conductor",
        END,
    )

    return workflow.compile()


graph = build_graph()