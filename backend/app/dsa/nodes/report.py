from __future__ import annotations

import json

from app.dsa.llm_text import generate_text
from app.dsa.schemas_llm import RecommendationLLM, SkillFeedbackLLM, StrengthsLLM
from app.dsa.state import DSAState, FinalReport, SkillFeedback, SkillFeedbackItem, StrengthWeakness
from app.services.llm.factory import get_llm_provider
from app.utils.logger import logger

provider = get_llm_provider()

_SYS_TRANSCRIPT = """Analyse the full interview transcript (all turns). Return a 3-paragraph
plain text summary covering: (1) communication style, (2) reasoning clarity, (3) pressure handling."""

_SYS_STRENGTHS = """You are a senior hiring manager. From structured scores and notes,
generate 3-5 specific strengths and 3-5 weaknesses. Be specific about code behaviour."""

_SYS_RECOMMENDATION = """You are a principal engineer making a hiring decision.
Return recommendation (strong_hire|hire|lean_hire|lean_reject|reject|insufficient_data) and rationale."""

_SYS_SKILL_FEEDBACK = """You are a senior engineering interviewer writing structured per-skill feedback.
Return JSON only, no markdown. Each skill has: score (0.0–1.0), strengths (list), weaknesses (list), recommendations (list).
Skill weights for context only (do not compute weighted_score yourself):
  communication: 25%  — clarity of explanation, asking good questions, signalling
  technical: 30%      — DSA knowledge, complexity analysis, correctness
  problem_solving: 25% — approach strategy, brute→optimal progression, edge cases
  code_quality: 20%  — naming, structure, readability, modularity

{
  "communication": {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
  "technical":     {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
  "problem_solving":{"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
  "code_quality":  {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []}
}
"""


async def skill_feedback_writer(state: DSAState) -> dict:
    scores = state.session_scores
    context = json.dumps({
        "scores": scores.model_dump(),
        "weak_areas": state.memory.known_weak_areas,
        "strong_areas": state.memory.known_strong_areas,
        "hints_used": f"{state.memory.hints_given}/{state.config.max_hints}",
        "approach_patterns": state.memory.approach_patterns,
        "transcript_analysis": state.scratch.get("_transcript_analysis", ""),
        "phases_observed": list({r.followup_asked[:40] for r in state.memory.turns[-6:] if r.followup_asked}),
    }, ensure_ascii=False)
    try:
        sf_llm = await provider.generate_structured_output(
            system_prompt=_SYS_SKILL_FEEDBACK,
            user_prompt=context,
            response_schema=SkillFeedbackLLM,
        )
        skill_feedback = SkillFeedback(
            communication=SkillFeedbackItem(**sf_llm.communication.model_dump()),
            technical=SkillFeedbackItem(**sf_llm.technical.model_dump()),
            problem_solving=SkillFeedbackItem(**sf_llm.problem_solving.model_dump()),
            code_quality=SkillFeedbackItem(**sf_llm.code_quality.model_dump()),
        )
    except Exception as exc:
        logger.warning("Skill feedback LLM failed, using score-derived fallback: %s", exc)
        skill_feedback = SkillFeedback(
            communication=SkillFeedbackItem(
                score=scores.communication,
                strengths=state.memory.known_strong_areas[:2],
                weaknesses=state.memory.known_weak_areas[:2],
                recommendations=["Practice thinking aloud throughout the solution."],
            ),
            technical=SkillFeedbackItem(
                score=scores.dsa_knowledge,
                strengths=[],
                weaknesses=state.memory.known_weak_areas[:2],
                recommendations=["Review time/space complexity for common patterns."],
            ),
            problem_solving=SkillFeedbackItem(
                score=scores.problem_solving,
                strengths=state.memory.known_strong_areas[:2],
                weaknesses=[],
                recommendations=["Explicitly name your brute force before optimising."],
            ),
            code_quality=SkillFeedbackItem(
                score=scores.coding,
                strengths=[],
                weaknesses=[],
                recommendations=["Use descriptive variable names and handle edge cases first."],
            ),
        )
    scratch = dict(state.scratch)
    scratch["_skill_feedback"] = skill_feedback.model_dump()
    return {"scratch": scratch}


async def transcript_analyser(state: DSAState) -> dict:
    lines = []
    for record in state.memory.turns:
        lines.append(
            f"Turn {record.turn}:\n"
            f" Code: {record.code_excerpt[:300]}\n"
            f" Explanation: {record.explanation_excerpt}\n"
            f" Followup: {record.followup_asked}\n"
            f" Score: {record.score.weighted_total:.2f}"
        )
    transcript = "\n\n".join(lines) or state.candidate_explanation
    analysis = await generate_text(_SYS_TRANSCRIPT, transcript, temperature=0.3, max_tokens=400)
    scratch = dict(state.scratch)
    scratch["_transcript_analysis"] = analysis.strip()
    return {"scratch": scratch}


def radar_chart_builder(state: DSAState) -> dict:
    scores = state.session_scores
    radar = {
        "Problem Solving": round(scores.problem_solving * 10, 1),
        "Coding": round(scores.coding * 10, 1),
        "Communication": round(scores.communication * 10, 1),
        "Debugging": round(scores.debugging * 10, 1),
        "DSA Knowledge": round(scores.dsa_knowledge * 10, 1),
        "Behavioural": round(state.behaviour_profile.overall_confidence * 10, 1),
    }
    scratch = dict(state.scratch)
    scratch["_radar_data"] = radar
    return {"scratch": scratch}


async def final_report_writer(state: DSAState) -> dict:
    plagiarism = float(state.scratch.get("_plagiarism_likelihood", 0.0))
    try:
        sw = await provider.generate_structured_output(
            system_prompt=_SYS_STRENGTHS,
            user_prompt=(
                f"Scores: {state.session_scores.model_dump()}\n"
                f"Weak areas: {state.memory.known_weak_areas}\n"
                f"Strong areas: {state.memory.known_strong_areas}\n"
                f"Patterns: {state.memory.approach_patterns}\n"
                f"Flags: {state.behaviour_profile.nervousness_flags}\n"
                f"Plagiarism: {plagiarism}"
            ),
            response_schema=StrengthsLLM,
        )
    except Exception as exc:
        logger.warning("DSA strengths report failed: %s", exc)
        sw = StrengthsLLM(
            strengths=state.memory.known_strong_areas or ["Showed persistence"],
            weaknesses=state.memory.known_weak_areas or ["Needs sharper complexity reasoning"],
        )

    try:
        rec = await provider.generate_structured_output(
            system_prompt=_SYS_RECOMMENDATION,
            user_prompt=(
                f"Scores: {state.session_scores.model_dump()}\n"
                f"Strengths: {sw.strengths}\n"
                f"Weaknesses: {sw.weaknesses}\n"
                f"Hints: {state.memory.hints_given}/{state.config.max_hints}\n"
                f"Confidence trend: {state.memory.confidence_trend[-5:]}\n"
                f"Plagiarism: {plagiarism}"
            ),
            response_schema=RecommendationLLM,
        )
    except Exception as exc:
        logger.warning("DSA recommendation failed: %s", exc)
        rec = RecommendationLLM(
            recommendation=_score_to_recommendation(state.session_scores.overall),
            rationale="Based on aggregated turn scores and interview behaviour.",
        )

    raw_sf = state.scratch.get("_skill_feedback", {})
    skill_feedback = SkillFeedback(**raw_sf) if raw_sf else SkillFeedback()

    report = FinalReport(
        session_id=state.config.session_id,
        candidate_id=state.config.candidate_id,
        scores=state.session_scores,
        strengths_weaknesses=StrengthWeakness(strengths=sw.strengths, weaknesses=sw.weaknesses),
        timeline=state.timeline,
        behaviour_summary=(
            f"Confidence trend: {state.memory.confidence_trend[-5:]}; "
            f"Flags: {state.behaviour_profile.nervousness_flags[:6]}"
        ),
        communication_transcript_analysis=state.scratch.get("_transcript_analysis", ""),
        plagiarism_likelihood=plagiarism,
        recommendation=rec.recommendation,
        recommendation_rationale=rec.rationale,
        radar_data=state.scratch.get("_radar_data", {}),
        skill_feedback=skill_feedback,
    )
    return {"report": report}


def hiring_recommender(state: DSAState) -> dict:
    report = state.report
    if float(state.scratch.get("_plagiarism_likelihood", 0.0)) > 0.85:
        return {
            "report": report.model_copy(
                update={
                    "recommendation": "reject",
                    "recommendation_rationale": (
                        "High plagiarism likelihood detected during the interview."
                    ),
                }
            ),
            "next_action": "end_interview",
        }
    return {"report": report, "next_action": "end_interview"}


async def report_bundle(state: DSAState) -> dict:
    merged: dict = {}
    merged.update(await transcript_analyser(state))
    state_after = state.model_copy(update=merged)
    merged.update(radar_chart_builder(state_after))
    state_after = state.model_copy(update=merged)
    # skill_feedback_writer reads _transcript_analysis from scratch so must run after transcript_analyser
    merged.update(await skill_feedback_writer(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(await final_report_writer(state_after))
    state_after = state.model_copy(update=merged)
    merged.update(hiring_recommender(state_after))
    return merged


def _score_to_recommendation(overall: float) -> str:
    if overall >= 0.85:
        return "strong_hire"
    if overall >= 0.72:
        return "hire"
    if overall >= 0.58:
        return "lean_hire"
    if overall >= 0.42:
        return "lean_reject"
    if overall > 0:
        return "reject"
    return "insufficient_data"
