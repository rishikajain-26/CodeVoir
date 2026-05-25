from __future__ import annotations

import asyncio
import json
import re
from typing import Literal

from app.dsa.llm_text import generate_text
from app.dsa.state import DSAState, SessionScores
from app.services.personality_service import get_interviewer_personality, personality_to_prompt_fragment


# ─── Probe Category Tracking (fallback anti-loop) ────────────────────────────
# Categories of interview probes. Used to avoid repeating the same TYPE of
# question in consecutive turns — even when the exact wording differs.
PROBE_CATEGORIES = (
    "complexity_probe",
    "edge_case_probe",
    "approach_choice",
    "invariant_check",
    "code_structure",
    "optimization",
    "tradeoff",
    "walkthrough",
    "data_structure",
    "correctness",
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "complexity_probe": ("time complexity", "space complexity", "big o", "o(n", "o(1", "o(log", "runtime", "how fast", "how slow"),
    "edge_case_probe": ("edge case", "empty input", "single element", "boundary", "corner case", "what happens when", "null", "zero"),
    "approach_choice": ("why did you choose", "alternative", "other approach", "different pattern", "could you use", "what about"),
    "invariant_check": ("invariant", "always true", "property holds", "at each step", "loop condition", "termination"),
    "code_structure": ("syntax", "function", "return", "incomplete", "finish", "clean up", "dead code", "unreachable"),
    "optimization": ("optimise", "optimize", "reduce", "improve", "faster", "less space", "better", "can you do better"),
    "tradeoff": ("tradeoff", "trade-off", "sacrifice", "cost", "pros and cons", "compare"),
    "walkthrough": ("walk me through", "trace", "step by step", "example", "dry run", "state at each"),
    "data_structure": ("data structure", "hash", "stack", "queue", "heap", "tree", "graph", "array", "linked list", "set"),
    "correctness": ("correct", "verify", "prove", "test", "counterexample", "flaw", "bug", "wrong"),
}


def _classify_probe(text: str) -> str:
    """Classify a probe/question into a category based on keyword matching."""
    lower = text.lower()
    best_cat = "walkthrough"
    best_score = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_cat = category
    return best_cat


def _category_recently_used(category: str, recent: list[str], window: int = 3) -> bool:
    """Check if a category was used in the last `window` turns."""
    return category in recent[-window:]


def _build_coverage_map(state: DSAState) -> dict:
    """Build a structured assessment of what's been tested and where the gaps are.

    This gives the LLM a clear picture of the candidate's current state so it
    can intelligently choose what to probe next — no hardcoded decision logic."""
    areas: dict[str, dict] = {}

    # 1. Problem understanding
    u = state.understanding
    tested = u.understanding_score > 0 or bool(u.clarifying_questions_asked)
    areas["problem_understanding"] = {
        "tested": tested,
        "score": round(u.understanding_score, 2) if tested else None,
        "gaps": u.misunderstood_constraints[:3] if u.misunderstood_constraints else [],
    }

    # 2. Approach / pattern recognition
    a = state.approach
    tested = a.approaches_attempted > 0 or a.approach_quality_score > 0
    areas["approach"] = {
        "tested": tested,
        "score": round(a.approach_quality_score, 2) if tested else None,
        "optimal": a.final_approach_optimal,
        "patterns_used": a.pattern_recognised[:4],
        "expected_patterns": state.config.allowed_patterns[:4],
        "gaps": [] if a.final_approach_optimal else ["approach not yet optimal"],
    }

    # 3. Complexity analysis
    c = state.complexity
    tested = bool(c.stated_time or c.stated_space)
    areas["complexity"] = {
        "tested": tested,
        "time_correct": c.time_correct if tested else None,
        "space_correct": c.space_correct if tested else None,
        "stated": f"T:{c.stated_time} S:{c.stated_space}" if tested else None,
        "actual": f"T:{c.actual_time} S:{c.actual_space}" if c.actual_time else None,
        "gaps": (
            (["time wrong"] if not c.time_correct else []) +
            (["space wrong"] if not c.space_correct else []) +
            (["no tradeoff discussion"] if c.tradeoff_discussion_quality < 0.3 else [])
        ) if tested else ["not discussed yet"],
    }

    # 4. Implementation / code quality
    impl = state.implementation
    has_code = bool(state.candidate_code.strip())
    areas["implementation"] = {
        "tested": has_code,
        "code_complete": impl.code_complete if has_code else None,
        "compiles": impl.compilation_success if has_code else None,
        "gaps": (
            (["code incomplete"] if not impl.code_complete else []) +
            (["no boundary checks"] if not impl.boundary_checks_handled else []) +
            (["no null/empty guards"] if not impl.null_empty_checks else []) +
            ([f"{impl.logical_bug_count} logical bugs"] if impl.logical_bug_count else [])
        ) if has_code else ["no code written yet"],
    }

    # 5. Edge cases / testing
    t = state.testing
    tested = t.test_cases_written > 0 or t.edge_case_coverage > 0
    areas["edge_cases"] = {
        "tested": tested,
        "coverage": round(t.edge_case_coverage, 2) if tested else None,
        "missed": state.turn_score.missed_edge_cases[:4],
        "gaps": state.turn_score.missed_edge_cases[:4] if state.turn_score.missed_edge_cases else (
            ["edge cases not discussed"] if not tested else []
        ),
    }

    # 6. Debugging
    d = state.debug_profile
    tested = d.debug_iterations > 0
    areas["debugging"] = {
        "tested": tested,
        "strategy": d.debug_strategy if tested else None,
        "fixes_root_cause": d.fixes_root_cause if tested else None,
    }

    # Summary: which areas have gaps (untested or low-scoring)
    untested = [area for area, info in areas.items() if not info.get("tested")]
    weakest = [area for area, info in areas.items() if info.get("gaps")]

    return {
        "areas": areas,
        "untested_areas": untested,
        "areas_with_gaps": weakest,
        "strong_areas": state.memory.known_strong_areas[-4:],
        "weak_areas": state.memory.known_weak_areas[-4:],
    }


def _compute_depth_signal(state: DSAState) -> dict:
    """Analyze recent turns to decide: dig_deeper, move_on, or neutral.

    Returns a dict with:
      - depth_signal: "dig_deeper" | "move_on" | "neutral"
      - reason: short explanation for the LLM
      - consecutive_same_topic: how many turns on the current category
    """
    recent_cats = state.memory.recent_probe_categories
    turns = state.memory.turns
    candidate_text = (state.candidate_explanation or "").strip().lower()

    # Detect explicit "I don't know" signals
    _stuck_phrases = (
        "i don't know", "i dont know", "not sure", "no idea", "i can't",
        "i cannot", "blank", "i'm stuck", "im stuck", "pass", "skip",
        "move on", "next question", "i give up",
    )
    candidate_gave_up = any(phrase in candidate_text for phrase in _stuck_phrases)

    # Count consecutive same-category probes
    consecutive = 0
    if recent_cats:
        current_cat = recent_cats[-1]
        for cat in reversed(recent_cats):
            if cat == current_cat:
                consecutive += 1
            else:
                break

    # Check if candidate is making progress (score trending up vs flat/down)
    recent_scores = [t.score.weighted_total for t in turns[-3:]] if turns else []
    score_stagnant = (
        len(recent_scores) >= 2
        and all(s <= recent_scores[0] + 0.05 for s in recent_scores[1:])
    )

    # Very short answers suggest the candidate has nothing more to offer
    short_answer = len(candidate_text.split()) < 8 and not candidate_gave_up

    # Decision logic
    if candidate_gave_up:
        return {
            "depth_signal": "move_on",
            "reason": "Candidate explicitly indicated they don't know. Move to a different topic.",
            "consecutive_same_topic": consecutive,
        }

    if consecutive >= 3 and score_stagnant:
        return {
            "depth_signal": "move_on",
            "reason": f"Same topic probed {consecutive} times with no score improvement. Switch to a different area.",
            "consecutive_same_topic": consecutive,
        }

    if consecutive >= 2 and short_answer:
        return {
            "depth_signal": "move_on",
            "reason": "Candidate giving minimal answers after repeated probing. They likely don't know more here.",
            "consecutive_same_topic": consecutive,
        }

    if consecutive >= 1 and not score_stagnant and len(candidate_text.split()) > 15:
        return {
            "depth_signal": "dig_deeper",
            "reason": "Candidate showed partial understanding — dig into the specifics they couldn't fully articulate.",
            "consecutive_same_topic": consecutive,
        }

    return {
        "depth_signal": "neutral",
        "reason": "Normal flow — pick the highest-value next question.",
        "consecutive_same_topic": consecutive,
    }

# When the AI appends this token, the orchestration layer will advance to the next question.
_ADVANCE_TOKEN = "[[ADVANCE]]"

_SYS_FOLLOWUP = """You are a focused DSA interviewer generating the NEXT probing question.

You receive a coverage_map showing what has been assessed and where gaps remain. Use it to decide what to ask next — always target the area with the most valuable untested gap.

Strict rules:
- Output ONE question only. Plain text. No preamble.
- PREVIOUSLY_ASKED lists questions already posed. Do NOT repeat them verbatim. You MAY dig deeper into the same topic if the candidate's prior answer was vague or incomplete — but ask something more specific, not the same surface question.
- aspects_already_covered lists the probe categories that have already been fully addressed this session. Prefer probing an aspect NOT in this list when a good untested gap exists.
- Use coverage_map.areas_with_gaps and coverage_map.untested_areas to identify where the candidate still has holes.
- If an area is untested: probe it. If an area was tested with a low score or gaps: dig deeper. If an area is tested with no gaps: skip it.
- If approach_correct=true: ask about an edge case, implementation detail, or next optimisation step.
- If approach_correct=false: ask which specific input breaks their logic.

Reading the candidate:
- consecutive_same_topic and recent_scores tell you if you've been probing the same area and whether the candidate is improving.
- Read the candidate's actual message. If they show partial knowledge (some correct reasoning but can't fully justify it): ask a deeper, more specific follow-up.
- If the candidate clearly has nothing left to offer on a topic (says "I don't know", gives empty/circular answers, no score improvement after 2-3 probes): move on to the next gap in the coverage map. Don't explain why — just ask about a different area.
- Your goal is maximum signal extraction in minimum turns."""

_SYS_HINT = """You are a compassionate DSA interviewer. Calibrate hint by tightness:
- tight: one concise nudge toward the right invariant, state, or data structure
- medium: point to the bottleneck and one useful way to reason about an example
- broad: high-level approach but not implementation
Use the actual problem, examples, candidate question, and current code. Do not reveal final code.
Return plain text only. Two sentences maximum."""

_SYS_CONTEXTUAL = """You are a sharp, professional DSA interviewer. RESPOND DIRECTLY to what the candidate just said.

Response structure — follow this exactly:
1. ONE sentence that directly reacts to the candidate's words (agree, correct, challenge, or answer).
2. ONE sentence that moves the interview forward (probe a gap, point to a flaw, or push toward code).

Rules by raw_intent:
- explaining_approach + approach_correct=true: acknowledge the specific logic they gave, then say "Go ahead and code that."
- explaining_approach + approach_correct=false: name the exact flaw and give one tiny counterexample. No new question.
- asking_clarification: answer the exact question from the problem context in one sentence. Do NOT ask anything back.
- asking_hint: give the calibrated hint only. Do not add another question.
- answering_followup: confirm whether they addressed the prior question, then name what is still missing.
- submitting_code: you MUST reference the actual test_run data.
    If test_run.all_passed=true: ONE sentence stating all N tests passed, then ask for the exact time and space complexity with proof, or name one specific edge case they have not handled.
    If test_run.all_passed=false and failure_diagnosis is present: ONE sentence explaining the root cause from failure_diagnosis (what logic error or condition in the code causes the wrong output — be specific, name the code element). Then ask the candidate to locate and explain that exact line or condition before touching anything.
    If test_run.all_passed=false and failure_diagnosis is absent: ONE sentence citing the first failing case (input, expected, actual), then ask what logic error causes that mismatch.
    If test_run is absent: ask the candidate to run the visible tests before continuing.
    Do NOT suggest a fix — make them diagnose first.
- meta_complaint: MUST start with "You're right" or "Sorry". If the complaint is about reviewing code, you MUST name at least one specific element from code_tail (a function, variable, loop, or condition) and say what you observe about it. Do not repeat the previous question. Reset the conversation.
- idle: ask what they are currently thinking in one sentence.

Phase-aware behavior (use interview_phase to calibrate your second sentence):
- reading: The candidate just received the problem. Push them to restate the input/output contract and name one constraint or edge case they noticed.
- clarification: Answer the exact question, then immediately push them to propose even a naive first approach.
- brute_force: They have a brute force but haven't optimized. Make them commit to it fully — exact time complexity, concrete trace on one example — before allowing optimization.
- optimization: They're discussing an optimized approach. Push for the specific invariant or data structure that makes the brute force redundant; don't accept "use a hash map" without the why.
- coding: Review actual code lines. Name a specific function, condition, or variable in code_tail and ask about it. Never ask abstract questions when code is visible.
- testing: Focus on edge cases their submitted tests miss, or ask them to trace the algorithm on a specific input value.
- closing: Ask one synthesis question — alternative approach, tradeoff, or how they'd extend this to a harder variant.

Depth vs Breadth — use your judgment:
- Look at consecutive_same_topic and recent_scores to gauge whether the candidate is progressing or stuck.
- If they gave a partial answer with some correct logic: dig deeper — your second sentence should ask for proof, a concrete example, or the exact mechanism.
- If they clearly have nothing left (empty answers, "I don't know", no improvement over multiple turns): briefly acknowledge and move your second sentence to a COMPLETELY DIFFERENT topic. Don't explain why you're moving on.

Anti-loop rules — check these BEFORE writing:
- If your first draft resembles anything in previous_followups or previous_hints, rewrite it to address a different gap.
- Do not ask about complexity unless neither previous_followups nor previous_hints already covered it.

Auto-advance: Once the candidate has a confirmed correct approach AND has written non-trivial code AND at least 4 turns have occurred, you may append [[ADVANCE]] on a new line at the very end of your response to move them to the next problem. Only do this when the current problem is genuinely settled.

Plain text only. Max 2 sentences (plus [[ADVANCE]] if applicable). No bullet points."""

_SYS_BRUTE_FORCE_DEMAND = """You are a strict DSA interviewer. The candidate has been discussing the problem for several turns but has NOT stated any concrete approach yet.

Your only job: demand a brute force solution right now.
- Ask for the simplest possible solution, even O(n³) or O(n!). Just get one concrete approach on the table.
- They must give: the data structure used, the loop/recursion structure, and the time complexity.
- Do NOT give hints. Do NOT accept vague descriptions like "iterate over the array."
- One direct sentence. No preamble. No encouragement."""

_SYS_SILENCE_PROBE = """You are a DSA interviewer. The candidate has been silent or produced minimal output for an extended period.

Ask ONE open question to break the silence. Options in priority order:
1. If they have partial code: "Walk me through what you have so far — what does line X do?"
2. If they mentioned an approach: "You mentioned [approach] — what's blocking you from writing the first line?"
3. If nothing: "What are you thinking right now — even half-formed ideas are fine to say out loud."

Plain text. One sentence. Do NOT give a hint."""

_SYS_WALKTHROUGH_DEMAND = """You are a sharp DSA interviewer. The candidate's code just passed all visible test cases.

Your job: demand a step-by-step trace on a specific input BEFORE moving on.
- Pick one concrete input (from the test cases or a tricky edge case you know about).
- Ask them to name: the exact state before the loop starts, what changes each iteration, and the final return value.
- Do not praise them. Do not ask about complexity yet. One sentence naming the specific input to trace."""

_SYS_TIME_PRESSURE = """You are a DSA interviewer and time is running critically short (less than 25% remaining).

The candidate has NOT written working code yet.
Your job: clearly tell them to start coding IMMEDIATELY with whatever approach they have.
- Name the specific approach they mentioned (or the simplest valid one).
- Make clear that an imperfect solution coded up is better than a perfect solution never written.
- One direct sentence. Urgent but professional. No question — a directive."""


def _format_test_run(state: DSAState) -> dict | None:
    run = state.latest_code_run or {}
    total = int(run.get("total_testcases", 0) or 0)
    if not run or total == 0:
        return None
    passed = int(run.get("passed_testcases", 0) or 0)
    failing = [
        {
            "input": str(tc.get("input", ""))[:300],
            "expected": str(tc.get("expected_output", ""))[:300],
            "actual": str(tc.get("actual_output", ""))[:300],
            "stderr": str(tc.get("stderr", ""))[:200],
        }
        for tc in run.get("testcase_results", [])
        if not tc.get("passed")
    ][:3]
    return {
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
        "score_pct": round(float(run.get("overall_score", 0) or 0), 1),
        "failing_cases": failing,
    }


_SYS_FAILURE_ANALYSIS = """You are a DSA code reviewer. A candidate's code failed one or more test cases.
Given: problem statement, candidate code, and up to 3 failing test cases (input, expected output, actual output, stderr if any).
Task: In 2-3 sentences total, identify the SPECIFIC bugs or logic errors in the candidate's code.
For each distinct failure pattern, name the function, variable, condition, or algorithm step that is incorrect and explain mechanically what the code does wrong.
If multiple failures share the same root cause, say so. If stderr is present, describe what causes the crash or infinite loop.
Do NOT suggest a fix. Return plain text only."""


async def _analyze_test_failures(state: DSAState, failing_cases: list[dict]) -> str:
    """Diagnose up to 3 failing test cases in a single LLM call."""
    if not failing_cases:
        return ""
    try:
        cases_text = ""
        for i, case in enumerate(failing_cases[:3], 1):
            cases_text += (
                f"\nCase {i}:\n"
                f"  Input:    {str(case.get('input', ''))[:200]}\n"
                f"  Expected: {str(case.get('expected', ''))[:200]}\n"
                f"  Actual:   {str(case.get('actual', ''))[:200]}\n"
            )
            if case.get("stderr"):
                cases_text += f"  Stderr:   {str(case['stderr'])[:150]}\n"
        user_prompt = (
            f"PROBLEM:\n{state.config.problem_statement[:1000]}\n\n"
            f"CANDIDATE CODE:\n{state.candidate_code[-1500:]}\n\n"
            f"FAILING TEST CASES:{cases_text}"
        )
        diagnosis = await generate_text(_SYS_FAILURE_ANALYSIS, user_prompt, temperature=0.1, max_tokens=180)
        return diagnosis.strip() if diagnosis else ""
    except Exception:
        return ""


async def followup_generator(state: DSAState) -> dict:
    intent = state.candidate_intent
    if intent.raw_intent in {"asking_hint", "asking_clarification", "meta_complaint"} or intent.should_give_hint:
        return {"followup_question": intent.interviewer_focus}

    asked_before = {record.followup_asked for record in state.memory.turns if record.followup_asked}
    asked_before.update(state.memory.hint_log)
    personality_fragment = _build_personality_fragment(state)
    sys_followup = _SYS_FOLLOWUP
    if personality_fragment:
        sys_followup = f"{_SYS_FOLLOWUP}\n\nINTERVIEWER STYLE: {personality_fragment}"

    # Raw signals for the LLM to judge depth vs breadth itself
    recent_cats = state.memory.recent_probe_categories
    consecutive_same = 0
    if recent_cats:
        for cat in reversed(recent_cats):
            if cat == recent_cats[-1]:
                consecutive_same += 1
            else:
                break
    recent_scores = [t.score.weighted_total for t in state.memory.turns[-3:]]

    context = {
        "question": state.progress.label,
        "time_remaining_s": state.progress.remaining_seconds,
        "raw_intent": intent.raw_intent,
        "intent_summary": intent.summary,
        "approach_correct": intent.approach_correct,
        "candidate_message": state.candidate_explanation[:1200],
        "interviewer_focus": intent.interviewer_focus,
        "problem": state.config.problem_statement[:1200],
        "code_tail": state.candidate_code[-1200:],
        "missed_edges": state.turn_score.missed_edge_cases,
        "approach_optimal": state.approach.final_approach_optimal,
        "complexity_correct": state.complexity.time_correct and state.complexity.space_correct,
        "behaviour_flags": state.behaviour_profile.nervousness_flags[:5],
        "weak_areas": state.memory.known_weak_areas,
        "confidence": state.behaviour_profile.overall_confidence,
        "patterns_used": state.approach.pattern_recognised,
        "expected_patterns": state.config.allowed_patterns,
        "pressure_level": state.pressure_level,
        "difficulty_level": state.difficulty_level,
        "consecutive_same_topic": consecutive_same,
        "recent_scores": recent_scores,
        "coverage_map": _build_coverage_map(state),
        "PREVIOUSLY_ASKED": list(asked_before)[-12:],
        # Aspect tracking: aspects fully probed this session — avoid re-covering these
        "aspects_already_covered": state.memory.asked_aspects,
        "test_run": _format_test_run(state),
        "interview_phase": state.interview_phase,
        "phase_turns": state.phase_turns,
        "brute_force_given": state.brute_force_given,
    }
    question = await generate_text(sys_followup, json.dumps(context, ensure_ascii=False, default=str), temperature=0.3, max_tokens=140)
    if not question:
        question = _fallback_followup(state)
    return {"followup_question": question.strip()}


async def hint_calibrator(state: DSAState) -> dict:
    hints_so_far = state.memory.hints_given
    tightness: Literal["tight", "medium", "broad"] = (
        "tight" if hints_so_far == 0 else "medium" if hints_so_far == 1 else "broad"
    )
    if state.behaviour_profile.overall_confidence < 0.25:
        tightness = "medium"
    context = {
        "candidate_question": state.candidate_explanation[:1200],
        "intent_summary": state.candidate_intent.summary,
        "problem": state.config.problem_statement[:1600],
        "code": state.candidate_code[-1000:],
        "tightness": tightness,
        "previous_hints": state.memory.hint_log[-5:],
        "approach_attempted": state.approach.approaches_attempted,
        "pattern_expected": state.config.allowed_patterns,
        "pattern_candidate": state.approach.pattern_recognised,
        "confidence": state.behaviour_profile.overall_confidence,
    }
    hint = await generate_text(_SYS_HINT, json.dumps(context, ensure_ascii=False, default=str), temperature=0.2, max_tokens=100)
    if not hint:
        hint = _fallback_hint(state, tightness)
    memory = state.memory
    return {
        "hint": hint.strip(),
        "hint_tightness": tightness,
        "memory": memory.model_copy(
            update={
                "hints_given": memory.hints_given + 1,
                "hint_log": [*memory.hint_log, hint.strip()][-20:],
            }
        ),
    }


def score_reporter(state: DSAState) -> dict:
    turns = state.memory.turns
    totals = [record.score.weighted_total for record in turns]
    avg = sum(totals) / max(len(totals), 1)
    latest = state.turn_score
    return {
        "session_scores": SessionScores(
            problem_solving=round((latest.approach_quality + latest.understanding) / 2, 3),
            coding=round(latest.implementation, 3),
            communication=round(latest.communication, 3),
            debugging=round(latest.debugging, 3),
            dsa_knowledge=round((latest.approach_quality + latest.complexity_accuracy) / 2, 3),
            overall=round(avg, 3),
            confidence_trend=state.memory.confidence_trend[-10:],
            per_turn=totals,
        )
    }


def _build_personality_fragment(state: DSAState) -> str:
    """Build personality fragment from current pressure level.

    Always derived from the live pressure_level so tone escalates/relaxes
    as difficulty_adjuster changes pressure during the session.
    """
    company = state.config.target_company or ""
    personality = get_interviewer_personality(company, "dsa", state.pressure_level)
    return personality_to_prompt_fragment(personality)


def _safe_code_structure(cs: dict) -> dict | None:
    """Only pass 100%-accurate structural facts to the LLM responder.
    Excludes complexity estimates which are structural guesses that could
    conflict with the LLM's semantic understanding."""
    if not cs:
        return None
    return {
        "parses": cs.get("parses"),
        "syntax_error": cs.get("syntax_error"),
        "functions": cs.get("functions"),
        "has_return": cs.get("has_return"),
        "loop_depth": cs.get("loop_depth"),
        "loop_count": cs.get("loop_count"),
        "has_recursion": cs.get("has_recursion"),
        "structures_used": cs.get("structures_used"),
        "code_complete": cs.get("code_complete"),
        "has_boundary_check": cs.get("has_boundary_check"),
        "has_empty_input_guard": cs.get("has_empty_input_guard"),
        "dead_code_lines": cs.get("dead_code_lines"),
    }


def _contradiction_note(state: DSAState) -> str:
    c = state.latest_contradiction
    if not c:
        return ""
    return (
        f"CONTRADICTION DETECTED (severity {c.severity:.1f}): "
        f"Candidate previously said '{c.claim_before}' but now says '{c.claim_now}' "
        f"(topic: {c.topic}). Address this directly — name the inconsistency and ask them to resolve it."
    )


async def contextual_responder(state: DSAState) -> dict:
    intent = state.candidate_intent
    previous_followups = [record.followup_asked for record in state.memory.turns[-5:] if record.followup_asked]

    personality_fragment = _build_personality_fragment(state)
    contradiction_note = _contradiction_note(state)
    rolling_summary = state.memory.rolling_summary

    sys_prompt = _SYS_CONTEXTUAL
    if personality_fragment:
        sys_prompt = f"{_SYS_CONTEXTUAL}\n\nINTERVIEWER STYLE: {personality_fragment}"

    recent_cats = state.memory.recent_probe_categories
    consecutive_same = 0
    if recent_cats:
        for cat in reversed(recent_cats):
            if cat == recent_cats[-1]:
                consecutive_same += 1
            else:
                break
    recent_scores = [t.score.weighted_total for t in state.memory.turns[-3:]]

    test_run = _format_test_run(state)
    failure_diagnosis = ""
    if intent.raw_intent == "submitting_code" and test_run and not test_run["all_passed"] and test_run["failing_cases"]:
        failure_diagnosis = await _analyze_test_failures(state, test_run["failing_cases"])

    context = {
        "raw_intent": intent.raw_intent,
        "intent_summary": intent.summary,
        "approach_correct": intent.approach_correct,
        "question_asked": intent.question_asked,
        "frustration_level": intent.frustration_level,
        "candidate_latest": state.candidate_explanation[:1600],
        "problem": state.config.problem_statement[:1600],
        "code_tail": state.candidate_code[-1200:],
        "code_structure": _safe_code_structure(state.code_structure) if state.code_structure else None,
        "followup_question_prepared": state.followup_question,
        "hint": state.hint,
        "hint_tightness": state.hint_tightness,
        "interviewer_focus": intent.interviewer_focus,
        "score": state.session_scores.model_dump(),
        "flags": state.behaviour_profile.nervousness_flags[:4],
        "understanding": state.understanding.understanding_score,
        "thinks_aloud": state.behaviour_profile.speech.thinks_aloud,
        "previous_followups": previous_followups,
        "previous_hints": state.memory.hint_log[-5:],
        "weak_areas": state.memory.known_weak_areas[-6:],
        "pressure_level": state.pressure_level,
        "difficulty_level": state.difficulty_level,
        "consecutive_same_topic": consecutive_same,
        "recent_scores": recent_scores,
        "coverage_map": _build_coverage_map(state),
        "test_run": test_run,
        "failure_diagnosis": failure_diagnosis or None,
        "interview_phase": state.interview_phase,
        "phase_turns": state.phase_turns,
        "brute_force_given": state.brute_force_given,
    }
    if contradiction_note:
        context["CONTRADICTION"] = contradiction_note
    if rolling_summary:
        context["session_summary"] = rolling_summary[:600]

    reply = await generate_text(sys_prompt, json.dumps(context, ensure_ascii=False, default=str), temperature=0.35, max_tokens=260)
    if not reply:
        reply = _fallback_contextual_reply(state)
    if intent.raw_intent == "meta_complaint":
        lowered = reply.lower().strip()
        if not (lowered.startswith("you're right") or lowered.startswith("sorry")):
            reply = f"You're right; I was not responding to your actual point. {reply}"
    # If there's an unresolved contradiction and the reply doesn't mention it, prepend a note
    if contradiction_note and state.latest_contradiction and state.latest_contradiction.severity >= 0.6:
        if state.latest_contradiction.topic not in reply.lower():
            reply = (
                f"Wait — earlier you said '{state.latest_contradiction.claim_before}', "
                f"but now you're saying '{state.latest_contradiction.claim_now}'. "
                f"Which is it? {reply}"
            )
    return {"interviewer_reply": reply.strip()}


async def response_composer(state: DSAState) -> dict:
    return await contextual_responder(state)


def _ends_with_question(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith("?") or stripped.endswith("?\"")


def _reply_too_similar(candidate: str, previous: list[str]) -> bool:
    """Rough check: if > 60% of candidate words appear in any previous reply."""
    c_words = set(candidate.lower().split())
    if len(c_words) < 6:
        return False
    for prev in previous:
        p_words = set(prev.lower().split())
        overlap = len(c_words & p_words)
        if p_words and overlap / len(c_words) > 0.60:
            return True
    return False


def _pick_different_category_fallback(state: DSAState, current_reply: str) -> str | None:
    """If the current reply's category was used recently, find an alternative from a
    different category. Returns None if current category is fine."""
    category = _classify_probe(current_reply)
    recent_cats = state.memory.recent_probe_categories

    if not _category_recently_used(category, recent_cats, window=3):
        return None

    # Current category is stale — pick a fallback from a different category
    cs = state.code_structure
    all_candidates: list[tuple[str, str]] = []

    # Targeted code-structure questions with their categories
    if cs:
        if cs.get("loop_depth", 0) >= 2:
            all_candidates.append(("optimization", f"You have nested loops. Can you reduce the time complexity below {cs.get('estimated_time', 'O(n²)')}?"))
        if not cs.get("has_boundary_check") and cs.get("code_complete"):
            all_candidates.append(("edge_case_probe", "What happens when the input is empty or has a single element?"))
        if cs.get("has_recursion") and not cs.get("has_memoization"):
            all_candidates.append(("optimization", "Your recursion doesn't memoize. Can you cache repeated subproblems?"))
        if cs.get("structures_used"):
            structures = ", ".join(cs["structures_used"])
            all_candidates.append(("data_structure", f"You're using {structures}. What's the space cost?"))
        if not cs.get("code_complete") and cs.get("functions"):
            all_candidates.append(("code_structure", f"Your function `{cs['functions'][0]}` seems incomplete. Can you finish it?"))

    # Generic diverse probes
    all_candidates.extend([
        ("complexity_probe", "What is the time complexity of your current solution, and can you prove the bound?"),
        ("edge_case_probe", "What specific input makes your current approach incorrect?"),
        ("approach_choice", "Are there alternative patterns that might fit this problem better?"),
        ("invariant_check", "What invariant holds true at every step of your algorithm?"),
        ("walkthrough", "Walk me through the exact state at each step using the first test case."),
        ("tradeoff", "What are you trading off with this approach — time for space, or readability for speed?"),
        ("correctness", "How would you verify your solution is correct without running it?"),
        ("data_structure", "Which data structure gives you the fastest lookup for the inner operation?"),
        ("optimization", "If the input size doubles, how does your runtime change?"),
    ])

    # Pick first candidate whose category hasn't been used recently
    for cat, question in all_candidates:
        if not _category_recently_used(cat, recent_cats, window=3):
            return question

    return None


async def output_bundle(state: DSAState) -> dict:
    merged: dict = {}
    merged.update(score_reporter(state))

    # Run followup generator and contextual responder in parallel — they share
    # the same input state and don't depend on each other's output.
    followup_result, reply_result = await asyncio.gather(
        followup_generator(state),
        contextual_responder(state),
    )
    merged.update(followup_result)
    merged.update(reply_result)
    reply = (merged.get("interviewer_reply") or "").strip()

    # Step 3: if the contextual reply does not end with a question and there IS a
    # pre-computed follow-up, append it so the candidate always has one clear prompt.
    followup = (merged.get("followup_question") or "").strip()
    intent = state.candidate_intent.raw_intent
    if (
        intent not in {"asking_hint", "asking_clarification", "meta_complaint"}
        and followup
        and reply
        and not _ends_with_question(reply)
        and followup not in reply
    ):
        reply = f"{reply} {followup}"

    # Step 4: detect and handle the auto-advance token.
    if _ADVANCE_TOKEN in reply:
        reply = reply.replace(_ADVANCE_TOKEN, "").strip()
        merged["candidate_intent"] = state.candidate_intent.model_copy(
            update={"should_advance_question": True, "primary_intent": "advance_question"}
        )

    # Step 5: fallback anti-loop (category-based + text similarity).
    # This is a last-resort guard, not a first-pass filter — the LLM already
    # receives PREVIOUSLY_ASKED and should self-diversify. We only override when
    # BOTH signals fire together: same probe category used recently AND the reply
    # text is word-similar to a recent followup. Category-only match is expected
    # (e.g., two distinct complexity questions in the same session) and should not
    # trigger a swap. Text similarity alone without category match is also not
    # enough — LLMs often rephrase correctly.
    if reply:
        alt = _pick_different_category_fallback(state, reply)
        if alt:
            recent_texts = [r.followup_asked for r in state.memory.turns[-4:] if r.followup_asked]
            recent_texts += state.memory.hint_log[-3:]
            if _reply_too_similar(reply, recent_texts):
                reply = alt

    merged["interviewer_reply"] = reply or followup or _fallback_contextual_reply(state)

    # Track which category was used this turn (anti-loop window) and update aspect log
    final_category = _classify_probe(merged["interviewer_reply"])
    recent_cats = list(state.memory.recent_probe_categories)
    recent_cats.append(final_category)
    recent_cats = recent_cats[-6:]  # keep last 6 for window checks

    # Aspect tracking: add this category to the persistent asked_aspects list if not there.
    # We mark an aspect "covered" once it has been probed at least once with a non-trivial reply.
    asked_aspects = list(state.memory.asked_aspects)
    if final_category not in asked_aspects and len(merged["interviewer_reply"].split()) > 6:
        asked_aspects.append(final_category)

    # Merge memory updates (may already have a partial memory from hint_calibrator)
    existing_memory = merged.get("memory", state.memory)
    merged["memory"] = existing_memory.model_copy(update={
        "recent_probe_categories": recent_cats,
        "asked_aspects": asked_aspects,
    })

    return merged


def _fallback_contextual_reply(state: DSAState) -> str:
    intent = state.candidate_intent
    cs = state.code_structure

    if intent.raw_intent == "meta_complaint":
        if cs and cs.get("functions"):
            parts = []
            parts.append(f"Sorry — I can see your code.")
            funcs = cs["functions"]
            parts.append(f"You have `{funcs[0]}`")
            if cs.get("estimated_time"):
                parts.append(f"with {cs['estimated_time']} complexity ({cs.get('time_reason', '')}).")
            else:
                parts.append("defined.")
            if not cs.get("has_boundary_check"):
                parts.append("One thing: I don't see boundary checking for empty input.")
            elif not cs.get("code_complete"):
                parts.append("It looks incomplete — I see no return statement yet.")
            else:
                parts.append("Walk me through your core loop logic.")
            return " ".join(parts)
        code = state.candidate_code.strip()
        if code:
            snippet = code[-300:].strip()
            first_line = next((ln.strip() for ln in snippet.splitlines() if ln.strip()), "")
            return (
                f"Sorry — I can see your code. "
                f"Looking at what you have (ending with: `{first_line}`), "
                f"walk me through the core logic and I will respond to that directly."
            )
        return "You are right; I repeated myself instead of responding to your point. Let me reset: state your current logic in one line and I will check that exact reasoning."

    # Use code_structure for richer fallbacks when LLM is down
    if cs and intent.raw_intent in ("answering_followup", "idle", "explaining_approach"):
        if not cs.get("parses"):
            return f"I see a syntax error in your code: {cs.get('syntax_error', 'check your brackets and indentation')}. Fix that first, then we can discuss the logic."
        if not cs.get("code_complete") and cs.get("functions"):
            return f"Your function `{cs['functions'][0]}` looks incomplete — add the return logic, then I can review the full solution."
        if cs.get("loop_depth", 0) >= 2 and not cs.get("has_memoization"):
            return f"I see nested loops (depth {cs['loop_depth']}), giving {cs.get('estimated_time', 'O(n²)')}. Can you reduce that with a better data structure or memoization?"
        if not cs.get("has_boundary_check") and cs.get("code_complete"):
            return "Your logic looks structurally complete, but I don't see an early guard for empty or single-element input. What happens at the boundary?"

    if intent.approach_correct is True:
        return "Yes, that reasoning is on the right track. Go ahead and turn that invariant into code, and I will review the edge cases after you run it."
    if intent.approach_correct is False:
        return "There is a flaw in that reasoning; try a smaller counterexample and check whether the same count still holds. Which case breaks your formula?"
    if intent.should_clarify_problem:
        return "Good question. Let's clarify the exact input and output contract first."
    if state.hint:
        return state.hint
    if state.followup_question:
        return state.followup_question
    return intent.interviewer_focus or "Tell me what you are thinking right now, and I will respond to that directly."


def _fallback_followup(state: DSAState) -> str:
    intent = state.candidate_intent
    if intent.raw_intent in {"asking_hint", "asking_clarification", "meta_complaint"} or intent.should_give_hint:
        return intent.interviewer_focus or _fallback_hint(state, state.hint_tightness)
    if intent.approach_correct is True:
        return "Turn that exact reasoning into code now; I will check edge cases after you run it."
    if intent.approach_correct is False:
        return "Which smallest counterexample exposes the flaw in that reasoning?"

    depth = _compute_depth_signal(state)
    asked_before: set[str] = {
        record.followup_asked for record in state.memory.turns if record.followup_asked
    }
    asked_before.update(state.memory.hint_log)
    recent_cats = state.memory.recent_probe_categories

    # If candidate is stuck, force a different category
    force_different_category = depth["depth_signal"] == "move_on"

    def _not_asked(q: str) -> bool:
        q_low = q.lower()
        return not any(q_low in prev.lower() or prev.lower() in q_low for prev in asked_before)

    def _fresh_category(q: str) -> bool:
        if force_different_category and recent_cats:
            return _classify_probe(q) != recent_cats[-1]
        return not _category_recently_used(_classify_probe(q), recent_cats, window=3)

    # Generate targeted questions from code_structure analysis
    cs = state.code_structure
    targeted: list[str] = []
    if cs:
        if not cs.get("parses"):
            targeted.append(f"Your code has a syntax issue — {cs.get('syntax_error', 'check brackets')}. Can you fix it?")
        if not cs.get("code_complete") and cs.get("functions"):
            targeted.append(f"Your function `{cs['functions'][0]}` seems incomplete. Can you finish the return logic?")
        if cs.get("loop_depth", 0) >= 2:
            targeted.append(f"You have nested loops giving {cs.get('estimated_time', 'O(n²)')}. Is that the best you can do for this problem?")
        if not cs.get("has_boundary_check") and cs.get("code_complete"):
            targeted.append("What happens when the input is empty or has a single element?")
        if cs.get("has_recursion") and not cs.get("has_memoization"):
            targeted.append("Your recursion doesn't memoize. What is the time complexity, and can you cache repeated subproblems?")
        if cs.get("structures_used"):
            structures = ", ".join(cs["structures_used"])
            targeted.append(f"You're using {structures}. What's the space cost, and is there a way to reduce it?")
        if cs.get("dead_code_lines", 0) > 0:
            targeted.append("I see unreachable code after a return. Can you clean that up?")

    candidates = [
        "What specific input makes your current approach incorrect or slow?",
        "Walk me through the exact state your algorithm tracks at each step.",
        "What is the time complexity of your current solution, and can you reduce it?",
        "Which data structure would let you answer queries in O(1) or O(log n) here?",
        "Have you handled the empty input and single-element edge cases?",
        "If the input size doubles, how does your runtime change?",
        "Can you identify the repeated subproblem in your current approach?",
        "What would a two-pointer or sliding-window variant look like for this problem?",
        "How would you verify your solution is correct on the given examples?",
        "What invariant holds true at every step of your algorithm?",
    ]

    all_candidates = targeted + candidates

    # Prefer questions that are both not-asked AND from a fresh category
    for q in all_candidates:
        if _not_asked(q) and _fresh_category(q):
            return q

    # Relax: just not-asked (may repeat category)
    for q in all_candidates:
        if _not_asked(q):
            return q

    return "Can you optimise further without changing the core idea?"


async def brute_force_prober(state: DSAState) -> dict:
    """Demand a brute force approach when candidate has stalled without proposing one."""
    ctx = {
        "problem": state.config.problem_statement[:1200],
        "candidate_latest": state.candidate_explanation[:800],
        "phase_turns": state.phase_turns,
        "code_so_far": state.candidate_code[-400:] or "(none)",
    }
    reply = await generate_text(_SYS_BRUTE_FORCE_DEMAND, json.dumps(ctx, ensure_ascii=False, default=str), temperature=0.2, max_tokens=100)
    if not reply:
        reply = "Before we optimize, give me the simplest possible solution — even O(n²) — with the loop structure and time complexity stated explicitly."
    return {"interviewer_reply": reply.strip()}


async def silence_prober(state: DSAState) -> dict:
    """Probe a candidate who has gone silent to get them thinking out loud."""
    cs = state.code_structure
    ctx = {
        "problem": state.config.problem_statement[:800],
        "candidate_latest": state.candidate_explanation[:400] or "(no recent message)",
        "code_so_far": state.candidate_code[-400:] or "(none)",
        "longest_silence_s": state.silence_profile.longest_gap,
        "has_partial_code": bool(state.candidate_code.strip()),
        "first_function": cs.get("functions", [None])[0] if cs else None,
    }
    reply = await generate_text(_SYS_SILENCE_PROBE, json.dumps(ctx, ensure_ascii=False, default=str), temperature=0.3, max_tokens=80)
    if not reply:
        reply = "What are you thinking right now — even partial ideas are useful to say out loud."
    return {"interviewer_reply": reply.strip()}


async def walkthrough_prober(state: DSAState) -> dict:
    """Demand a step-by-step trace after all visible tests pass."""
    run = state.latest_code_run or {}
    test_cases = run.get("testcase_results", [])
    pick = next((tc for tc in test_cases if tc.get("passed")), None)
    trace_input = pick["input"] if pick else "the first example input"
    ctx = {
        "problem": state.config.problem_statement[:800],
        "code_tail": state.candidate_code[-800:],
        "trace_input": trace_input,
        "passed": run.get("passed_testcases", "all"),
        "total": run.get("total_testcases", ""),
    }
    reply = await generate_text(_SYS_WALKTHROUGH_DEMAND, json.dumps(ctx, ensure_ascii=False, default=str), temperature=0.2, max_tokens=100)
    if not reply:
        reply = f"All tests passed — now trace your algorithm step by step on input `{trace_input}`: initial state, each iteration's change, and the final return value."
    return {"interviewer_reply": reply.strip()}


async def time_pressure_pusher(state: DSAState) -> dict:
    """Push candidate to start coding when time is critically low and no code exists."""
    remaining_min = round(state.progress.remaining_seconds / 60, 1)
    approach = state.candidate_explanation[-300:] or "the approach you described"
    ctx = {
        "problem": state.config.problem_statement[:600],
        "remaining_minutes": remaining_min,
        "approach_mentioned": approach,
        "brute_force_given": state.brute_force_given,
    }
    reply = await generate_text(_SYS_TIME_PRESSURE, json.dumps(ctx, ensure_ascii=False, default=str), temperature=0.2, max_tokens=80)
    if not reply:
        approach_label = "your brute force approach" if state.brute_force_given else "even an O(n²) solution"
        reply = f"You have {remaining_min} minutes left — start coding {approach_label} now; an imperfect working solution beats a perfect one that never gets written."
    return {"interviewer_reply": reply.strip()}


def _fallback_hint(state: DSAState, tightness: str) -> str:
    patterns = state.config.allowed_patterns
    if tightness == "tight" and patterns:
        return f"Look for the invariant behind `{patterns[0]}` here, not the final code."
    if tightness == "medium":
        return "Identify the repeated work in your current approach, then decide what state would avoid recomputing it."
    return "Start from brute force, name the exact state/choice at each step, then collapse repeated work with the suitable pattern."
