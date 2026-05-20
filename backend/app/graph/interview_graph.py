from langgraph.graph import StateGraph
from langgraph.graph import END

from app.graph.state import (
    InterviewState
)

from app.agents.technical.evaluator import (
    evaluate_technical_response
)

from app.agents.contradiction.agent import (
    analyze_contradiction
)

from app.agents.strategy.agent import (
    generate_strategy
)

from app.agents.memory.agent import (
    generate_memory_summary
)


async def evaluator_node(
    state: InterviewState
):

    result = await (
        evaluate_technical_response(
            question="Explain Redis replication",

            candidate_answer=(
                state["candidate_response"]
            ),
        )
    )

    state["technical_evaluation"] = (
        result.model_dump()
    )

    return state


async def contradiction_node(
    state: InterviewState
):

    history = "\n".join(
        state["interview_history"]
    )

    result = await (
        analyze_contradiction(
            previous_claims=history,
            latest_answer=(
                state["candidate_response"]
            ),
        )
    )

    state["contradiction_analysis"] = (
        result.model_dump()
    )

    return state


async def strategy_node(
    state: InterviewState
):

    result = await (
        generate_strategy(

            technical_evaluation=str(
                state[
                    "technical_evaluation"
                ]
            ),

            contradiction_analysis=str(
                state[
                    "contradiction_analysis"
                ]
            ),
        )
    )

    state["strategy"] = (
        result.model_dump()
    )

    return state


async def memory_node(
    state: InterviewState
):

    history = "\n".join(
        state["interview_history"]
    )

    result = await (
        generate_memory_summary(
            conversation_history=history
        )
    )

    state["memory_summary"] = (
        result.model_dump()
    )

    return state


graph = StateGraph(
    InterviewState
)

graph.add_node(
    "evaluator",
    evaluator_node
)

graph.add_node(
    "contradiction",
    contradiction_node
)

graph.add_node(
    "strategy",
    strategy_node
)

graph.add_node(
    "memory",
    memory_node
)

graph.set_entry_point(
    "evaluator"
)

graph.add_edge(
    "evaluator",
    "contradiction"
)

graph.add_edge(
    "contradiction",
    "strategy"
)

graph.add_edge(
    "strategy",
    "memory"
)

graph.add_edge(
    "memory",
    END
)

interview_graph = graph.compile()