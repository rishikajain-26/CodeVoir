from __future__ import annotations

import json

from app.dsa.schemas_llm import CandidateTurnIntentLLM
from app.dsa.state import CandidateIntent, DSAState
from app.services.llm.factory import get_llm_provider
from app.utils.logger import logger

provider = get_llm_provider()

_SYS_INTENT = """You are classifying what a candidate just said in a coding interview.
Return JSON only, no markdown, no extra keys:
{
  "intent": "explaining_approach|asking_clarification|asking_hint|submitting_code|answering_followup|meta_complaint|change_topic|idle",
  "summary": "one sentence of what they actually said",
  "approach_correct": null or true or false,
  "question_asked": null or "exact question they asked",
  "frustration_level": 0-3,
  "confidence": 0.0-1.0
}

Rules:
- If they describe an algorithm, formula, invariant, or walk through an example, use explaining_approach.
- If they ask "is my logic correct?", still use explaining_approach and set approach_correct when possible.
- If they ask what a word means, ask to repeat, ask about examples/constraints, or ask what the problem means, use asking_clarification.
- If they say hint, help, stuck, clue, nudge, don't know, or where to start, use asking_hint.
- If the trigger is code_submit or they are mainly asking about run results/code feedback, use submitting_code.
- If they respond to the last interviewer question, use answering_followup.
- If they complain about repetition, not listening, dumb responses, or interviewer behavior, use meta_complaint.
- If they explicitly ask to switch topic, discuss a different problem concept, or redirect the conversation, use change_topic.
- If there is no meaningful candidate content, use idle.
- Set confidence (0.0-1.0) to reflect how certain you are about the classification.
"""


async def resolve_candidate_intent(state: DSAState) -> dict:
    context = _build_intent_context(state)
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_INTENT,
            user_prompt=json.dumps(context, ensure_ascii=False),
            response_schema=CandidateTurnIntentLLM,
        )
        turn_intent = result
    except Exception as exc:
        logger.warning("DSA intent classification failed, using fallback: %s", exc)
        turn_intent = _fallback_turn_intent(state)

    turn_intent = _apply_explicit_signal_overrides(state, turn_intent)
    # Low-confidence classifications fall back to safe "answering_followup" to avoid
    # false positives on topic-change or hint routing.
    if turn_intent.confidence < 0.7 and turn_intent.intent not in {
        "meta_complaint", "asking_hint", "submitting_code"
    }:
        turn_intent = turn_intent.model_copy(update={"intent": "answering_followup"})
    intent = _to_candidate_intent(state, turn_intent)
    intent = _apply_intent_guardrails(state, intent)
    return {"candidate_intent": intent, "next_action": _route_action_from_intent(state, intent)}


def _build_intent_context(state: DSAState) -> dict:
    recent_turns = [
        {
            "candidate": record.explanation_excerpt[:300],
            "interviewer": record.followup_asked[:300],
            "hint": record.hint_given,
        }
        for record in state.memory.turns[-5:]
    ]
    run = state.latest_code_run or {}
    return {
        "trigger": state.trigger,
        "candidate_said": state.candidate_explanation[:2400],
        "code_in_editor": state.candidate_code[-1600:],
        "problem": {
            "statement": state.config.problem_statement[:1400],
            "expected_patterns": state.config.allowed_patterns,
            "expected_time": state.config.expected_time_complexity,
            "expected_space": state.config.expected_space_complexity,
        },
        "latest_code_run": {
            "passed": run.get("passed_testcases"),
            "total": run.get("total_testcases"),
            "overall_score": run.get("overall_score"),
        }
        if run
        else None,
        "last_question_asked": state.memory.turns[-1].followup_asked if state.memory.turns else "",
        "previous_followups": [record.followup_asked for record in state.memory.turns[-5:] if record.followup_asked],
        "previous_hints": state.memory.hint_log[-5:],
        "hints_given": state.memory.hints_given,
        "max_hints": state.config.max_hints,
    }


def _fallback_turn_intent(state: DSAState) -> CandidateTurnIntentLLM:
    text = state.candidate_explanation.lower()
    if state.trigger == "code_submit" or "submitted" in text:
        return CandidateTurnIntentLLM(intent="submitting_code", summary="Candidate submitted code or asked for code feedback.")
    if any(term in text for term in ("not listening", "repeating", "dumb", "child", "wrong with you", "ignoring")):
        return CandidateTurnIntentLLM(intent="meta_complaint", summary=state.candidate_explanation[:200], frustration_level=3)
    if any(phrase in text for phrase in ("can you see my code", "check my code", "go through my code", "review my code", "look at my code", "check out my code", "please go through", "see my code")):
        return CandidateTurnIntentLLM(intent="meta_complaint", summary="Candidate is asking the interviewer to review their current code.", frustration_level=2)
    if any(term in text for term in ("hint", "help", "stuck", "clue", "nudge", "not sure", "where to start")):
        return CandidateTurnIntentLLM(intent="asking_hint", summary=state.candidate_explanation[:200], question_asked=state.candidate_explanation[:300])
    if any(term in text for term in ("change topic", "different topic", "switch topic", "talk about something else", "let's talk about")):
        return CandidateTurnIntentLLM(intent="change_topic", summary=state.candidate_explanation[:200], confidence=0.9)
    if "?" in text and any(term in text for term in ("what", "why", "how", "constraint", "example", "input", "output", "substring", "subarray")):
        return CandidateTurnIntentLLM(intent="asking_clarification", summary=state.candidate_explanation[:200], question_asked=state.candidate_explanation[:300])
    if any(term in text for term in ("logic", "approach", "formula", "count", "because", "so ", "therefore", "is this correct")):
        return CandidateTurnIntentLLM(intent="explaining_approach", summary=state.candidate_explanation[:200], question_asked=state.candidate_explanation[:300] if "?" in text else None)
    if text.strip():
        return CandidateTurnIntentLLM(intent="answering_followup", summary=state.candidate_explanation[:200])
    return CandidateTurnIntentLLM(intent="idle", summary="Candidate did not provide meaningful content.")


def _apply_explicit_signal_overrides(state: DSAState, turn_intent: CandidateTurnIntentLLM) -> CandidateTurnIntentLLM:
    text = state.candidate_explanation.lower()
    if any(term in text for term in ("not listening", "repeating", "repeat yourself", "ignoring", "dumb", "childbot", "child bot")):
        return turn_intent.model_copy(
            update={
                "intent": "meta_complaint",
                "summary": state.candidate_explanation[:240],
                "frustration_level": max(turn_intent.frustration_level, 3),
            }
        )
    if any(term in text for term in ("change topic", "different topic", "switch topic", "talk about something else")):
        return turn_intent.model_copy(
            update={
                "intent": "change_topic",
                "summary": turn_intent.summary or state.candidate_explanation[:240],
                "confidence": max(float(turn_intent.confidence or 0.5), 0.85),
            }
        )
    if any(term in text for term in ("hint", "help me", "stuck", "clue", "nudge", "where to start")):
        return turn_intent.model_copy(
            update={
                "intent": "asking_hint",
                "summary": turn_intent.summary or state.candidate_explanation[:240],
                "question_asked": turn_intent.question_asked or state.candidate_explanation[:300],
            }
        )
    if "is this correct" in text or "am i correct" in text or "is my logic" in text:
        return turn_intent.model_copy(
            update={
                "intent": "explaining_approach",
                "summary": turn_intent.summary or state.candidate_explanation[:240],
                "question_asked": turn_intent.question_asked or state.candidate_explanation[:300],
            }
        )
    _code_review_phrases = (
        "can you see my code", "check my code", "go through my code",
        "review my code", "look at my code", "check out my code",
        "can you go through", "please go through", "check my approach",
        "look at my approach", "see my code", "can you review",
        "look at the code", "see the code", "read my code",
    )
    if any(phrase in text for phrase in _code_review_phrases):
        return turn_intent.model_copy(
            update={
                "intent": "meta_complaint",
                "summary": "Candidate is asking the interviewer to look at and review their current code.",
                "frustration_level": max(int(turn_intent.frustration_level or 0), 2),
            }
        )
    return turn_intent


def _to_candidate_intent(state: DSAState, turn_intent: CandidateTurnIntentLLM) -> CandidateIntent:
    raw = turn_intent.intent
    primary_map = {
        "explaining_approach": "discuss_approach",
        "asking_clarification": "clarify_problem",
        "asking_hint": "request_hint",
        "submitting_code": "review_submission",
        "answering_followup": "continue",
        "meta_complaint": "continue",
        "change_topic": "continue",
        "idle": "continue",
    }
    should_give_hint = raw == "asking_hint"
    should_clarify = raw == "asking_clarification"
    should_change_topic = raw == "change_topic"
    should_end = any(term in state.candidate_explanation.lower() for term in ("end interview", "stop interview", "wrap up"))
    should_advance = any(
        term in state.candidate_explanation.lower()
        for term in ("next question", "next problem", "move on", "done with this", "finished this problem")
    )
    focus = _focus_for_intent(raw, turn_intent)
    return CandidateIntent(
        primary_intent=primary_map[raw],
        should_give_hint=should_give_hint,
        should_advance_question=should_advance,
        should_end_round=should_end,
        should_clarify_problem=should_clarify,
        should_change_topic=should_change_topic,
        interviewer_focus=focus,
        reasoning=turn_intent.summary,
        raw_intent=raw,
        summary=turn_intent.summary,
        approach_correct=turn_intent.approach_correct,
        question_asked=turn_intent.question_asked,
        frustration_level=max(0, min(int(turn_intent.frustration_level or 0), 3)),
    )


def _focus_for_intent(raw: str, turn_intent: CandidateTurnIntentLLM) -> str:
    if raw == "explaining_approach":
        if turn_intent.approach_correct is True:
            return "Acknowledge the candidate's reasoning specifically and ask them to implement it."
        if turn_intent.approach_correct is False:
            return "Point out the exact flaw in their reasoning and give a small counterexample."
        return "React to the candidate's approach before asking any new question."
    if raw == "asking_clarification":
        return "Answer the exact clarification question from the problem context."
    if raw == "asking_hint":
        return "Give one calibrated hint, not a formula dump or full solution."
    if raw == "meta_complaint":
        return "Apologize for the repetition, acknowledge the issue, and re-engage differently."
    if raw == "submitting_code":
        return "Review the submitted code or test result."
    if raw == "change_topic":
        return "Acknowledge the candidate's request and redirect them back to the current problem with a focused question."
    if raw == "idle":
        return "Ask one open question about their current thinking."
    return "Respond to the candidate's last answer in context."


def _apply_intent_guardrails(state: DSAState, intent: CandidateIntent) -> CandidateIntent:
    if intent.should_give_hint and state.memory.hints_given >= state.config.max_hints:
        intent = intent.model_copy(
            update={
                "should_give_hint": False,
                "interviewer_focus": "No more hints remain; ask the candidate to reason from their current invariant.",
            }
        )
    if intent.should_advance_question and state.progress.current_question_index >= state.progress.total_questions:
        intent = intent.model_copy(update={"should_advance_question": False, "should_end_round": True})
    if state.progress.time_expired:
        intent = intent.model_copy(update={"should_end_round": True})
    return intent


def _route_action_from_intent(state: DSAState, intent: CandidateIntent) -> str:
    if intent.should_end_round or state.progress.round_complete:
        return "generate_report"
    if intent.raw_intent in {"meta_complaint", "asking_clarification", "change_topic"} or intent.frustration_level >= 2:
        return "direct_reply"
    if intent.should_give_hint and state.memory.hints_given < state.config.max_hints:
        return "escalate_hint"
    return "next_turn"
