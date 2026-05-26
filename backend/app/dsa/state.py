from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

DSA_PATTERNS = Literal[
    "dp",
    "graph",
    "bfs",
    "dfs",
    "sliding_window",
    "two_pointer",
    "binary_search",
    "greedy",
    "backtracking",
    "trie",
    "heap",
    "union_find",
    "segment_tree",
    "monotonic_stack",
    "hashing",
    "none",
]


class AudioMeta(BaseModel):
    wpm: float = 0.0
    filler_count: int = 0
    hesitation_count: int = 0
    tone_label: Literal["confident", "nervous", "neutral", "frustrated"] = "neutral"
    avg_sentence_len: float = 0.0
    silence_gaps: list[float] = Field(default_factory=list)
    start_ts: float = Field(default_factory=time.time)


class EditorEvent(BaseModel):
    ts: float
    action: Literal[
        "insert",
        "delete",
        "replace_block",
        "approach_switch",
        "copy_paste",
        "run",
        "submit",
    ]
    chars: str = ""
    line: int = 0


class SessionConfig(BaseModel):
    session_id: str = ""
    candidate_id: str = ""
    target_company: str = ""
    problem_id: str = ""
    problem_statement: str = ""
    expected_solution: str = ""
    expected_time_complexity: str = ""
    expected_space_complexity: str = ""
    max_turns: int = 10
    max_hints: int = 3
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    allowed_patterns: list[str] = Field(default_factory=list)
    total_questions: int = 2
    allocated_minutes: int = 45
    per_question_minutes: float = 22.5


class CandidateIntent(BaseModel):
    """Resolved from the candidate's latest message plus live session context."""

    primary_intent: Literal[
        "continue",
        "request_hint",
        "clarify_problem",
        "discuss_approach",
        "discuss_complexity",
        "review_submission",
        "advance_question",
        "end_interview",
        "express_stuck",
    ] = "continue"
    should_give_hint: bool = False
    should_advance_question: bool = False
    should_end_round: bool = False
    should_clarify_problem: bool = False
    interviewer_focus: str = ""
    reasoning: str = ""
    raw_intent: Literal[
        "explaining_approach",
        "asking_clarification",
        "asking_hint",
        "submitting_code",
        "answering_followup",
        "meta_complaint",
        "change_topic",
        "idle",
    ] = "idle"
    should_change_topic: bool = False
    summary: str = ""
    approach_correct: bool | None = None
    question_asked: str | None = None
    frustration_level: int = 0


class InterviewProgress(BaseModel):
    current_question_index: int = 1
    total_questions: int = 2
    company_minutes: int = 45
    allocated_minutes: int = 45
    per_question_minutes: float = 22.5
    started_at_epoch: float = Field(default_factory=time.time)
    elapsed_seconds: int = 0
    remaining_seconds: int = 0
    time_expired: bool = False
    completed_questions: list[int] = Field(default_factory=list)
    round_complete: bool = False
    label: str = "Question 1 of 2"


class SpeechSignals(BaseModel):
    wpm: float = 0.0
    filler_ratio: float = 0.0
    hesitation_count: int = 0
    tone_label: str = "neutral"
    avg_sentence_len: float = 0.0
    thinks_aloud: bool = False
    explains_intuition: bool = False


class SilenceProfile(BaseModel):
    gaps: list[float] = Field(default_factory=list)
    longest_gap: float = 0.0
    total_silence: float = 0.0
    gap_before_brute_force: float = 0.0
    gap_before_optimisation: float = 0.0
    confidence_proxy: float = 1.0


class EditorSignals(BaseModel):
    edits_per_minute: float = 0.0
    backspace_frequency: float = 0.0
    rewrite_count: int = 0
    approach_switches: int = 0
    first_keystroke_latency: float = 0.0
    copy_paste_detected: bool = False
    run_count: int = 0
    submit_count: int = 0
    time_planning_s: float = 0.0
    time_coding_s: float = 0.0
    time_debugging_s: float = 0.0


class CandidateBehaviourProfile(BaseModel):
    turn: int = 0
    speech: SpeechSignals = Field(default_factory=SpeechSignals)
    silence: SilenceProfile = Field(default_factory=SilenceProfile)
    editor: EditorSignals = Field(default_factory=EditorSignals)
    overall_confidence: float = 1.0
    nervousness_flags: list[str] = Field(default_factory=list)
    persistence_score: float = 1.0
    panic_indicators: list[str] = Field(default_factory=list)
    recovery_quality: float = 1.0
    hint_dependency_score: float = 0.0
    curiosity_signals: list[str] = Field(default_factory=list)


class UnderstandingProfile(BaseModel):
    time_to_first_clarification_s: float = 0.0
    clarifying_questions_asked: list[str] = Field(default_factory=list)
    constraint_interpretation_correct: bool = True
    edge_cases_identified_early: list[str] = Field(default_factory=list)
    misunderstood_constraints: list[str] = Field(default_factory=list)
    understanding_score: float = 0.0
    # How well the latest reply answers the follow-up question that was asked,
    # judged against the problem. 0 when no follow-up was pending.
    answer_relevance: float = 0.0


class ApproachProfile(BaseModel):
    brute_force_identified: bool = False
    brute_force_time_complexity: str = ""
    optimised_identified: bool = False
    approaches_attempted: int = 0
    final_approach_optimal: bool = False
    data_structure_used: list[str] = Field(default_factory=list)
    pattern_recognised: list[str] = Field(default_factory=list)
    pattern_recognition_score: float = 0.0
    approach_quality_score: float = 0.0


class ComplexityProfile(BaseModel):
    stated_time: str = ""
    stated_space: str = ""
    actual_time: str = ""
    actual_space: str = ""
    time_correct: bool = False
    space_correct: bool = False
    optimisation_awareness: bool = False
    tradeoff_discussion_quality: float = 0.0
    complexity_accuracy_score: float = 0.0


class ImplementationQuality(BaseModel):
    compilation_success: bool = False
    syntax_error_count: int = 0
    runtime_error_count: int = 0
    logical_bug_count: int = 0
    code_complete: bool = False
    modular_score: float = 0.0
    naming_quality: float = 0.0
    readability_score: float = 0.0
    comment_quality: float = 0.0
    dead_code_present: bool = False
    redundant_loops: bool = False
    repeated_logic: bool = False
    boundary_checks_handled: bool = False
    null_empty_checks: bool = False
    overflow_handling: bool = False


class TestingProfile(BaseModel):
    test_cases_written: int = 0
    edge_case_coverage: float = 0.0
    adversarial_tests: int = 0
    hidden_test_pass_pct: float = 0.0
    visible_test_pass_pct: float = 0.0


class DebugProfile(BaseModel):
    time_to_first_success_s: float = 0.0
    debug_iterations: int = 0
    bug_localisation_quality: float = 0.0
    debug_strategy: Literal["print_debug", "systematic", "random", "none"] = "none"
    fixes_root_cause: bool = True
    uses_logging_well: bool = False


class TimelineEvent(BaseModel):
    phase: Literal[
        "problem_reading",
        "clarification",
        "brute_force",
        "optimisation",
        "implementation",
        "debugging",
        "done",
    ]
    start_ts: float
    end_ts: float
    duration_s: float
    notes: str = ""


class InterviewTimeline(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)
    current_phase: str = "problem_reading"
    phase_start_ts: float = Field(default_factory=time.time)


class TurnScore(BaseModel):
    understanding: float = 0.0
    approach_quality: float = 0.0
    complexity_accuracy: float = 0.0
    implementation: float = 0.0
    debugging: float = 0.0
    communication: float = 0.0
    behavioural: float = 0.0
    answer_relevance: float = 0.0  # quality of reply vs the follow-up asked (0 if none)
    weighted_total: float = 0.0
    missed_edge_cases: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    approach_delta_notes: str = ""


class SessionScores(BaseModel):
    problem_solving: float = 0.0
    coding: float = 0.0
    communication: float = 0.0
    debugging: float = 0.0
    dsa_knowledge: float = 0.0
    followup_handling: float = 0.0  # avg answer_relevance over turns that answered a follow-up
    overall: float = 0.0
    confidence_trend: list[float] = Field(default_factory=list)
    per_turn: list[float] = Field(default_factory=list)


class TurnRecord(BaseModel):
    turn: int
    problem_excerpt: str
    code_excerpt: str
    explanation_excerpt: str
    score: TurnScore
    behaviour: CandidateBehaviourProfile
    followup_asked: str = ""
    hint_given: str | None = None
    timeline_snapshot: list[TimelineEvent] = Field(default_factory=list)


class ContradictionRecord(BaseModel):
    turn: int
    claim_before: str
    claim_now: str
    severity: float = 0.0
    topic: str = ""


class SessionMemory(BaseModel):
    turns: list[TurnRecord] = Field(default_factory=list)
    behaviour_history: list[CandidateBehaviourProfile] = Field(default_factory=list)
    confidence_trend: list[float] = Field(default_factory=list)
    known_weak_areas: list[str] = Field(default_factory=list)
    known_strong_areas: list[str] = Field(default_factory=list)
    approach_patterns: dict[str, int] = Field(default_factory=dict)
    hints_given: int = 0
    hint_log: list[str] = Field(default_factory=list)
    total_silence_s: float = 0.0
    total_coding_s: float = 0.0
    contradiction_history: list[ContradictionRecord] = Field(default_factory=list)
    rolling_summary: str = ""
    recent_probe_categories: list[str] = Field(default_factory=list)
    asked_aspects: list[str] = Field(default_factory=list)


class StrengthWeakness(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class SkillFeedbackItem(BaseModel):
    score: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SkillFeedback(BaseModel):
    """Weighted per-skill breakdown (Comm 25%, Tech 30%, Problem-Solving 25%, Code Quality 20%)."""

    communication: SkillFeedbackItem = Field(default_factory=SkillFeedbackItem)
    technical: SkillFeedbackItem = Field(default_factory=SkillFeedbackItem)
    problem_solving: SkillFeedbackItem = Field(default_factory=SkillFeedbackItem)
    code_quality: SkillFeedbackItem = Field(default_factory=SkillFeedbackItem)

    @property
    def weighted_score(self) -> float:
        return (
            self.communication.score * 0.25
            + self.technical.score * 0.30
            + self.problem_solving.score * 0.25
            + self.code_quality.score * 0.20
        )


class FinalReport(BaseModel):
    session_id: str = ""
    candidate_id: str = ""
    scores: SessionScores = Field(default_factory=SessionScores)
    strengths_weaknesses: StrengthWeakness = Field(default_factory=StrengthWeakness)
    timeline: InterviewTimeline = Field(default_factory=InterviewTimeline)
    behaviour_summary: str = ""
    communication_transcript_analysis: str = ""
    plagiarism_likelihood: float = 0.0
    recommendation: Literal[
        "strong_hire",
        "hire",
        "lean_hire",
        "lean_reject",
        "reject",
        "insufficient_data",
    ] = "insufficient_data"
    recommendation_rationale: str = ""
    radar_data: dict[str, float] = Field(default_factory=dict)
    skill_feedback: SkillFeedback = Field(default_factory=SkillFeedback)


class DSAState(BaseModel):
    config: SessionConfig = Field(default_factory=SessionConfig)
    progress: InterviewProgress = Field(default_factory=InterviewProgress)
    candidate_intent: CandidateIntent = Field(default_factory=CandidateIntent)
    exchange_number: int = 0
    turn_number: int = 0
    trigger: Literal["message", "code_submit", "timer"] = "message"
    candidate_code: str = ""
    code_language: str = "python"
    candidate_explanation: str = ""
    latest_code_run: dict[str, Any] = Field(default_factory=dict)
    audio_meta: AudioMeta = Field(default_factory=AudioMeta)
    editor_events: list[EditorEvent] = Field(default_factory=list)
    editor_context: str = ""

    speech_signals: SpeechSignals = Field(default_factory=SpeechSignals)
    silence_profile: SilenceProfile = Field(default_factory=SilenceProfile)
    editor_signals: EditorSignals = Field(default_factory=EditorSignals)
    behaviour_profile: CandidateBehaviourProfile = Field(default_factory=CandidateBehaviourProfile)

    understanding: UnderstandingProfile = Field(default_factory=UnderstandingProfile)
    approach: ApproachProfile = Field(default_factory=ApproachProfile)
    complexity: ComplexityProfile = Field(default_factory=ComplexityProfile)
    implementation: ImplementationQuality = Field(default_factory=ImplementationQuality)
    testing: TestingProfile = Field(default_factory=TestingProfile)
    debug_profile: DebugProfile = Field(default_factory=DebugProfile)
    timeline: InterviewTimeline = Field(default_factory=InterviewTimeline)
    turn_score: TurnScore = Field(default_factory=TurnScore)

    memory: SessionMemory = Field(default_factory=SessionMemory)
    scratch: dict[str, Any] = Field(default_factory=dict)

    followup_question: str = ""
    hint: str | None = None
    hint_tightness: Literal["tight", "medium", "broad"] = "tight"
    interviewer_reply: str = ""
    session_scores: SessionScores = Field(default_factory=SessionScores)
    report: FinalReport = Field(default_factory=FinalReport)

    next_action: Literal["next_turn", "escalate_hint", "direct_reply", "generate_report", "end_interview"] = "next_turn"
    error: str | None = None

    # Adaptive difficulty and pressure
    pressure_level: float = 0.3  # 0.0 = relaxed, 1.0 = high pressure
    difficulty_level: Literal["easy", "medium", "hard"] = "medium"

    # Contradiction tracking
    latest_contradiction: ContradictionRecord | None = None

    # Interviewer personality (injected from personality_service)
    personality: dict[str, Any] = Field(default_factory=dict)

    # Static code analysis (populated by tree-sitter in ingest, zero LLM cost)
    code_structure: dict[str, Any] = Field(default_factory=dict)

    # Interview phase — drives routing and phase-specific prompts
    interview_phase: Literal[
        "reading", "clarification", "brute_force", "optimization", "coding", "testing", "closing"
    ] = "reading"
    phase_turns: int = 0            # turns spent in the current phase
    brute_force_given: bool = False  # candidate has stated any concrete approach
    optimized_approach_confirmed: bool = False  # approach is at target complexity

    # Legacy-compatible payloads for existing API consumers
    evaluation: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
