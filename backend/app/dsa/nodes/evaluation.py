from __future__ import annotations

import asyncio
import re
import time

from app.dsa.schemas_llm import (
    ApproachLLM,
    ComplexityLLM,
    DebugLLM,
    ImplementationLLM,
    TestingLLM,
    UnderstandingLLM,
)
from app.dsa.state import (
    ApproachProfile,
    ComplexityProfile,
    DebugProfile,
    DSAState,
    ImplementationQuality,
    InterviewTimeline,
    TestingProfile,
    TimelineEvent,
    TurnScore,
    UnderstandingProfile,
)
from app.services.llm.factory import get_llm_provider
from app.utils.logger import logger

provider = get_llm_provider()

_SYS_UNDERSTAND = """You are a senior DSA interviewer assessing candidate understanding.
Return JSON with: time_to_first_clarification_s, clarifying_questions, constraint_interpretation_correct,
edge_cases_identified_early, misunderstood_constraints, score (0-1), answer_relevance.

answer_relevance (0-1): ONLY when an INTERVIEWER FOLLOW-UP is present, rate how directly and
correctly the candidate's reply answers THAT specific question, judged against the problem.
1.0 = fully and correctly addresses the exact question; 0.5 = partial/vague; 0.0 = ignores it,
deflects, or is wrong. If NO follow-up was asked, return answer_relevance = -1 (not applicable)."""

_SYS_APPROACH = """You are a senior DSA interviewer. Evaluate approach quality.
Return JSON with: brute_force_identified, brute_force_time, optimised_identified, approaches_attempted,
final_optimal, data_structures, patterns_recognised, pattern_recognition_score, approach_quality_score."""

_SYS_COMPLEXITY = """You are a senior DSA reviewer. Analyse complexity claims vs code reality.
Return JSON with: stated_time, stated_space, actual_time, actual_space, time_correct, space_correct,
optimisation_awareness, tradeoff_discussion_quality, accuracy_score."""

_SYS_IMPLEMENTATION = """You are a meticulous code reviewer. Evaluate implementation quality.
Return JSON with: compilation_success, syntax_errors, runtime_errors, logical_bugs, code_complete,
modular_score, naming_quality, readability_score, comment_quality, dead_code, redundant_loops,
repeated_logic, boundary_checks, null_empty_checks, overflow_handling."""

_SYS_TESTING = """You are a test quality reviewer. Return JSON with: test_cases_written,
edge_case_coverage, adversarial_tests, visible_test_pass_pct."""

_SYS_DEBUG = """You are assessing debugging quality. Return JSON with: time_to_first_success_s,
iterations, localisation_quality, strategy, fixes_root_cause, uses_logging_well."""


def _pending_followup(state: DSAState) -> str:
    """The interviewer question the candidate's current reply is answering.

    At evaluation time memory.turns holds only PRIOR turns, so the last recorded
    turn's followup_asked is exactly the question now being answered.
    """
    if state.memory.turns:
        return (state.memory.turns[-1].followup_asked or "").strip()
    return ""


async def explanation_listener(state: DSAState) -> dict:
    asked = _pending_followup(state)
    followup_block = f"\n\nINTERVIEWER FOLLOW-UP (the candidate is answering this):\n{asked}" if asked else ""
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_UNDERSTAND,
            user_prompt=(
                f"PROBLEM:\n{state.config.problem_statement}\n\n"
                f"EXPLANATION:\n{state.candidate_explanation}"
                f"{followup_block}"
            ),
            response_schema=UnderstandingLLM,
        )
    except Exception as exc:
        logger.warning("DSA understanding eval failed: %s", exc)
        result = UnderstandingLLM(score=_heuristic_understanding(state),
                                  answer_relevance=_heuristic_answer_relevance(state, asked))
    # Normalise answer_relevance: clamp to 0–1, treat the -1 "not applicable" sentinel as 0.
    rel = result.answer_relevance
    answer_relevance = max(0.0, min(1.0, rel)) if (asked and rel is not None and rel >= 0) else 0.0
    return {
        "understanding": UnderstandingProfile(
            clarifying_questions_asked=result.clarifying_questions,
            constraint_interpretation_correct=result.constraint_interpretation_correct,
            edge_cases_identified_early=result.edge_cases_identified_early,
            misunderstood_constraints=result.misunderstood_constraints,
            understanding_score=result.score,
            time_to_first_clarification_s=result.time_to_first_clarification_s,
            answer_relevance=answer_relevance,
        )
    }


def _heuristic_answer_relevance(state: DSAState, asked: str) -> float:
    """Keyword fallback for answer relevance when the LLM is unavailable.

    Rewards term overlap between the asked question and the reply, plus a small
    bonus for a substantive reply. Conservative — real grading needs the LLM.
    """
    if not asked:
        return -1.0
    reply = state.candidate_explanation.lower()
    if len(reply.split()) < 3:
        return 0.0
    import re as _re
    stop = {"the", "a", "an", "is", "are", "of", "to", "in", "for", "and", "or",
            "what", "how", "why", "would", "your", "you", "this", "that", "do", "does", "can", "if"}
    q_terms = {w for w in _re.findall(r"\b\w+\b", asked.lower()) if w not in stop and len(w) > 2}
    if not q_terms:
        return 0.4
    overlap = len(q_terms & set(_re.findall(r"\b\w+\b", reply))) / len(q_terms)
    return round(min(1.0, 0.2 + overlap * 0.8), 3)


async def dsa_evaluator(state: DSAState) -> dict:
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_APPROACH,
            user_prompt=(
                f"PROBLEM:\n{state.config.problem_statement}\n\n"
                f"CODE:\n{state.candidate_code}\n\n"
                f"EXPLANATION:\n{state.candidate_explanation}\n\n"
                f"EXPECTED SOLUTION:\n{state.config.expected_solution}"
            ),
            response_schema=ApproachLLM,
        )
    except Exception as exc:
        logger.warning("DSA approach eval failed: %s", exc)
        result = ApproachLLM(approach_quality_score=_heuristic_approach(state))
    return {
        "approach": ApproachProfile(
            brute_force_identified=result.brute_force_identified,
            brute_force_time_complexity=result.brute_force_time,
            optimised_identified=result.optimised_identified,
            approaches_attempted=result.approaches_attempted,
            final_approach_optimal=result.final_optimal,
            data_structure_used=result.data_structures,
            pattern_recognised=result.patterns_recognised,
            pattern_recognition_score=result.pattern_recognition_score,
            approach_quality_score=result.approach_quality_score,
        )
    }


async def approach_comparator(state: DSAState) -> dict:
    if not state.candidate_code.strip() and not state.complexity.stated_time:
        return {
            "complexity": ComplexityProfile(
                complexity_accuracy_score=_heuristic_complexity(state)
            )
        }
    # Build LLM prompt — enrich with tree-sitter structural facts when available
    cs = state.code_structure
    structural_hint = ""
    if cs:
        structural_hint = (
            f"\n\nSTRUCTURAL ANALYSIS (from parser, may not reflect semantic complexity):\n"
            f"  loop_depth={cs.get('loop_depth', '?')}, has_recursion={cs.get('has_recursion')}, "
            f"has_memoization={cs.get('has_memoization')}, structures={cs.get('structures_used')}, "
            f"structural_estimate_time={cs.get('estimated_time', '?')}, "
            f"structural_estimate_space={cs.get('estimated_space', '?')}"
        )

    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_COMPLEXITY,
            user_prompt=(
                f"PROBLEM:\n{state.config.problem_statement}\n\n"
                f"CODE:\n{state.candidate_code}\n\n"
                f"CANDIDATE STATED: time={state.complexity.stated_time} space={state.complexity.stated_space}\n\n"
                f"EXPECTED: time={state.config.expected_time_complexity} "
                f"space={state.config.expected_space_complexity}"
                f"{structural_hint}"
            ),
            response_schema=ComplexityLLM,
        )
    except Exception as exc:
        logger.warning("DSA complexity eval failed: %s", exc)
        # Fallback: use tree-sitter structural estimate (better than static 0.25)
        if cs:
            actual_time = cs.get("estimated_time", "")
            actual_space = cs.get("estimated_space", "")
            expected_time = state.config.expected_time_complexity.lower().replace(" ", "")
            expected_space = state.config.expected_space_complexity.lower().replace(" ", "")
            time_correct = _complexity_matches(actual_time, expected_time) if expected_time else True
            space_correct = _complexity_matches(actual_space, expected_space) if expected_space else True
            accuracy = (0.5 if time_correct else 0.0) + (0.5 if space_correct else 0.0)
            return {
                "complexity": ComplexityProfile(
                    stated_time=state.complexity.stated_time,
                    stated_space=state.complexity.stated_space,
                    actual_time=actual_time,
                    actual_space=actual_space,
                    time_correct=time_correct,
                    space_correct=space_correct,
                    optimisation_awareness=bool(state.complexity.stated_time),
                    tradeoff_discussion_quality=0.5 if state.complexity.stated_time else 0.0,
                    complexity_accuracy_score=accuracy,
                )
            }
        result = ComplexityLLM(accuracy_score=_heuristic_complexity(state))

    return {
        "complexity": ComplexityProfile(
            stated_time=result.stated_time,
            stated_space=result.stated_space,
            actual_time=result.actual_time,
            actual_space=result.actual_space,
            time_correct=result.time_correct,
            space_correct=result.space_correct,
            optimisation_awareness=result.optimisation_awareness,
            tradeoff_discussion_quality=result.tradeoff_discussion_quality,
            complexity_accuracy_score=result.accuracy_score,
        )
    }


def _complexity_matches(actual: str, expected: str) -> bool:
    """Check if estimated complexity matches expected (fuzzy)."""
    if not actual or not expected:
        return False
    a = actual.lower().replace(" ", "").replace("o(", "").replace(")", "")
    e = expected.lower().replace(" ", "").replace("o(", "").replace(")", "")
    if a == e:
        return True
    a_norm = a.replace("log", "log").replace("*", "")
    e_norm = e.replace("log", "log").replace("*", "")
    return a_norm == e_norm


async def understanding_scorer(state: DSAState) -> dict:
    if not state.candidate_code.strip():
        return {"testing": TestingProfile()}
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_TESTING,
            user_prompt=(
                f"PROBLEM:\n{state.config.problem_statement}\n\n"
                f"CODE:\n{state.candidate_code}"
            ),
            response_schema=TestingLLM,
        )
    except Exception as exc:
        logger.warning("DSA testing eval failed: %s", exc)
        result = TestingLLM()
    return {
        "testing": TestingProfile(
            test_cases_written=result.test_cases_written,
            edge_case_coverage=result.edge_case_coverage,
            adversarial_tests=result.adversarial_tests,
            visible_test_pass_pct=result.visible_test_pass_pct,
        )
    }


async def edge_case_checker(state: DSAState) -> dict:
    if not state.candidate_code.strip():
        return {"implementation": ImplementationQuality()}
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_IMPLEMENTATION,
            user_prompt=f"CODE:\n{state.candidate_code}",
            response_schema=ImplementationLLM,
        )
    except Exception as exc:
        logger.warning("DSA implementation eval failed: %s", exc)
        # Use tree-sitter analysis for meaningful fallback instead of static defaults
        cs = state.code_structure
        if cs:
            from app.dsa.code_analysis import analyze_code, analysis_to_implementation_fields
            analysis = analyze_code(state.candidate_code, state.code_language)
            fields = analysis_to_implementation_fields(analysis)
            result = ImplementationLLM(
                compilation_success=fields["compilation_success"],
                syntax_errors=fields["syntax_error_count"],
                code_complete=fields["code_complete"],
                naming_quality=fields["naming_quality"],
                readability_score=fields["readability_score"],
                dead_code=fields["dead_code_present"],
                boundary_checks=fields["boundary_checks_handled"],
            )
        else:
            result = ImplementationLLM(readability_score=0.5 if state.candidate_code.strip() else 0.0)
    return {
        "implementation": ImplementationQuality(
            compilation_success=result.compilation_success,
            syntax_error_count=result.syntax_errors,
            runtime_error_count=result.runtime_errors,
            logical_bug_count=result.logical_bugs,
            code_complete=result.code_complete,
            modular_score=result.modular_score,
            naming_quality=result.naming_quality,
            readability_score=result.readability_score,
            comment_quality=result.comment_quality,
            dead_code_present=result.dead_code,
            redundant_loops=result.redundant_loops,
            repeated_logic=result.repeated_logic,
            boundary_checks_handled=result.boundary_checks,
            null_empty_checks=result.null_empty_checks,
            overflow_handling=result.overflow_handling,
        )
    }


async def complexity_tracker(state: DSAState) -> dict:
    editor = state.editor_signals
    if editor.run_count == 0 and editor.time_debugging_s < 1:
        return {
            "debug_profile": DebugProfile(
                debug_iterations=0,
                bug_localisation_quality=min(1.0, editor.run_count * 0.08),
            )
        }
    try:
        result = await provider.generate_structured_output(
            system_prompt=_SYS_DEBUG,
            user_prompt=(
                f"Run count: {editor.run_count}\n"
                f"Submit count: {editor.submit_count}\n"
                f"Time debugging: {editor.time_debugging_s:.1f}s\n"
                f"Rewrite count: {editor.rewrite_count}\n"
                f"CODE:\n{state.candidate_code}"
            ),
            response_schema=DebugLLM,
        )
    except Exception as exc:
        logger.warning("DSA debug eval failed: %s", exc)
        result = DebugLLM(
            localisation_quality=min(1.0, editor.run_count * 0.08),
            iterations=editor.run_count,
        )
    return {
        "debug_profile": DebugProfile(
            time_to_first_success_s=result.time_to_first_success_s,
            debug_iterations=result.iterations,
            bug_localisation_quality=result.localisation_quality,
            debug_strategy=result.strategy,
            fixes_root_cause=result.fixes_root_cause,
            uses_logging_well=result.uses_logging_well,
        )
    }


_COMMON_CODE_TOKENS = frozenset({
    "def", "return", "if", "else", "elif", "for", "while", "in", "not",
    "and", "or", "self", "len", "range", "true", "false", "none",
    "class", "import", "from", "pass", "break", "continue", "int", "str",
})


def plagiarism_detector(state: DSAState) -> dict:
    """Structural plagiarism check — no LLM cost.

    Flags copy-paste events and high token overlap with the expected solution
    in the first two turns (when genuine plagiarism is most likely).
    """
    likelihood = 0.0

    if state.editor_signals.copy_paste_detected:
        likelihood = max(likelihood, 0.65)

    candidate = state.candidate_code.strip()
    expected = state.config.expected_solution.strip()
    if candidate and expected and state.turn_number <= 2:
        c_tokens = set(re.findall(r"\b\w+\b", candidate.lower())) - _COMMON_CODE_TOKENS
        e_tokens = set(re.findall(r"\b\w+\b", expected.lower())) - _COMMON_CODE_TOKENS
        if e_tokens:
            overlap = len(c_tokens & e_tokens) / len(e_tokens)
            if overlap > 0.80:
                likelihood = max(likelihood, 0.55)

    scratch = dict(state.scratch)
    scratch["_plagiarism_likelihood"] = likelihood
    return {"scratch": scratch}


async def evaluation_parallel(state: DSAState) -> dict:
    """Run independent LLM evaluations in parallel.

    Plagiarism check is now a zero-cost structural heuristic (no LLM call),
    so total parallel calls dropped from 4 to 3.
    """
    merged: dict = plagiarism_detector(state)  # sync, no LLM
    results = await asyncio.gather(
        explanation_listener(state),
        dsa_evaluator(state),
        approach_comparator(state),
        return_exceptions=True,
    )
    for item in results:
        if isinstance(item, Exception):
            logger.warning("Parallel DSA evaluation error: %s", item)
            continue
        merged.update(item)
    return merged


async def evaluation_dependent(state: DSAState) -> dict:
    results = await asyncio.gather(
        understanding_scorer(state),
        edge_case_checker(state),
        complexity_tracker(state),
        return_exceptions=True,
    )
    merged: dict = {}
    for item in results:
        if isinstance(item, Exception):
            logger.warning("Dependent DSA evaluation error: %s", item)
            continue
        merged.update(item)
    return merged


def timeline_builder(state: DSAState) -> dict:
    editor = state.editor_signals
    base = state.audio_meta.start_ts
    events: list[TimelineEvent] = []
    phases = [
        ("problem_reading", 0, editor.first_keystroke_latency),
        ("clarification", editor.first_keystroke_latency, editor.first_keystroke_latency + 30),
        (
            "brute_force",
            editor.first_keystroke_latency + 30,
            editor.first_keystroke_latency + 90,
        ),
        (
            "implementation",
            editor.first_keystroke_latency + editor.time_planning_s + 60,
            editor.first_keystroke_latency + editor.time_planning_s + editor.time_coding_s + 60,
        ),
        (
            "debugging",
            editor.first_keystroke_latency + editor.time_planning_s + editor.time_coding_s,
            editor.first_keystroke_latency
            + editor.time_planning_s
            + editor.time_coding_s
            + editor.time_debugging_s,
        ),
    ]
    for phase_name, start_off, end_off in phases:
        if end_off > start_off:
            events.append(
                TimelineEvent(
                    phase=phase_name,
                    start_ts=base + start_off,
                    end_ts=base + end_off,
                    duration_s=end_off - start_off,
                )
            )
    current = "debugging" if editor.run_count > 0 else "implementation"
    return {
        "timeline": InterviewTimeline(
            events=[*state.timeline.events, *events][-20:],
            current_phase=current,
            phase_start_ts=time.time(),
        )
    }


def pattern_recogniser(state: DSAState) -> dict:
    known = set(state.config.allowed_patterns)
    recognised = set(state.approach.pattern_recognised)
    score = len(recognised & known) / max(len(known), 1) if known else state.approach.pattern_recognition_score
    approach = state.approach.model_copy(update={"pattern_recognition_score": round(score, 3)})
    return {"approach": approach}


def eval_aggregator(state: DSAState) -> dict:
    understanding = state.understanding.understanding_score
    approach = state.approach.approach_quality_score
    complexity = state.complexity.complexity_accuracy_score
    implementation = (
        state.implementation.modular_score * 0.25
        + state.implementation.readability_score * 0.25
        + state.implementation.naming_quality * 0.20
        + (1.0 if state.implementation.compilation_success else 0.0) * 0.30
    )
    debugging = state.debug_profile.bug_localisation_quality
    communication = (
        (1.0 if state.behaviour_profile.speech.thinks_aloud else 0.0) * 0.4
        + (1.0 if state.behaviour_profile.speech.explains_intuition else 0.0) * 0.6
    )
    behavioural = state.behaviour_profile.overall_confidence
    answer_relevance = state.understanding.answer_relevance

    # When the candidate is answering an interviewer follow-up, how well they
    # addressed THAT question is a first-class signal — give it real weight by
    # rebalancing the standard weights so they still sum to 1.0.
    answered_followup = bool(_pending_followup(state))
    if answered_followup:
        weighted = (
            understanding * 0.12
            + approach * 0.25
            + complexity * 0.13
            + implementation * 0.18
            + debugging * 0.08
            + communication * 0.04
            + behavioural * 0.05
            + answer_relevance * 0.15
        )
    else:
        weighted = (
            understanding * 0.15
            + approach * 0.30
            + complexity * 0.15
            + implementation * 0.20
            + debugging * 0.10
            + communication * 0.05
            + behavioural * 0.05
        )
    turn_score = TurnScore(
        understanding=round(understanding, 3),
        approach_quality=round(approach, 3),
        complexity_accuracy=round(complexity, 3),
        implementation=round(implementation, 3),
        debugging=round(debugging, 3),
        communication=round(communication, 3),
        behavioural=round(behavioural, 3),
        answer_relevance=round(answer_relevance, 3),
        weighted_total=round(weighted, 3),
        missed_edge_cases=state.understanding.misunderstood_constraints,
        suggested_followups=[],
    )
    evaluation = {
        "correctness_score": round(turn_score.approach_quality * 10, 1),
        "optimization_score": round(turn_score.complexity_accuracy * 10, 1),
        "debugging_score": round(turn_score.debugging * 10, 1),
        "communication_score": round(turn_score.communication * 10, 1),
        "edge_case_handling_score": round(state.testing.edge_case_coverage * 10, 1),
        "detected_strengths": state.memory.known_strong_areas[:5],
        "detected_weaknesses": state.memory.known_weak_areas[:5],
        "follow_up_questions": [state.followup_question] if state.followup_question else [],
        "confidence_score": round(behavioural * 10, 1),
        "reasoning": f"Weighted turn score {weighted:.2f} from approach, complexity, implementation, and behaviour.",
    }
    comparison = {
        "alignment_score": round(approach * 10, 1),
        "expected_alignment_score": 8.0,
        "missing_concepts": state.understanding.misunderstood_constraints,
        "extra_risk_flags": state.behaviour_profile.panic_indicators[:5],
        "recommended_improvements": state.understanding.edge_cases_identified_early[:3],
        "confidence_score": round(behavioural * 10, 1),
        "reasoning": state.complexity.actual_time or "Complexity analysis pending.",
    }
    return {"turn_score": turn_score, "evaluation": evaluation, "comparison": comparison}


def _heuristic_understanding(state: DSAState) -> float:
    text = state.candidate_explanation.lower()
    score = 0.0
    if "?" in text or "clarif" in text:
        score += 0.2
    if any(term in text for term in ("constraint", "edge", "input", "output")):
        score += 0.2
    if len(text.split()) > 30:
        score += 0.1
    if len(text.split()) > 60:
        score += 0.1
    return round(min(1.0, score), 3)


_ALGO_TERMS = (
    "hash map", "hash table", "sliding window", "two pointer", "two pointers",
    "dynamic programming", "memoization", "dp", "bfs", "dfs", "binary search",
    "stack", "queue", "heap", "priority queue", "trie", "prefix sum",
    "monotonic", "greedy", "backtracking", "divide and conquer",
)
_DEPTH_PHRASES = (
    "because", "since", "so that", "in order to", "this gives", "which means",
    "therefore", "as a result", "to avoid", "the idea is", "key insight",
)
_COMPLEXITY_TERMS = ("o(n", "o(log", "o(1)", "linear time", "constant time",
                     "quadratic", "n squared", "n^2", "log n", "n log n")


def _heuristic_approach(state: DSAState) -> float:
    expl = state.candidate_explanation.lower()
    combined = (expl + " " + state.candidate_code.lower())
    words = expl.split()
    score = 0.0

    # Reward matching specific algorithm patterns — but only once per family
    algo_hits = sum(1 for t in _ALGO_TERMS if t in combined)
    score += min(0.40, algo_hits * 0.12)

    # Reward causal reasoning — "I'd use X because Y" shows actual understanding
    if any(p in expl for p in _DEPTH_PHRASES):
        score += 0.15

    # Reward complexity discussion
    if any(t in expl for t in _COMPLEXITY_TERMS):
        score += 0.15

    # Reward length proportional to 50 words — longer coherent explanations score higher
    score += min(0.15, len(words) / 50 * 0.15)

    # Reward brute-force / optimization transition — a key interview signal
    if any(t in expl for t in ("brute force", "naive", "optimise", "optimize", "better approach", "improve")):
        score += 0.10

    return round(min(1.0, score), 3)


def _heuristic_complexity(state: DSAState) -> float:
    text = state.candidate_explanation.lower()
    if "o(" in text or "complex" in text:
        return 0.65
    return 0.0
