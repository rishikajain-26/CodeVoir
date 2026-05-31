from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.dsa.code_analysis import analyze_code, analysis_to_context_dict
from app.dsa.nodes import evaluation, ingestion, intent, memory, output, report, signals
from app.dsa.nodes.compression import memory_compressor
from app.dsa.nodes.contradiction import contradiction_detector
from app.dsa.nodes.difficulty import difficulty_adjuster
from app.dsa.state import DSAState

# Module-level constants so they're accessible before any use inside phase_tracker
_BRUTE_SIGNALS = (
    "brute force", "naive", "o(n2)", "o(n^2)", "o(n²)", "nested loop",
    "check all", "every pair", "all combinations", "simple approach",
    "straightforward", "linear scan", "n squared",
)
_OPT_SIGNALS = (
    "optimize", "optimise", "better approach", "o(n log", "o(n)", "hash map",
    "two pointer", "sliding window", "dynamic programming", "binary search",
    "greedy", "monotonic", "prefix sum", "memoiz",
)


def phase_tracker(state: DSAState) -> dict:
    """Infer the current interview phase from candidate content, code, and editor signals.

    Runs after evaluation so approach/complexity profiles are current.
    Only transitions forward — phases never regress.
    """
    phase = state.interview_phase
    phase_turns = state.phase_turns
    explanation = state.candidate_explanation.lower()
    code = state.candidate_code.strip()
    run_count = state.editor_signals.run_count
    trigger = state.trigger

    # Keyword match is authoritative — don't wait for LLM eval to set brute_force_given
    brute_force_from_text = any(sig in explanation for sig in _BRUTE_SIGNALS)
    brute_force_given = state.brute_force_given or state.approach.brute_force_identified or brute_force_from_text
    optimized = state.optimized_approach_confirmed or state.approach.final_approach_optimal

    new_phase = phase

    # reading → clarification: candidate starts asking or explains understanding
    if phase == "reading" and (len(explanation.split()) > 8 or "?" in explanation):
        new_phase = "clarification"

    # → brute_force: any concrete approach is named
    if phase in ("reading", "clarification"):
        if any(sig in explanation for sig in _BRUTE_SIGNALS) or state.approach.brute_force_identified:
            new_phase = "brute_force"
            brute_force_given = True

    # → optimization: candidate moves beyond brute force
    if phase == "brute_force":
        if any(sig in explanation for sig in _OPT_SIGNALS) or state.approach.optimised_identified:
            new_phase = "optimization"

    # → coding: non-trivial code appears in the editor
    # Use new_phase (not phase) so we don't overwrite a just-set optimization transition
    if new_phase in ("reading", "clarification", "brute_force", "optimization"):
        if code and len(code.splitlines()) > 3:
            new_phase = "coding"

    # → testing: candidate explicitly submits code.
    # Do NOT use run_count here — it comes from editor_events which may be stale
    # (loaded from prior_state) and would permanently trap the phase at "testing"
    # after the first run even on purely verbal turns.
    if trigger == "code_submit":
        if phase != "closing":
            new_phase = "testing"

    # → closing: last question and round is effectively complete
    if (
        state.progress.current_question_index >= state.progress.total_questions
        and optimized
        and state.implementation.code_complete
    ):
        new_phase = "closing"

    if new_phase != phase:
        phase_turns = 0
    else:
        phase_turns += 1

    return {
        "interview_phase": new_phase,
        "phase_turns": phase_turns,
        "brute_force_given": brute_force_given,
        "optimized_approach_confirmed": optimized,
    }


def phase_router(state: DSAState) -> str:
    """Route to the appropriate response node based on interview phase and session signals.

    Called as a conditional edge after phase_tracker. Returns the graph node key.
    """
    phase = state.interview_phase
    phase_turns = state.phase_turns
    remaining_s = state.progress.remaining_seconds
    total_s = state.progress.allocated_minutes * 60
    time_fraction = remaining_s / max(total_s, 1) if total_s > 0 else 1.0
    code = state.candidate_code.strip()
    run = state.latest_code_run or {}

    # 1. Time critical: <25% time left and no code written → push to code NOW
    if time_fraction < 0.25 and not code and total_s > 0:
        return "time_pressure_push"

    # 2. Silence: candidate hasn't said anything meaningful and is in an early phase.
    # Two signals: real audio gap data (when frontend sends it) OR heuristic
    # (very short response + stuck in same phase ≥2 turns with no code).
    candidate_words = len(state.candidate_explanation.split())
    has_real_silence = state.silence_profile.longest_gap > 20
    heuristic_silence = candidate_words < 5 and phase_turns >= 2 and not code
    if (
        (has_real_silence or heuristic_silence)
        and phase in ("reading", "clarification", "brute_force")
    ):
        return "silence_probe"

    # 3. Brute force gate: candidate has spent ≥3 turns without proposing any approach
    if phase in ("reading", "clarification") and phase_turns >= 3 and not state.brute_force_given:
        return "demand_brute_force"

    # 4. Walkthrough: code just submitted and all tests passed
    passed = int(run.get("passed_testcases", 0) or 0)
    total_tc = int(run.get("total_testcases", 0) or 0)
    if state.trigger == "code_submit" and total_tc > 0 and passed == total_tc:
        return "code_walkthrough"

    # 5. Default: normal output pipeline
    return "output_turn"


async def ingest_bundle(state: DSAState) -> dict:
    merged: dict = {}
    merged.update(ingestion.session_loader(state))
    state_after = state.model_copy(update=merged)
    merged.update(await ingestion.audio_ingest(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(await ingestion.code_stream_ingest(state_after))

    # Static code analysis via tree-sitter (zero LLM cost, <10ms)
    if state.candidate_code.strip():
        analysis = analyze_code(state.candidate_code, state.code_language)
        merged["code_structure"] = analysis_to_context_dict(analysis)

    return merged


def signals_bundle(state: DSAState) -> dict:
    merged: dict = {}
    merged.update(signals.speech_signal_extractor(state))
    state_after = state.model_copy(update=merged)
    merged.update(signals.editor_event_analyser(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(signals.silence_gap_detector(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(signals.behaviour_aggregator(state_after))
    return merged


async def post_evaluation_bundle(state: DSAState) -> dict:
    merged: dict = {}
    merged.update(evaluation.timeline_builder(state))
    state_after = state.model_copy(update=merged)
    merged.update(evaluation.pattern_recogniser(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(evaluation.eval_aggregator(state_after))
    return merged


async def adaptive_bundle(state: DSAState) -> dict:
    """Contradiction detection followed by difficulty adjustment."""
    merged: dict = {}
    merged.update(await contradiction_detector(state))
    state_after = state.model_copy(update=merged)
    merged.update(difficulty_adjuster(state_after))
    return merged


async def compose_after_hint(state: DSAState) -> dict:
    return await output.contextual_responder(state)


async def question_advancer(state: DSAState) -> dict:
    """Handle explicit question advancement — generate a clean bridging reply
    and reset all per-question state fields so the next turn starts fresh.

    The actual problem swap happens in run_dsa_turn_async AFTER the graph
    finishes, so we only need to produce the transition message here.
    """
    from app.dsa.llm_text import generate_text

    q_index = state.progress.current_question_index
    total = state.progress.total_questions
    next_q = q_index + 1

    if next_q > total:
        reply = (
            f"That wraps up all {total} question(s) for this round. "
            "End the interview to generate your full report."
        )
    else:
        ctx = {
            "current_question_index": q_index,
            "next_question_index": next_q,
            "total_questions": total,
            "candidate_said": state.candidate_explanation[:300],
        }
        import json as _json
        reply = await generate_text(
            "You are a DSA interviewer. The candidate is moving to the next coding problem. "
            "Write ONE short sentence acknowledging the move (e.g. 'Got it, let's move to Q2.'). "
            "Do NOT reveal the next problem — it will appear on screen separately. "
            "Do NOT ask a question. Plain text only.",
            _json.dumps(ctx, ensure_ascii=False),
            temperature=0.2,
            max_tokens=50,
        )
        if not reply:
            reply = f"Got it — moving to question {next_q} of {total}."

    # Clear per-question memory so Q2 starts with a clean conversation slate.
    # Cross-question tracking (weak/strong areas, confidence trend, behaviour
    # history, approach patterns, cumulative hints_given) is preserved.
    clean_memory = state.memory.model_copy(
        update={
            "turns": [],
            "hint_log": [],
            "recent_probe_categories": [],
            "asked_aspects": [],
            "rolling_summary": "",
        }
    )

    return {
        "interviewer_reply": reply.strip(),
        "memory": clean_memory,
        # Reset all per-question tracking fields
        "interview_phase": "reading",
        "phase_turns": 0,
        "brute_force_given": False,
        "optimized_approach_confirmed": False,
        "candidate_code": "",
        "latest_code_run": {},
        "hint": None,
        "followup_question": "",
    }


def pre_router(state: DSAState) -> str:
    intent_state = state.candidate_intent
    if state.progress.time_expired or intent_state.should_end_round:
        return "generate_report"
    # Advance question short-circuits full evaluation — no need to score the old problem
    if intent_state.should_advance_question and not state.progress.round_complete:
        return "advance_question"
    if state.next_action == "direct_reply":
        return "direct_reply"
    if state.next_action == "escalate_hint":
        return "escalate_hint"
    return "full_eval"


def build_dsa_graph():
    graph = StateGraph(DSAState)

    graph.add_node("resolve_intent", intent.resolve_candidate_intent)
    graph.add_node("advance_question", question_advancer)
    graph.add_node("ingest", ingest_bundle)
    graph.add_node("signals", signals_bundle)
    graph.add_node("evaluate_parallel", evaluation.evaluation_parallel)
    graph.add_node("evaluate_dependent", evaluation.evaluation_dependent)
    graph.add_node("post_evaluate", post_evaluation_bundle)
    graph.add_node("adaptive", adaptive_bundle)
    graph.add_node("phase_tracker", phase_tracker)
    graph.add_node("memory_update", memory.memory_update_bundle)
    graph.add_node("compress_memory", memory_compressor)
    graph.add_node("output_turn", output.output_bundle)
    graph.add_node("silence_probe", output.silence_prober)
    graph.add_node("demand_brute_force", output.brute_force_prober)
    graph.add_node("code_walkthrough", output.walkthrough_prober)
    graph.add_node("time_pressure_push", output.time_pressure_pusher)
    graph.add_node("hint_calibrator", output.hint_calibrator)
    graph.add_node("compose_hint", compose_after_hint)
    graph.add_node("direct_reply", output.contextual_responder)
    graph.add_node("report_finalize", report.report_bundle)

    graph.set_entry_point("resolve_intent")
    graph.add_conditional_edges(
        "resolve_intent",
        pre_router,
        {
            "advance_question": "advance_question",
            "direct_reply": "direct_reply",
            "escalate_hint": "hint_calibrator",
            "generate_report": "report_finalize",
            "full_eval": "ingest",
        },
    )
    graph.add_edge("advance_question", "memory_update")
    graph.add_edge("ingest", "signals")
    graph.add_edge("signals", "evaluate_parallel")
    graph.add_edge("evaluate_parallel", "evaluate_dependent")
    graph.add_edge("evaluate_dependent", "post_evaluate")
    graph.add_edge("post_evaluate", "adaptive")
    graph.add_edge("adaptive", "phase_tracker")
    graph.add_conditional_edges(
        "phase_tracker",
        phase_router,
        {
            "time_pressure_push": "time_pressure_push",
            "silence_probe": "silence_probe",
            "demand_brute_force": "demand_brute_force",
            "code_walkthrough": "code_walkthrough",
            "output_turn": "output_turn",
        },
    )
    graph.add_edge("output_turn", "memory_update")
    graph.add_edge("silence_probe", "memory_update")
    graph.add_edge("demand_brute_force", "memory_update")
    graph.add_edge("code_walkthrough", "memory_update")
    graph.add_edge("time_pressure_push", "memory_update")
    graph.add_edge("memory_update", "compress_memory")
    graph.add_edge("hint_calibrator", "compose_hint")
    graph.add_edge("compose_hint", "memory_update")
    graph.add_edge("direct_reply", "memory_update")
    graph.add_edge("compress_memory", END)
    graph.add_edge("report_finalize", END)

    return graph.compile()


DSA_GRAPH = build_dsa_graph()


async def run_dsa_turn(
    state: DSAState,
    *,
    candidate_code: str | None = None,
    candidate_explanation: str | None = None,
    audio_meta_dict: dict | None = None,
    editor_events_raw: list[dict] | None = None,
) -> DSAState:
    from app.dsa.state import AudioMeta, EditorEvent

    updates: dict = {
        "hint": None,
        "followup_question": "",
    }
    if candidate_code is not None:
        updates["candidate_code"] = candidate_code
    if candidate_explanation is not None:
        updates["candidate_explanation"] = candidate_explanation
    if audio_meta_dict:
        updates["audio_meta"] = AudioMeta(**audio_meta_dict)
    if editor_events_raw:
        updates["editor_events"] = [EditorEvent(**event) for event in editor_events_raw]

    updated = state.model_copy(update=updates)
    result = await DSA_GRAPH.ainvoke(updated)
    if isinstance(result, dict):
        return DSAState.model_validate(result)
    return result
