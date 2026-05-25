from __future__ import annotations

from app.dsa.state import (
    AudioMeta,
    DSAState,
    EditorEvent,
    EditorSignals,
    SessionConfig,
    SilenceProfile,
    SpeechSignals,
)
from app.services.interview_data_service import get_dsa_config


FILLERS = {
    "um",
    "uh",
    "like",
    "basically",
    "you",
    "know",
    "so",
    "right",
    "okay",
    "kind",
    "of",
    "actually",
}


async def audio_ingest(state: DSAState) -> dict:
    meta = state.audio_meta
    words = state.candidate_explanation.lower().split()
    filler_count = sum(1 for word in words if word in FILLERS)
    filler_ratio = filler_count / max(len(words), 1)
    explanation = state.candidate_explanation.lower()
    thinks_aloud = len(words) > 40 and filler_ratio < 0.15
    explains_intuition = any(
        keyword in explanation
        for keyword in ("because", "since", "reason", "intuition", "key insight", "notice")
    )
    speech = SpeechSignals(
        wpm=meta.wpm,
        filler_ratio=round(filler_ratio, 3),
        hesitation_count=meta.hesitation_count,
        tone_label=meta.tone_label,
        avg_sentence_len=meta.avg_sentence_len,
        thinks_aloud=thinks_aloud,
        explains_intuition=explains_intuition,
    )
    gaps = list(meta.silence_gaps)
    longest = max(gaps, default=0.0)
    confidence = max(0.0, 1.0 - longest / 15.0)
    silence = SilenceProfile(
        gaps=gaps,
        longest_gap=longest,
        total_silence=sum(gaps),
        confidence_proxy=round(confidence, 3),
    )
    return {"speech_signals": speech, "silence_profile": silence}


async def code_stream_ingest(state: DSAState) -> dict:
    events = state.editor_events
    if not events:
        return {"editor_signals": EditorSignals()}

    timestamps = [event.ts for event in events]
    start, end = min(timestamps), max(timestamps)
    duration_min = max((end - start) / 60.0, 0.01)
    inserts = [event for event in events if event.action == "insert"]
    deletes = [event for event in events if event.action == "delete" and len(event.chars) > 3]
    rewrites = [event for event in events if event.action == "replace_block"]
    switches = [event for event in events if event.action == "approach_switch"]
    pastes = [event for event in events if event.action == "copy_paste"]
    runs = [event for event in events if event.action == "run"]
    submits = [event for event in events if event.action == "submit"]
    total_edit_events = len(inserts) + len(deletes)
    first_keystroke = timestamps[0] - state.audio_meta.start_ts if timestamps else 0.0
    first_run_ts = runs[0].ts if runs else end
    time_coding = first_run_ts - (timestamps[0] if timestamps else start)
    time_debugging = (end - first_run_ts) if runs else 0.0

    return {
        "editor_signals": EditorSignals(
            edits_per_minute=round(total_edit_events / duration_min, 2),
            backspace_frequency=round(len(deletes) / max(total_edit_events, 1), 3),
            rewrite_count=len(rewrites),
            approach_switches=len(switches),
            first_keystroke_latency=round(first_keystroke, 2),
            copy_paste_detected=len(pastes) > 0,
            run_count=len(runs),
            submit_count=len(submits),
            time_planning_s=round(first_keystroke, 2),
            time_coding_s=round(max(time_coding, 0), 2),
            time_debugging_s=round(max(time_debugging, 0), 2),
        )
    }


def session_loader(state: DSAState) -> dict:
    raw = get_dsa_config(state.config.target_company)
    problem_bank = raw.get("problem_bank", {}) if isinstance(raw, dict) else {}
    patterns = raw.get("patterns", []) or problem_bank.get("patterns", []) or state.config.allowed_patterns
    total_questions = int(raw.get("question_count", state.config.total_questions) or state.config.total_questions)
    allocated_minutes = int(
        state.progress.allocated_minutes
        or state.config.allocated_minutes
        or raw.get("minutes", 45)
    )
    per_question_minutes = round(allocated_minutes / max(total_questions, 1), 1)
    max_turns = max(12, total_questions * 12)
    cfg = state.config.model_copy(
        update={
            "problem_statement": state.config.problem_statement or problem_bank.get("prompt", ""),
            "expected_solution": state.config.expected_solution or problem_bank.get("expected_solution", ""),
            "expected_time_complexity": state.config.expected_time_complexity
            or problem_bank.get("time_complexity", ""),
            "expected_space_complexity": state.config.expected_space_complexity
            or problem_bank.get("space_complexity", ""),
            "allowed_patterns": patterns or state.config.allowed_patterns,
            "max_hints": int(raw.get("max_hints", state.config.max_hints) or state.config.max_hints),
            "max_turns": max_turns,
            "total_questions": total_questions,
            "allocated_minutes": allocated_minutes,
            "per_question_minutes": per_question_minutes,
        }
    )
    progress = state.progress.model_copy(
        update={
            "total_questions": total_questions,
            "company_minutes": int(raw.get("minutes", state.progress.company_minutes) or 45),
            "allocated_minutes": allocated_minutes,
            "per_question_minutes": per_question_minutes,
            "current_question_index": max(
                1,
                min(state.progress.current_question_index or 1, total_questions),
            ),
            "label": (
                f"Question {max(1, min(state.progress.current_question_index or 1, total_questions))}"
                f" of {total_questions}"
            ),
        }
    )
    return {"config": cfg, "progress": progress}


def build_audio_meta_from_session(
    explanation: str,
    metrics: dict | None = None,
    behavioral: dict | None = None,
) -> AudioMeta:
    metrics = metrics or {}
    behavioral = behavioral or {}
    words = explanation.split()
    duration_ms = int(metrics.get("speech_duration_ms", 0) or 0)
    wpm = (len(words) / max(duration_ms / 60000.0, 0.25)) if words else 0.0
    gaps = list(metrics.get("silence_gaps") or behavioral.get("idle_gap_seconds") or [])
    if isinstance(gaps, (int, float)):
        gaps = [float(gaps)]
    tone = "neutral"
    if behavioral.get("nervous_markers", 0) > 2:
        tone = "nervous"
    elif behavioral.get("filler_words", 0) > 5:
        tone = "nervous"
    return AudioMeta(
        wpm=round(wpm, 1),
        filler_count=int(behavioral.get("filler_words", 0) or 0),
        hesitation_count=int(metrics.get("hesitations", 0) or behavioral.get("hesitations", 0) or 0),
        tone_label=tone,
        avg_sentence_len=round(len(words) / max(len(explanation.split(".")), 1), 1),
        silence_gaps=[float(g) for g in gaps if g],
    )


def build_editor_events_from_session(session: dict, code: str) -> list[EditorEvent]:
    import time

    events: list[EditorEvent] = []
    now = time.time()
    signals = session.get("behavioral_signals", {})
    snapshots = session.get("code_snapshots", [])
    runs = session.get("code_runs", [])

    if signals.get("paste_events", 0) > 0 or signals.get("large_pastes", 0) > 0:
        events.append(EditorEvent(ts=now - 30, action="copy_paste", chars=code[:200]))
    if signals.get("delete_events", 0) > 3:
        events.append(EditorEvent(ts=now - 20, action="delete", chars="block"))
    if len(snapshots) >= 2 and snapshots[-1].get("code") != snapshots[-2].get("code"):
        events.append(EditorEvent(ts=now - 15, action="insert", chars=code[-120:]))
    for index, run in enumerate(runs[-5:]):
        events.append(EditorEvent(ts=now - 10 + index, action="run"))
    if code.strip():
        events.append(EditorEvent(ts=now - 5, action="insert", chars=code[-80:]))
    if not events and code.strip():
        events.append(EditorEvent(ts=now, action="insert", chars=code[:80]))
    return events
