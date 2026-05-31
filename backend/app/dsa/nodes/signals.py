from __future__ import annotations

from app.dsa.state import CandidateBehaviourProfile, DSAState


def speech_signal_extractor(state: DSAState) -> dict:
    speech = state.speech_signals
    flags: list[str] = []
    panic: list[str] = []
    curiosity: list[str] = []

    if speech.wpm < 80:
        flags.append("very_slow_speech")
    elif speech.wpm < 110:
        flags.append("below_average_pace")
    if speech.filler_ratio > 0.15:
        flags.append("high_filler_ratio")
        panic.append("excessive_fillers")
    if speech.hesitation_count > 5:
        flags.append("frequent_mid_sentence_hesitation")
    if speech.tone_label == "nervous":
        flags.append("nervous_tone")
        panic.append("nervous_tone_detected")
    if speech.tone_label == "frustrated":
        flags.append("frustrated_tone")
    if speech.thinks_aloud:
        curiosity.append("thinks_aloud_while_coding")
    if speech.explains_intuition:
        curiosity.append("explains_intuition_unprompted")

    scratch = dict(state.scratch)
    scratch["_speech_flags"] = flags
    scratch["_panic_signals"] = panic
    scratch["_curiosity_signals"] = curiosity
    return {"scratch": scratch}


def editor_event_analyser(state: DSAState) -> dict:
    editor = state.editor_signals
    flags: list[str] = []
    patterns: dict[str, int] = {}
    panic: list[str] = []

    if editor.copy_paste_detected:
        flags.append("copy_paste_detected")
        panic.append("possible_plagiarism")
    if editor.approach_switches >= 2:
        flags.append("multiple_approach_switches")
        patterns["approach_switches"] = editor.approach_switches
    if editor.backspace_frequency > 0.4:
        flags.append("high_backspace_frequency")
        patterns["frequent_backtracking"] = int(editor.backspace_frequency * 100)
    if editor.first_keystroke_latency > 30:
        flags.append("long_pre_coding_pause")
    elif 0 < editor.first_keystroke_latency < 5:
        flags.append("premature_coding_tendency")
        panic.append("jumped_to_code_without_planning")
    if editor.run_count > 8:
        flags.append("many_debug_runs")
        patterns["high_run_count"] = editor.run_count
    if editor.rewrite_count >= 3:
        flags.append("full_rewrites_observed")
        patterns["full_rewrites"] = editor.rewrite_count

    scratch = dict(state.scratch)
    scratch["_editor_flags"] = flags
    scratch["_coding_patterns"] = patterns
    scratch["_panic_signals_editor"] = panic
    return {"scratch": scratch}


def silence_gap_detector(state: DSAState) -> dict:
    silence = state.silence_profile
    flags: list[str] = []
    panic: list[str] = []
    long_gaps = [gap for gap in silence.gaps if gap > 8]

    if silence.longest_gap > 20:
        flags.append(f"very_long_gap_{silence.longest_gap:.0f}s")
        panic.append("candidate_appears_stuck")
    elif silence.longest_gap > 10:
        flags.append(f"long_gap_{silence.longest_gap:.0f}s")
    if len(long_gaps) >= 3:
        flags.append("repeated_long_gaps")
    if silence.total_silence > 120:
        flags.append("high_total_silence_overall")

    scratch = dict(state.scratch)
    scratch["_silence_flags"] = flags
    scratch["_panic_signals_silence"] = panic
    return {"scratch": scratch}


def behaviour_aggregator(state: DSAState) -> dict:
    scratch = state.scratch
    speech_flags = scratch.get("_speech_flags", [])
    editor_flags = scratch.get("_editor_flags", [])
    silence_flags = scratch.get("_silence_flags", [])
    panic = (
        scratch.get("_panic_signals", [])
        + scratch.get("_panic_signals_editor", [])
        + scratch.get("_panic_signals_silence", [])
    )
    curiosity = scratch.get("_curiosity_signals", [])
    patterns = dict(scratch.get("_coding_patterns", {}))
    editor = state.editor_signals
    silence = state.silence_profile
    speech = state.speech_signals

    # Only weight each component when there's actual data behind it.
    # Absence of a negative signal (no fillers, no backspace, no silence gaps)
    # is NOT evidence of good performance — it's absence of data.
    word_count = len(state.candidate_explanation.split())
    has_code = len(state.candidate_code.strip()) > 10

    _conf_components: list[float] = []

    # Silence / confidence proxy: only meaningful when speech is substantive
    if word_count >= 10 or silence.longest_gap > 0:
        _conf_components.append(silence.confidence_proxy)

    # Speech quality: only meaningful when candidate actually spoke
    if word_count >= 10:
        _conf_components.append(1.0 - min(speech.filler_ratio / 0.20, 1.0))

    # Editor quality: only meaningful when candidate actually typed
    if has_code or editor.first_keystroke_latency > 0 or editor.run_count > 0:
        _conf_components.append(1.0 - min(editor.backspace_frequency / 0.60, 1.0))

    confidence = (
        sum(_conf_components) / len(_conf_components)
        if _conf_components
        else 0.0  # no engagement → no confidence signal
    )
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    persistence = 1.0
    if editor.approach_switches >= 3:
        persistence -= 0.3
    if editor.rewrite_count >= 3:
        persistence += 0.1
    persistence = round(max(0.0, min(1.0, persistence)), 3)

    hints_given = state.memory.hints_given
    hint_dep = round(min(hints_given / max(state.config.max_hints, 1), 1.0), 3)
    recovery = round(max(0.0, 1.0 - (0.1 * min(editor.approach_switches, 5))), 3)

    profile = CandidateBehaviourProfile(
        turn=state.progress.current_question_index,
        speech=speech,
        silence=silence,
        editor=editor,
        overall_confidence=confidence,
        nervousness_flags=speech_flags + editor_flags + silence_flags,
        persistence_score=persistence,
        panic_indicators=panic,
        recovery_quality=recovery,
        hint_dependency_score=hint_dep,
        curiosity_signals=curiosity,
    )
    scratch["_coding_patterns"] = patterns
    return {"behaviour_profile": profile, "scratch": scratch}
