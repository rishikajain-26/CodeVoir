import asyncio

from app.dsa.state import DSAState, TurnScore
from app.orchestration.dsa_graph import run_dsa_turn_async


def _sample_graph_result(state: DSAState) -> dict:
    turn_score = TurnScore(
        understanding=0.7,
        approach_quality=0.75,
        complexity_accuracy=0.6,
        implementation=0.65,
        debugging=0.5,
        communication=0.8,
        behavioural=0.7,
        weighted_total=0.68,
    )
    dumped = state.model_dump()
    dumped.update(
        {
            "progress": {
                "current_question_index": 1,
                "total_questions": 2,
                "allocated_minutes": 45,
                "remaining_seconds": 2400,
                "label": "Question 1 of 2",
            },
            "turn_score": turn_score,
            "evaluation": {
                "correctness_score": 7.5,
                "optimization_score": 6.0,
                "debugging_score": 5.0,
                "communication_score": 8.0,
                "edge_case_handling_score": 6.5,
                "detected_strengths": ["clean structure"],
                "detected_weaknesses": ["missing boundary checks"],
                "follow_up_questions": ["What is the worst-case time complexity?"],
                "confidence_score": 7.0,
                "reasoning": "Mock graph evaluation.",
            },
            "comparison": {
                "alignment_score": 6.5,
                "expected_alignment_score": 8.5,
                "missing_concepts": ["early termination handling"],
                "extra_risk_flags": [],
                "recommended_improvements": ["add bounds checks"],
                "confidence_score": 7.0,
                "reasoning": "Mock comparison.",
            },
            "followup_question": "How would you change this implementation for very large inputs?",
            "interviewer_reply": "Good structure so far. How would you change this implementation for very large inputs?",
            "next_action": "next_turn",
            "candidate_intent": {
                "primary_intent": "continue",
                "should_give_hint": False,
                "should_advance_question": False,
                "should_end_round": False,
                "should_clarify_problem": False,
                "interviewer_focus": "Probe complexity.",
                "reasoning": "mock",
            },
        }
    )
    return dumped


async def _fake_graph_invoke(state):
    if isinstance(state, dict):
        state = DSAState.model_validate(state)
    return _sample_graph_result(state)


def test_dsa_graph_async_flow(monkeypatch):
    monkeypatch.setattr("app.orchestration.dsa_graph.DSA_GRAPH.ainvoke", _fake_graph_invoke)

    session = {"target_company": "TestCorp", "llm_enabled": True, "question_count": 1, "problem": {"prompt": "Find duplicate", "topics": ["hashing"]}}
    result = asyncio.run(
        run_dsa_turn_async(
            session=session,
            candidate_code="def solve(): pass",
            candidate_explanation="I traverse the array once and use a hash map.",
            problem_statement="Find the first repeated integer.",
            editor_context="# candidate is editing in Python",
        )
    )

    assert result["evaluation"]["correctness_score"] == 7.5
    assert result["comparison"]["alignment_score"] == 6.5
    assert "very large inputs" in result["followup"]
    assert session["dsa"]["latest_evaluation"]["confidence_score"] == 7.0
    assert session["dsa"]["graph_state"]


def test_dsa_graph_sync_wrapper(monkeypatch):
    monkeypatch.setattr("app.orchestration.dsa_graph.DSA_GRAPH.ainvoke", _fake_graph_invoke)

    from app.orchestration.dsa_graph import run_dsa_turn

    session = {"target_company": "TestCorp", "llm_enabled": True, "question_count": 1, "problem": {"prompt": "Find duplicate"}}
    result = run_dsa_turn(
        session=session,
        candidate_code="def solve(): pass",
        candidate_explanation="I use a two-pointer technique.",
        problem_statement="Find the first repeated integer.",
        editor_context="# candidate is editing in Python",
    )

    assert "edge cases" in result["followup"].lower() or "implementation" in result["followup"].lower()
    assert session["dsa"]["latest_followup"]
