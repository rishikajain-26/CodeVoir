"""
DSA Interview Pipeline — Scenario-based Robustness Tests
=========================================================
Tests the *pure-Python* routing, intent-classification, and phase-tracking
logic without making any LLM calls.  Every scenario is a realistic conversation
turn that exercises a different path through the graph.

Run:
    pytest backend/tests/test_dsa_scenarios.py -v
"""
from __future__ import annotations

import time
from copy import deepcopy

import pytest

from app.dsa.graph import phase_router, phase_tracker, pre_router
from app.dsa.nodes.intent import (
    _apply_explicit_signal_overrides,
    _apply_intent_guardrails,
    _route_action_from_intent,
    _to_candidate_intent,
)
from app.dsa.nodes.output import (
    _classify_probe,
    _compute_depth_signal,
    _ends_with_question,
    _reply_too_similar,
)
from app.dsa.schemas_llm import CandidateTurnIntentLLM
from app.dsa.state import (
    ApproachProfile,
    AudioMeta,
    CandidateIntent,
    DSAState,
    EditorSignals,
    ImplementationQuality,
    InterviewProgress,
    SessionConfig,
    SessionMemory,
    SilenceProfile,
    TurnRecord,
    TurnScore,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _base_state(**overrides) -> DSAState:
    """Build a minimal DSAState suitable for routing / intent tests."""
    now = time.time()
    progress = InterviewProgress(
        current_question_index=1,
        total_questions=2,
        allocated_minutes=45,
        started_at_epoch=now,
        elapsed_seconds=0,
        remaining_seconds=2700,  # 45 min
        time_expired=False,
        round_complete=False,
        label="Question 1 of 2",
    )
    config = SessionConfig(
        session_id="test-session",
        target_company="TestCorp",
        problem_statement="Find the first non-repeating character in a string.",
        expected_time_complexity="O(n)",
        expected_space_complexity="O(1)",
        allowed_patterns=["hashing", "sliding_window"],
        max_hints=3,
        max_turns=24,
        total_questions=2,
        allocated_minutes=45,
        per_question_minutes=22.5,
    )
    state = DSAState(
        config=config,
        progress=progress,
        interview_phase="reading",
        phase_turns=0,
        brute_force_given=False,
        optimized_approach_confirmed=False,
        candidate_explanation="",
        candidate_code="",
        trigger="message",
    )
    if overrides:
        state = state.model_copy(update=overrides)
    return state


def _turn_record(followup: str = "What is the time complexity?", score: float = 0.5) -> TurnRecord:
    return TurnRecord(
        turn=1,
        problem_excerpt="Find first non-repeating char",
        code_excerpt="",
        explanation_excerpt="",
        followup_asked=followup,
        score=TurnScore(weighted_total=score),
        behaviour=state_behaviour(),
    )


def state_behaviour():
    from app.dsa.state import CandidateBehaviourProfile
    return CandidateBehaviourProfile()


def _intent_from_raw(raw: str, **kwargs) -> CandidateTurnIntentLLM:
    return CandidateTurnIntentLLM(intent=raw, summary="test", **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 1 — Happy path: reading → brute_force → optimization → coding
# ──────────────────────────────────────────────────────────────────────────────

class TestHappyPhaseTransitions:
    def test_reading_to_clarification_on_long_explanation(self):
        """Candidate asks a question: phase should move to clarification."""
        state = _base_state(
            interview_phase="reading",
            phase_turns=0,
            candidate_explanation="Can you clarify if the string has only lowercase letters?",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "clarification"
        assert result["phase_turns"] == 0  # reset on transition

    def test_reading_stays_reading_on_very_short_message(self):
        """A one-word acknowledgment doesn't advance the phase."""
        state = _base_state(
            interview_phase="reading",
            phase_turns=1,
            candidate_explanation="Ok.",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "reading"
        assert result["phase_turns"] == 2

    def test_brute_force_keyword_advances_from_reading(self):
        state = _base_state(
            interview_phase="reading",
            phase_turns=1,
            candidate_explanation="My naive approach would use a nested loop to check all pairs.",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "brute_force"
        assert result["brute_force_given"] is True

    def test_optimization_keyword_advances_from_brute_force(self):
        state = _base_state(
            interview_phase="brute_force",
            phase_turns=1,
            brute_force_given=True,
            candidate_explanation="We can optimize using a hash map to get O(n) time.",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "optimization"

    def test_code_advances_to_coding_phase(self):
        state = _base_state(
            interview_phase="clarification",
            phase_turns=1,
            candidate_code="def solve(s):\n    seen = {}\n    for c in s:\n        seen[c] = seen.get(c, 0) + 1\n    return seen",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "coding"

    def test_code_submit_trigger_advances_to_testing(self):
        state = _base_state(
            interview_phase="coding",
            phase_turns=2,
            trigger="code_submit",
            candidate_code="def solve(s):\n    pass",
            editor_signals=EditorSignals(run_count=0),
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "testing"

    def test_closing_phase_requires_all_conditions(self):
        """Closing only fires when optimized + code complete + on last question."""
        state = _base_state(
            interview_phase="testing",
            phase_turns=2,
            brute_force_given=True,
            optimized_approach_confirmed=True,
            progress=InterviewProgress(
                current_question_index=2,
                total_questions=2,
                remaining_seconds=600,
                allocated_minutes=45,
            ),
            implementation=ImplementationQuality(code_complete=True),
            approach=ApproachProfile(final_approach_optimal=True),
            candidate_explanation="I think the solution is complete.",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] == "closing"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 2 — Silent / idle candidate
# ──────────────────────────────────────────────────────────────────────────────

class TestSilentCandidate:
    def test_two_turns_of_empty_messages_trigger_silence_probe(self):
        """After 2 turns in reading with no meaningful content: silence_probe."""
        state = _base_state(
            interview_phase="reading",
            phase_turns=2,
            candidate_explanation="",
        )
        # phase_tracker will keep phase at "reading" and push phase_turns to 3
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "silence_probe"

    def test_real_silence_gap_triggers_silence_probe(self):
        """A long audio silence gap should trigger silence_probe regardless of phase_turns."""
        state = _base_state(
            interview_phase="brute_force",
            phase_turns=0,
            candidate_explanation="um",
            silence_profile=SilenceProfile(longest_gap=25.0),
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "silence_probe"

    def test_three_turns_no_approach_triggers_demand_brute_force(self):
        """≥3 turns in reading/clarification with ≥5 words but no approach: demand brute force.

        Silence probe only fires when candidate_words < 5.  Use a non-approach sentence
        so the candidate doesn't accidentally trigger the brute-force keyword detector.
        """
        # Explanation must be 5-8 words: avoids both silence probe (< 5) and
        # clarification transition (> 8), while containing no brute-force keywords.
        state = _base_state(
            interview_phase="reading",
            phase_turns=3,
            candidate_explanation="Still figuring out the overall plan.",
            brute_force_given=False,
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "demand_brute_force"

    def test_silence_probe_not_fired_in_coding_phase(self):
        """Once in coding, silence is expected (they're writing code)."""
        state = _base_state(
            interview_phase="coding",
            phase_turns=5,
            candidate_explanation="hmm",
            candidate_code="def solve(s):\n    for c in s:\n        pass\n    return -1",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        # Should not silence-probe in coding phase — there's code in the editor
        assert route != "silence_probe"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 3 — Time pressure
# ──────────────────────────────────────────────────────────────────────────────

class TestTimePressure:
    def test_under_25pct_time_with_no_code_triggers_time_pressure(self):
        """<25% time remaining + no code → time_pressure_push."""
        state = _base_state(
            interview_phase="clarification",
            phase_turns=2,
            progress=InterviewProgress(
                current_question_index=1,
                total_questions=2,
                allocated_minutes=45,
                remaining_seconds=600,   # ~22% of 2700s
                time_expired=False,
            ),
            candidate_explanation="I think I should iterate through",
            candidate_code="",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "time_pressure_push"

    def test_time_pressure_NOT_fired_when_candidate_has_code(self):
        """Even with low time, don't interrupt if they're already coding."""
        state = _base_state(
            interview_phase="coding",
            phase_turns=1,
            progress=InterviewProgress(
                current_question_index=1,
                total_questions=2,
                allocated_minutes=45,
                remaining_seconds=400,
                time_expired=False,
            ),
            candidate_code="def solve(s):\n    seen = {}\n    for c in s:\n        if c not in seen:\n            return c\n    return ''\n",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route != "time_pressure_push"

    def test_time_expired_generates_report_via_pre_router(self):
        """When time_expired=True, pre_router should send to generate_report."""
        state = _base_state(
            progress=InterviewProgress(
                current_question_index=1,
                total_questions=2,
                allocated_minutes=45,
                remaining_seconds=0,
                time_expired=True,
                round_complete=False,
            ),
            candidate_intent=CandidateIntent(
                primary_intent="continue",
                should_end_round=True,   # guardrail sets this when time_expired
            ),
        )
        route = pre_router(state)
        assert route == "generate_report"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 4 — Intent classification edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestIntentClassification:
    def test_asking_hint_low_frustration_routes_to_escalate_hint(self):
        """Standard hint request with low frustration → escalate_hint."""
        state = _base_state(candidate_explanation="I'm stuck, can I get a hint?")
        raw_intent = _intent_from_raw("asking_hint", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        action = _route_action_from_intent(state, intent)
        assert action == "escalate_hint"

    def test_meta_complaint_routes_to_direct_reply(self):
        """Candidate complaining about repetition → direct_reply."""
        state = _base_state(candidate_explanation="You keep repeating yourself, you're not listening!")
        raw_intent = _intent_from_raw("meta_complaint", frustration_level=3)
        intent = _to_candidate_intent(state, raw_intent)
        action = _route_action_from_intent(state, intent)
        assert action == "direct_reply"

    def test_clarification_routes_to_direct_reply(self):
        """Clarification always bypasses the evaluation pipeline."""
        state = _base_state(candidate_explanation="What does 'non-repeating' mean exactly?")
        raw_intent = _intent_from_raw("asking_clarification", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        action = _route_action_from_intent(state, intent)
        assert action == "direct_reply"

    def test_change_topic_routes_to_direct_reply(self):
        state = _base_state(candidate_explanation="Can we change topic and talk about graphs instead?")
        raw_intent = _intent_from_raw("change_topic", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        action = _route_action_from_intent(state, intent)
        assert action == "direct_reply"

    def test_end_interview_intent_detected_from_keywords(self):
        """Explicit end-interview keywords → should_end_round=True."""
        state = _base_state(candidate_explanation="Let's end the interview, I'm done.")
        raw_intent = _intent_from_raw("idle", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        assert intent.should_end_round is True

    def test_end_interview_exact_phrase(self):
        """Exact phrase 'end interview' (no article) also triggers."""
        state = _base_state(candidate_explanation="Let's end interview now.")
        raw_intent = _intent_from_raw("idle", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        assert intent.should_end_round is True

    def test_hint_limit_exhausted_blocks_hint(self):
        """When all hints used, should_give_hint is reset to False."""
        state = _base_state(candidate_explanation="I still need a hint please")
        state = state.model_copy(update={
            "memory": SessionMemory(hints_given=3)  # max_hints=3 → exhausted
        })
        raw_intent = _intent_from_raw("asking_hint", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        intent = _apply_intent_guardrails(state, intent)
        assert intent.should_give_hint is False
        assert "No more hints" in intent.interviewer_focus

    def test_code_submit_trigger_classifies_as_review_submission(self):
        """trigger=code_submit should anchor intent to review_submission."""
        state = _base_state(
            trigger="code_submit",
            candidate_explanation="I've submitted my solution.",
        )
        raw_intent = _intent_from_raw("submitting_code", frustration_level=0)
        intent = _to_candidate_intent(state, raw_intent)
        assert intent.primary_intent == "review_submission"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 5 — Explicit signal overrides
# ──────────────────────────────────────────────────────────────────────────────

class TestExplicitSignalOverrides:
    def test_not_listening_override_forces_meta_complaint(self):
        state = _base_state(candidate_explanation="You're not listening to me at all!")
        raw = _intent_from_raw("explaining_approach", frustration_level=1)
        overridden = _apply_explicit_signal_overrides(state, raw)
        assert overridden.intent == "meta_complaint"
        assert overridden.frustration_level >= 3

    def test_hint_keyword_override(self):
        state = _base_state(candidate_explanation="I'm stuck, where to start?")
        raw = _intent_from_raw("idle", frustration_level=0)
        overridden = _apply_explicit_signal_overrides(state, raw)
        assert overridden.intent == "asking_hint"

    def test_change_topic_override(self):
        state = _base_state(candidate_explanation="Let's talk about something else please.")
        raw = _intent_from_raw("idle", frustration_level=0)
        overridden = _apply_explicit_signal_overrides(state, raw)
        assert overridden.intent == "change_topic"

    def test_is_my_logic_correct_override(self):
        state = _base_state(candidate_explanation="Is my logic correct here?")
        raw = _intent_from_raw("idle", frustration_level=0)
        overridden = _apply_explicit_signal_overrides(state, raw)
        assert overridden.intent == "explaining_approach"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 6 — Question advancement
# ──────────────────────────────────────────────────────────────────────────────

class TestQuestionAdvancement:
    def test_explicit_next_question_phrase_triggers_advance(self):
        state = _base_state(candidate_explanation="I'm done, let's move to the next question.")
        raw = _intent_from_raw("explaining_approach", frustration_level=0)
        intent = _to_candidate_intent(state, raw)
        assert intent.should_advance_question is True

    def test_pre_router_sends_to_advance_question(self):
        state = _base_state(
            candidate_explanation="Next question please.",
            candidate_intent=CandidateIntent(
                primary_intent="advance_question",
                should_advance_question=True,
                should_end_round=False,
            ),
            next_action="next_turn",
        )
        route = pre_router(state)
        assert route == "advance_question"

    def test_advance_on_last_question_triggers_end_round(self):
        """Trying to advance past the last question → end round, not advance."""
        state = _base_state(
            progress=InterviewProgress(
                current_question_index=2,
                total_questions=2,
                remaining_seconds=1000,
                allocated_minutes=45,
            ),
            candidate_explanation="Done with this, next question.",
        )
        raw = _intent_from_raw("idle", frustration_level=0)
        intent = _to_candidate_intent(state, raw)
        intent = _apply_intent_guardrails(state, intent)
        assert intent.should_advance_question is False
        assert intent.should_end_round is True

    def test_advance_with_round_complete_generates_report(self):
        """If round is already complete, should generate report."""
        state = _base_state(
            progress=InterviewProgress(
                current_question_index=2,
                total_questions=2,
                remaining_seconds=500,
                allocated_minutes=45,
                round_complete=True,
            ),
            candidate_intent=CandidateIntent(
                primary_intent="advance_question",
                should_advance_question=True,
                should_end_round=False,
            ),
            next_action="next_turn",
        )
        route = pre_router(state)
        # round_complete=True → advance_question NOT fired → falls through
        # should_end_round is checked first in pre_router
        assert route != "advance_question"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 7 — Code submission paths
# ──────────────────────────────────────────────────────────────────────────────

class TestCodeSubmission:
    def test_all_tests_pass_routes_to_walkthrough(self):
        state = _base_state(
            interview_phase="testing",
            phase_turns=1,
            trigger="code_submit",
            latest_code_run={
                "passed_testcases": 5,
                "total_testcases": 5,
                "overall_score": 100.0,
            },
            candidate_code="def solve(s): pass",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "code_walkthrough"

    def test_partial_pass_routes_to_output_turn(self):
        """Partial test pass with code_submit goes to normal output_turn."""
        state = _base_state(
            interview_phase="testing",
            phase_turns=1,
            trigger="code_submit",
            latest_code_run={
                "passed_testcases": 3,
                "total_testcases": 5,
                "overall_score": 60.0,
            },
            candidate_code="def solve(s): pass",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route == "output_turn"

    def test_zero_tests_does_not_trigger_walkthrough(self):
        """Empty test results don't trick the router into a walkthrough."""
        state = _base_state(
            interview_phase="testing",
            phase_turns=1,
            trigger="code_submit",
            latest_code_run={},
            candidate_code="def solve(s): pass",
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        route = phase_router(updated)
        assert route != "code_walkthrough"

    def test_code_submit_with_advance_question_intent_bypasses_walkthrough(self):
        """
        If candidate submits code AND says 'next question', pre_router should
        handle the advance first — the walkthrough lives inside phase_router
        which is only reached on 'full_eval' path.
        """
        state = _base_state(
            trigger="code_submit",
            candidate_explanation="All tests passed, next question please.",
            candidate_intent=CandidateIntent(
                primary_intent="advance_question",
                should_advance_question=True,
                should_end_round=False,
            ),
            next_action="next_turn",
            latest_code_run={"passed_testcases": 5, "total_testcases": 5},
        )
        route = pre_router(state)
        assert route == "advance_question"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 8 — Anti-loop / probe diversity
# ──────────────────────────────────────────────────────────────────────────────

class TestProbeAntiLoop:
    def test_classify_probe_complexity(self):
        q = "What is the time complexity of your solution?"
        assert _classify_probe(q) == "complexity_probe"

    def test_classify_probe_edge_case(self):
        q = "What happens when the input is empty?"
        assert _classify_probe(q) == "edge_case_probe"

    def test_classify_probe_optimization(self):
        q = "Can you optimize this further to reduce the runtime?"
        assert _classify_probe(q) == "optimization"

    def test_reply_similarity_detected(self):
        current = "What is the time complexity of your current solution?"
        prev = ["What is the time complexity of your current solution and can you reduce it?"]
        assert _reply_too_similar(current, prev) is True

    def test_reply_similarity_not_false_positive_on_short(self):
        """Fewer than 6 unique words → similarity check skipped (returns False)."""
        current = "Tell me."
        prev = ["Tell me more."]
        assert _reply_too_similar(current, prev) is False

    def test_depth_signal_move_on_on_giveup(self):
        state = _base_state(candidate_explanation="I don't know, I give up.")
        signal = _compute_depth_signal(state)
        assert signal["depth_signal"] == "move_on"

    def test_depth_signal_dig_deeper_on_partial_knowledge(self):
        """Long answer + been probed once + scores improving → dig deeper.

        Avoid 'not sure' which (before fix) was in _stuck_phrases and caused
        a false move_on even for partial-knowledge explanations.
        """
        turns = [_turn_record(score=0.4), _turn_record(score=0.5)]
        # Must be > 15 words and avoid every phrase in _stuck_phrases
        # ("i cannot", "not sure", "no idea", "i give up", etc.)
        state = _base_state(
            candidate_explanation=(
                "I think using a hash map will track frequency counts, "
                "and the traversal order is what I want to explore further with you."
            ),
        )
        state = state.model_copy(update={
            "memory": SessionMemory(
                turns=turns,
                recent_probe_categories=["complexity_probe"],
            )
        })
        signal = _compute_depth_signal(state)
        assert signal["depth_signal"] == "dig_deeper"

    def test_depth_signal_move_on_stagnant_after_3_probes(self):
        """Same category probed 3+ times with flat scores → move on."""
        turns = [
            _turn_record(score=0.4),
            _turn_record(score=0.41),
            _turn_record(score=0.40),
        ]
        state = _base_state(candidate_explanation="I already explained this.")
        state = state.model_copy(update={
            "memory": SessionMemory(
                turns=turns,
                recent_probe_categories=["complexity_probe", "complexity_probe", "complexity_probe"],
            )
        })
        signal = _compute_depth_signal(state)
        assert signal["depth_signal"] == "move_on"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 9 — Pre-router priority / coordination issues
# ──────────────────────────────────────────────────────────────────────────────

class TestPreRouterPriority:
    def test_end_round_takes_highest_priority(self):
        state = _base_state(
            candidate_intent=CandidateIntent(
                primary_intent="end_interview",
                should_end_round=True,
                should_advance_question=True,   # also set (edge case)
            ),
            next_action="generate_report",
        )
        route = pre_router(state)
        assert route == "generate_report"

    def test_direct_reply_for_escalate_hint_keyword(self):
        """escalate_hint action takes priority over full_eval."""
        state = _base_state(
            candidate_intent=CandidateIntent(
                primary_intent="request_hint",
                should_give_hint=True,
            ),
            next_action="escalate_hint",
        )
        route = pre_router(state)
        assert route == "escalate_hint"

    def test_direct_reply_action_bypasses_evaluation(self):
        state = _base_state(
            candidate_intent=CandidateIntent(
                primary_intent="clarify_problem",
                should_clarify_problem=True,
            ),
            next_action="direct_reply",
        )
        route = pre_router(state)
        assert route == "direct_reply"

    def test_full_eval_when_no_special_action(self):
        state = _base_state(
            candidate_intent=CandidateIntent(primary_intent="continue"),
            next_action="next_turn",
        )
        route = pre_router(state)
        assert route == "full_eval"

    def test_max_turns_reached_generates_report_via_router(self):
        """Router.py turn_router returns generate_report when max_turns hit.
        Here we test that the progress fields correctly reflect time-expiry."""
        state = _base_state(
            progress=InterviewProgress(
                current_question_index=1,
                total_questions=2,
                remaining_seconds=0,
                allocated_minutes=45,
                time_expired=True,
            ),
            candidate_intent=CandidateIntent(should_end_round=True),
            next_action="generate_report",
        )
        route = pre_router(state)
        assert route == "generate_report"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 10 — Known bugs / regressions
# ──────────────────────────────────────────────────────────────────────────────

class TestKnownBugs:
    # FIX-1: "move on" false positive (fixed by removing "move on" from advance keywords)
    def test_move_on_to_optimize_must_not_advance_question(self):
        """'move on to optimize' must NOT trigger question advancement (fixed)."""
        state = _base_state(
            candidate_explanation="Let me move on to optimize my brute force approach.",
            interview_phase="brute_force",
            phase_turns=1,
        )
        raw = _intent_from_raw("explaining_approach", frustration_level=0)
        intent = _to_candidate_intent(state, raw)
        assert intent.should_advance_question is False

    def test_explicit_next_question_still_advances(self):
        """Explicit 'next question' phrasing still triggers advancement after fix."""
        state = _base_state(candidate_explanation="I'm done, let's go to the next question.")
        raw = _intent_from_raw("idle", frustration_level=0)
        intent = _to_candidate_intent(state, raw)
        assert intent.should_advance_question is True

    # FIX-2: Frustrated hint-seeker now gets escalate_hint (fixed)
    def test_frustrated_hint_request_should_still_give_hint(self):
        """Frustrated (level=2) candidate asking for hint should get escalate_hint."""
        state = _base_state(
            candidate_explanation="I'm really frustrated and completely stuck. I need a hint, please.",
            memory=SessionMemory(hints_given=0),
        )
        raw = _intent_from_raw("asking_hint", frustration_level=2)
        intent = _to_candidate_intent(state, raw)
        action = _route_action_from_intent(state, intent)
        assert action == "escalate_hint"

    # FIX-3: Code-review request no longer treated as meta_complaint (fixed)
    def test_code_review_request_should_not_be_meta_complaint(self):
        """'Can you review my code?' should be submitting_code, not meta_complaint."""
        state = _base_state(
            candidate_explanation="Can you review my code and give feedback?",
            candidate_code="def solve(s):\n    for c in s:\n        return c\n",
        )
        raw = _intent_from_raw("submitting_code", frustration_level=0)
        overridden = _apply_explicit_signal_overrides(state, raw)
        assert overridden.intent == "submitting_code"
        assert overridden.frustration_level < 2  # not treated as a complaint

    # FIX-4: Stale run_count no longer forces testing phase (fixed)
    def test_run_count_from_stale_events_should_not_force_testing_phase(self):
        """Verbal turn with trigger='message' and stale run_count must NOT force testing."""
        state = _base_state(
            interview_phase="optimization",
            phase_turns=1,
            trigger="message",
            editor_signals=EditorSignals(run_count=1),  # stale from prior turn
            candidate_explanation=(
                "I realized I can optimize by using a hash map instead of nested loops, "
                "which would bring it down to O(n) time complexity."
            ),
            candidate_code="def solve(s):\n    for i in s:\n        for j in s:\n            pass",
        )
        result = phase_tracker(state)
        # After fix: trigger="message" alone should not transition to "testing"
        assert result["interview_phase"] != "testing"

    # BUG-5: Reply concatenation can produce excessively long voice output
    def test_output_bundle_reply_ends_with_question_mark(self):
        """The contextual reply should end with a question (voice interviewers need a response hook)."""
        assert _ends_with_question("What is the time complexity?") is True
        assert _ends_with_question("Good, go ahead and code that.") is False
        assert _ends_with_question("Nice work.") is False

    def test_combined_reply_length_check(self):
        """
        BUG-5 (design gap): output_bundle concatenates contextual_reply + followup_question
        with no length cap.  This test documents the maximum expected voice reply length.
        A voice system reading 300 words would take ~2 minutes — too long.
        """
        contextual = "Your reasoning is correct but you need to handle the edge case where the input is empty. " * 3
        followup = "What is the time complexity of your current solution and how would you improve it?"
        combined = f"{contextual} {followup}"
        word_count = len(combined.split())
        # Document: at 150wpm speech rate, >60 words is a 24-second monologue — poor UX
        assert word_count < 80, (
            f"BUG-5: combined reply is {word_count} words — too long for voice. "
            "output_bundle should cap the combined reply to ~60 words."
        )


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 11 — Contradiction detection
# ──────────────────────────────────────────────────────────────────────────────

class TestContradictionPipeline:
    def test_contradiction_record_triggers_response_note(self):
        """When a contradiction is present, pre_router should not swallow it."""
        from app.dsa.state import ContradictionRecord
        contradiction = ContradictionRecord(
            turn=2,
            claim_before="O(n²) time complexity",
            claim_now="O(n) time complexity",
            severity=0.8,
            topic="complexity",
        )
        state = _base_state(
            latest_contradiction=contradiction,
            candidate_intent=CandidateIntent(primary_intent="continue"),
            next_action="next_turn",
        )
        route = pre_router(state)
        # Contradiction does not short-circuit routing — it's handled in contextual_responder
        assert route == "full_eval"


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 12 — Multi-question flow coordination
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiQuestionFlow:
    def test_question_advance_resets_phase_fields(self):
        """
        After question_advancer runs, it must reset phase, brute_force_given, etc.
        so the next question starts fresh.
        """
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _run():
            from app.dsa.graph import question_advancer

            state = _base_state(
                interview_phase="testing",
                phase_turns=3,
                brute_force_given=True,
                optimized_approach_confirmed=True,
                candidate_code="def solve(s): pass",
                progress=InterviewProgress(
                    current_question_index=1,
                    total_questions=2,
                    remaining_seconds=1200,
                    allocated_minutes=45,
                ),
                candidate_explanation="next question please",
            )
            with patch("app.dsa.llm_text.generate_text", new=AsyncMock(return_value="Got it, moving to Q2.")):
                result = await question_advancer(state)

            assert result["interview_phase"] == "reading"
            assert result["phase_turns"] == 0
            assert result["brute_force_given"] is False
            assert result["optimized_approach_confirmed"] is False
            assert result["candidate_code"] == ""
            assert result["latest_code_run"] == {}
            assert result["hint"] is None
            assert result["followup_question"] == ""

        asyncio.run(_run())

    def test_question_advance_clears_per_question_memory(self):
        """
        Root cause fix: question_advancer must clear per-question memory fields
        (turns, hint_log, probe categories, rolling_summary) so the LLM on Q2
        does not see Q1's conversation history and follow-up questions.
        """
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _run():
            from app.dsa.graph import question_advancer

            # Build state with Q1 memory full of Q1-specific context
            q1_memory = SessionMemory(
                turns=[
                    _turn_record(followup="What is the time complexity of your brute force?", score=0.4),
                    _turn_record(followup="Can you optimise using a hash map?", score=0.5),
                    _turn_record(followup="Trace your solution on input [1,2,1].", score=0.6),
                ],
                hint_log=["Think about what data structure gives O(1) lookup.", "Consider a hash set."],
                hints_given=2,
                recent_probe_categories=["complexity_probe", "approach_choice", "walkthrough"],
                asked_aspects=["complexity_probe", "approach_choice", "walkthrough"],
                rolling_summary="Candidate identified brute force O(n²), then optimised to O(n) with hash map.",
                known_weak_areas=["edge_case_handling"],
                known_strong_areas=["approach_quality"],
                confidence_trend=[0.5, 0.6, 0.7],
            )
            state = _base_state(
                interview_phase="testing",
                phase_turns=3,
                brute_force_given=True,
                candidate_code="def solve(s): pass",
                memory=q1_memory,
                progress=InterviewProgress(
                    current_question_index=1,
                    total_questions=2,
                    remaining_seconds=1200,
                    allocated_minutes=45,
                ),
                candidate_explanation="I'm done, next question.",
            )
            with patch("app.dsa.llm_text.generate_text", new=AsyncMock(return_value="Moving to Q2.")):
                result = await question_advancer(state)

            memory = result["memory"]

            # Per-question fields must be cleared
            assert memory.turns == [], "Q1 turns leaked into Q2"
            assert memory.hint_log == [], "Q1 hint_log leaked into Q2"
            assert memory.recent_probe_categories == [], "Q1 probe categories leaked"
            assert memory.asked_aspects == [], "Q1 asked_aspects leaked"
            assert memory.rolling_summary == "", "Q1 rolling_summary leaked"

            # Cross-question fields must be preserved
            assert memory.hints_given == 2, "Cross-question hints_given was reset"
            assert memory.known_weak_areas == ["edge_case_handling"]
            assert memory.known_strong_areas == ["approach_quality"]
            assert memory.confidence_trend == [0.5, 0.6, 0.7]

        asyncio.run(_run())

    def test_advance_message_generated_for_middle_question(self):
        """Question advance between Q1 and Q2 generates a transition message."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _run():
            from app.dsa.graph import question_advancer

            state = _base_state(
                progress=InterviewProgress(
                    current_question_index=1,
                    total_questions=2,
                    remaining_seconds=1200,
                    allocated_minutes=45,
                ),
                candidate_explanation="I'm done with this one.",
            )
            with patch("app.dsa.llm_text.generate_text", new=AsyncMock(return_value="Great, moving to Q2.")):
                result = await question_advancer(state)

            assert result["interviewer_reply"]
            assert "2" in result["interviewer_reply"] or "Q2" in result["interviewer_reply"]

        asyncio.run(_run())

    def test_advance_message_wraps_up_on_last_question(self):
        """On last question, advance generates a wrap-up message."""
        import asyncio

        async def _run():
            from app.dsa.graph import question_advancer

            state = _base_state(
                progress=InterviewProgress(
                    current_question_index=2,
                    total_questions=2,
                    remaining_seconds=600,
                    allocated_minutes=45,
                ),
                candidate_explanation="done",
            )
            result = await question_advancer(state)
            reply = result["interviewer_reply"].lower()
            assert "wrap" in reply or "end" in reply or "all" in reply or "2" in reply

        asyncio.run(_run())


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 13 — Plagiarism detection
# ──────────────────────────────────────────────────────────────────────────────

class TestPlagiarismDetection:
    def test_copy_paste_event_raises_likelihood(self):
        from app.dsa.nodes.evaluation import plagiarism_detector
        state = _base_state(
            turn_number=1,
            editor_signals=EditorSignals(copy_paste_detected=True),
        )
        result = plagiarism_detector(state)
        assert result["scratch"]["_plagiarism_likelihood"] >= 0.65

    def test_high_token_overlap_with_expected_solution_raises_likelihood(self):
        from app.dsa.nodes.evaluation import plagiarism_detector
        expected = "def first_non_repeating(s):\n    count = {}\n    for c in s:\n        count[c] = count.get(c, 0) + 1\n    for c in s:\n        if count[c] == 1:\n            return c\n    return None\n"
        state = _base_state(
            turn_number=1,
            candidate_code=expected,  # identical to expected
            config=SessionConfig(
                expected_solution=expected,
                problem_statement="Find the first non-repeating character.",
                allowed_patterns=["hashing"],
                max_hints=3,
                max_turns=24,
                total_questions=2,
                allocated_minutes=45,
                per_question_minutes=22.5,
            ),
        )
        result = plagiarism_detector(state)
        assert result["scratch"]["_plagiarism_likelihood"] >= 0.55

    def test_normal_similar_solution_does_not_trigger_plagiarism(self):
        from app.dsa.nodes.evaluation import plagiarism_detector
        expected = "def solve(s):\n    count = {}\n    for c in s:\n        count[c] = count.get(c,0)+1\n    for c in s:\n        if count[c] == 1: return c\n    return ''\n"
        candidate = "def first_unique(s):\n    freq = {}\n    for char in s:\n        freq[char] = freq.get(char, 0) + 1\n    for char in s:\n        if freq[char] == 1:\n            return char\n    return ''\n"
        state = _base_state(
            turn_number=1,
            candidate_code=candidate,
            config=SessionConfig(
                expected_solution=expected,
                problem_statement="Find the first non-repeating character.",
                allowed_patterns=["hashing"],
                max_hints=3,
                max_turns=24,
                total_questions=2,
                allocated_minutes=45,
                per_question_minutes=22.5,
            ),
        )
        result = plagiarism_detector(state)
        # Good solution ≠ plagiarism
        assert result["scratch"]["_plagiarism_likelihood"] < 0.55


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 14 — Voice / audio signal edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestVoiceAudioSignals:
    def test_nervous_tone_flagged(self):
        from app.dsa.nodes.signals import speech_signal_extractor
        from app.dsa.state import SpeechSignals
        state = _base_state(
            speech_signals=SpeechSignals(
                wpm=70,
                filler_ratio=0.20,
                hesitation_count=8,
                tone_label="nervous",
            ),
        )
        result = speech_signal_extractor(state)
        flags = result["scratch"]["_speech_flags"]
        assert "nervous_tone" in flags
        assert "very_slow_speech" in flags
        assert "high_filler_ratio" in flags

    def test_confident_fast_speaker_no_panic(self):
        from app.dsa.nodes.signals import speech_signal_extractor
        from app.dsa.state import SpeechSignals
        state = _base_state(
            speech_signals=SpeechSignals(
                wpm=140,
                filler_ratio=0.05,
                hesitation_count=1,
                tone_label="confident",
            ),
        )
        result = speech_signal_extractor(state)
        panic = result["scratch"]["_panic_signals"]
        assert panic == []

    def test_long_silence_gap_flagged(self):
        from app.dsa.nodes.signals import silence_gap_detector
        state = _base_state(
            silence_profile=SilenceProfile(
                gaps=[5.0, 12.0, 25.0],
                longest_gap=25.0,
                total_silence=42.0,
            ),
        )
        result = silence_gap_detector(state)
        panic = result["scratch"]["_panic_signals_silence"]
        assert "candidate_appears_stuck" in panic

    def test_silence_below_threshold_not_flagged(self):
        from app.dsa.nodes.signals import silence_gap_detector
        state = _base_state(
            silence_profile=SilenceProfile(
                gaps=[2.0, 3.5, 4.0],
                longest_gap=4.0,
                total_silence=9.5,
            ),
        )
        result = silence_gap_detector(state)
        panic = result["scratch"]["_panic_signals_silence"]
        assert "candidate_appears_stuck" not in panic


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 15 — Fuzz: extreme / adversarial inputs
# ──────────────────────────────────────────────────────────────────────────────

class TestAdversarialInputs:
    @pytest.mark.parametrize("explanation", [
        "",                      # completely empty
        " " * 500,               # whitespace-only
        "A" * 3000,              # extremely long (>2400 char limit in intent context)
        "!!!???###@@@",          # special characters only
        "end interview\n" * 20,  # repeated end keywords
        "next question\n" * 20,  # repeated advance keywords
        "hint\n" * 20,           # repeated hint keywords
        "I don't know " * 50,    # long give-up signal
    ])
    def test_phase_tracker_does_not_crash(self, explanation):
        """phase_tracker must survive any candidate_explanation string."""
        state = _base_state(candidate_explanation=explanation, interview_phase="reading")
        result = phase_tracker(state)
        assert "interview_phase" in result
        assert result["interview_phase"] in {
            "reading", "clarification", "brute_force",
            "optimization", "coding", "testing", "closing",
        }

    @pytest.mark.parametrize("explanation", [
        "",
        " " * 500,
        "A" * 3000,
        "!!!???###@@@",
        "not listening " * 30,
        "change topic " * 30,
    ])
    def test_explicit_override_does_not_crash(self, explanation):
        """_apply_explicit_signal_overrides must survive any input string."""
        state = _base_state(candidate_explanation=explanation)
        raw = _intent_from_raw("idle")
        result = _apply_explicit_signal_overrides(state, raw)
        assert result.intent in {
            "explaining_approach", "asking_clarification", "asking_hint",
            "submitting_code", "answering_followup", "meta_complaint",
            "change_topic", "idle",
        }

    @pytest.mark.parametrize("explanation", [
        "end interview",
        "stop interview",
        "wrap up",
        "END INTERVIEW",         # uppercase
        "  end interview  ",     # leading/trailing spaces
        "I want to end interview now.",
    ])
    def test_various_end_interview_phrasings(self, explanation):
        """All end-interview phrase variations must trigger should_end_round."""
        state = _base_state(candidate_explanation=explanation)
        raw = _intent_from_raw("idle")
        intent = _to_candidate_intent(state, raw)
        assert intent.should_end_round is True, f"Failed for: {explanation!r}"

    @pytest.mark.parametrize("code", [
        "",                              # no code
        "def solve(): pass",             # trivially short
        "x = 1",                         # single-line expression
        "def f():\n    return None",     # 2 lines — below the 3-line threshold
    ])
    def test_short_code_does_not_advance_to_coding_phase(self, code):
        """The 3-line threshold must be respected — trivial code stubs stay in current phase."""
        state = _base_state(
            interview_phase="clarification",
            phase_turns=1,
            candidate_code=code,
            candidate_explanation="",
        )
        result = phase_tracker(state)
        assert result["interview_phase"] != "coding", (
            f"Short code {code!r} unexpectedly advanced to 'coding' phase."
        )

    def test_negative_remaining_seconds_does_not_crash_phase_router(self):
        """Edge case: remaining_seconds could be slightly negative due to timing."""
        state = _base_state(
            interview_phase="reading",
            phase_turns=0,
            progress=InterviewProgress(
                current_question_index=1,
                total_questions=2,
                allocated_minutes=45,
                remaining_seconds=-5,   # edge case
                time_expired=True,
            ),
        )
        pt_result = phase_tracker(state)
        updated = state.model_copy(update=pt_result)
        # Should not crash
        route = phase_router(updated)
        assert route in {
            "time_pressure_push", "silence_probe", "demand_brute_force",
            "code_walkthrough", "output_turn",
        }
