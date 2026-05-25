from __future__ import annotations

"""Dataset-driven interviewer personality service.

Derives interviewer behaviour parameters from the company dataset so
the AI does NOT use hardcoded styles. Parameters are injected into
DSAState.personality and read by output.py to shape prompts.
"""

from typing import Any

from app.services.interview_data_service import InterviewDataService

_data_service = InterviewDataService()

# Company-tier defaults (applied when a company has no explicit personality config)
_TIER_DEFAULTS: dict[str, dict[str, Any]] = {
    "tier_1": {
        "pressure_baseline": 0.65,
        "followup_depth": "deep",        # shallow | medium | deep
        "dry_run_frequency": "high",     # low | medium | high
        "challenge_style": "adversarial",# supportive | neutral | adversarial
        "hint_willingness": 0.2,         # 0 = never hints, 1 = always hints
        "interruption_frequency": 0.3,   # probability of cutting in mid-explanation
        "focus_areas": ["optimality", "edge_cases", "code_quality"],
        "tone": "sharp",                 # warm | neutral | sharp
        "preamble": (
            "I'm going to push back on weak reasoning and expect you to "
            "defend your choices with evidence."
        ),
    },
    "tier_2": {
        "pressure_baseline": 0.45,
        "followup_depth": "medium",
        "dry_run_frequency": "medium",
        "challenge_style": "neutral",
        "hint_willingness": 0.35,
        "interruption_frequency": 0.15,
        "focus_areas": ["correctness", "complexity", "communication"],
        "tone": "neutral",
        "preamble": "Walk me through your reasoning clearly and we'll explore the solution together.",
    },
    "default": {
        "pressure_baseline": 0.35,
        "followup_depth": "medium",
        "dry_run_frequency": "low",
        "challenge_style": "supportive",
        "hint_willingness": 0.5,
        "interruption_frequency": 0.05,
        "focus_areas": ["correctness", "communication"],
        "tone": "warm",
        "preamble": "Take your time. Think aloud and I'll guide you.",
    },
}

# Per-company overrides — populated from known dataset signals.
# The service merges these on top of tier defaults so dataset drives behaviour.
_COMPANY_OVERRIDES: dict[str, dict[str, Any]] = {
    "google": {
        "challenge_style": "adversarial",
        "dry_run_frequency": "high",
        "focus_areas": ["optimality", "edge_cases", "scalability", "code_quality"],
        "tone": "sharp",
        "preamble": (
            "I want you to think about the most efficient approach. "
            "Walk me through your logic step by step, and I'll probe every assumption."
        ),
    },
    "meta": {
        "challenge_style": "adversarial",
        "focus_areas": ["optimality", "code_quality", "scalability"],
        "preamble": "Let's look at how your solution scales. I'll challenge each design decision.",
    },
    "amazon": {
        "followup_depth": "deep",
        "focus_areas": ["correctness", "edge_cases", "leadership_principles", "communication"],
        "preamble": "Tell me your approach and be specific about trade-offs and failure modes.",
    },
    "microsoft": {
        "challenge_style": "neutral",
        "hint_willingness": 0.4,
        "focus_areas": ["correctness", "communication", "code_quality"],
        "preamble": "Let's work through the problem together. Explain your thought process clearly.",
    },
    "apple": {
        "dry_run_frequency": "high",
        "focus_areas": ["optimality", "code_quality", "edge_cases"],
        "preamble": "I care about clean, correct code. Run me through your solution carefully.",
    },
    "netflix": {
        "challenge_style": "adversarial",
        "focus_areas": ["scalability", "optimality", "code_quality"],
        "preamble": "We operate at extreme scale. I need to see that you think about edge cases at scale.",
    },
    "startup": {
        "pressure_baseline": 0.4,
        "hint_willingness": 0.5,
        "focus_areas": ["correctness", "communication", "pragmatism"],
        "preamble": "Think out loud; I want to understand how you reason, not just if you know the answer.",
    },
}


def get_interviewer_personality(
    company_name: str | None,
    round_type: str = "dsa",
    current_pressure: float = 0.3,
) -> dict[str, Any]:
    """Return an interviewer personality dict for the given company.

    Merges tier defaults → company overrides → live pressure adjustment.
    Result is stored in DSAState.personality.
    """
    profile = _data_service.get_company_profile(company_name)
    tier: str = profile.get("tier", "default")

    # Map tier names to our tier key
    tier_key = "default"
    if "1" in str(tier) or tier in {"tier_1", "top", "faang", "big_tech"}:
        tier_key = "tier_1"
    elif "2" in str(tier) or tier in {"tier_2", "mid", "unicorn"}:
        tier_key = "tier_2"

    base = dict(_TIER_DEFAULTS[tier_key])

    # Apply per-company overrides
    resolved_company = _data_service.resolve_company(company_name) or ""
    for key, overrides in _COMPANY_OVERRIDES.items():
        if key in resolved_company.lower():
            base.update(overrides)
            break

    # Adjust pressure from company's DSA config if present
    dsa_cfg = profile.get("rounds", {}).get("dsa", {})
    if dsa_cfg.get("pressure_high"):
        base["pressure_baseline"] = max(base.get("pressure_baseline", 0.35) + 0.15, 0.7)

    # Blend live pressure into the hint_willingness threshold
    live_pressure = max(0.0, min(1.0, current_pressure))
    base["effective_pressure"] = live_pressure
    # Higher live pressure → less willing to hint
    base["hint_willingness"] = round(
        base.get("hint_willingness", 0.35) * (1.0 - live_pressure * 0.5), 3
    )

    base["company"] = resolved_company or company_name or "unknown"
    base["tier"] = tier_key
    return base


def personality_to_prompt_fragment(personality: dict[str, Any]) -> str:
    """Convert a personality dict into a short system-prompt fragment injected into output.py."""
    tone = personality.get("tone", "neutral")
    challenge = personality.get("challenge_style", "neutral")
    depth = personality.get("followup_depth", "medium")
    dry_run = personality.get("dry_run_frequency", "medium")
    preamble = personality.get("preamble", "")
    focus = ", ".join(personality.get("focus_areas", []))
    pressure = personality.get("effective_pressure", 0.3)
    company = personality.get("company", "")

    pressure_label = "high" if pressure >= 0.7 else "medium" if pressure >= 0.4 else "low"

    lines = [
        f"Interviewer style for {company}: tone={tone}, challenge={challenge}, pressure={pressure_label}.",
        f"Follow-up depth: {depth}. Dry-run requests: {dry_run}.",
        f"Focus areas: {focus}.",
    ]
    if preamble:
        lines.append(f'Style note: "{preamble}"')
    if challenge == "adversarial":
        lines.append("Push back firmly when the candidate is vague or claims incorrect complexity.")
    if dry_run == "high":
        lines.append(
            "When candidate has code, ask them to manually trace through a small example before running it."
        )
    if pressure_label == "high":
        lines.append(
            "Ask follow-ups immediately; do not wait for the candidate to volunteer information."
        )

    return " ".join(lines)
