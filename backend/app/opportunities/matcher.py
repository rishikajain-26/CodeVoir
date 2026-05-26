"""
Scores and ranks opportunities against a candidate's profile.

Priority layers (highest to lowest):
  1. Hard eligibility filters  — year in eligible_years, CGPA >= min_cgpa
  2. Platform company boost    — +35 pts if is_platform_company flag set in DB
  3. Target company boost      — +25 pts if user's target_companies matches org
  4. Skill match score         — 0-50 pts
  5. Interest score            — 0-25 pts
  6. Deadline urgency          — 0-15 pts
  7. Opportunity type pref     — 0-20 pts
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from .database import SessionLocal
from .models import Opportunity

logger = logging.getLogger(__name__)


# ── Name normalizer (shared with platform_companies module) ───────────────────

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _skill_score(
    user_skills: set[str], opp_skills: list[str], opp_tags: list[str]
) -> tuple[float, list[str]]:
    """0–50 pts; returns (score, matched_skill_names)."""
    all_kw = {s.lower() for s in opp_skills + opp_tags}
    if not all_kw:
        return 20.0, []   # no requirement → give baseline so it still appears
    matched = user_skills & all_kw
    ratio = len(matched) / min(len(all_kw), 6)
    return min(ratio * 50, 50), sorted(matched)[:5]


def _interest_score(
    user_interests: set[str], opp_tags: list[str], title: str, desc: str
) -> float:
    """0–25 pts."""
    if not user_interests:
        return 0.0
    haystack = (
        " ".join(opp_tags).lower()
        + " " + title.lower()
        + " " + (desc or "").lower()
    )
    hits = sum(1 for interest in user_interests if interest in haystack)
    return min(hits * 12, 25)


def _deadline_score(deadline_str: str) -> tuple[float, str]:
    """0–15 pts; label like '12d left' or 'Expired'."""
    if not deadline_str or deadline_str.strip() in ("", "None", "null"):
        return 5.0, ""
    try:
        dl_str = deadline_str.strip().replace(" ", "T")
        if dl_str.endswith("Z"):
            dl_str = dl_str[:-1] + "+00:00"
        dl = datetime.fromisoformat(dl_str)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        days = (dl - datetime.now(timezone.utc)).days
        if days < 0:
            return 0.0, "Expired"
        if days == 0:
            return 15.0, "Ends today"
        if days <= 7:
            return 12.0, f"{days}d left"
        if days <= 30:
            return 8.0, f"{days}d left"
        return 4.0, f"{days}d left"
    except Exception:
        return 5.0, ""


def _type_pref_score(opp_type: str, preferred_types: list[str]) -> float:
    """0–20 pts."""
    if not preferred_types:
        return 10.0
    return 20.0 if opp_type in preferred_types else 5.0


# ── Per-opportunity scoring ───────────────────────────────────────────────────

def _score_opp(
    opp: Opportunity,
    user_skills: set[str],
    user_interests: set[str],
    user_year: Optional[int],
    user_cgpa: Optional[float],
    preferred_types: list[str],
    target_norms: list[str],
) -> tuple[float, dict]:
    """Return (total_score, metadata).  score < 0 means hard-filtered out."""

    # ── 1. Hard eligibility filters ──
    eligible_years = opp.years_list()
    if user_year and eligible_years:
        if user_year not in eligible_years:
            return -1.0, {}

    min_cgpa = opp.min_cgpa or 0.0
    if min_cgpa > 0 and user_cgpa is not None:
        if user_cgpa < min_cgpa:
            return -1.0, {}

    # ── 2. Soft scores ──
    s_skill, matched_skills = _skill_score(
        user_skills, opp.skills_list(), opp.tags_list()
    )
    s_interest = _interest_score(
        user_interests, opp.tags_list(), opp.title, opp.description or ""
    )
    s_deadline, deadline_label = _deadline_score(opp.deadline or "")
    s_type = _type_pref_score(opp.type, preferred_types)

    total = s_skill + s_interest + s_deadline + s_type

    # ── 3. Platform company boost (pre-computed in DB at crawl time) ──
    # Opportunities from companies with Codevoir interview data are surfaced first
    # so candidates can directly prep for those companies on the platform.
    is_platform = bool(opp.is_platform_company)
    if is_platform:
        total += 35

    # ── 4. User-specified target company boost ──
    tc_match = False
    org_norm = _norm(opp.organization or "")
    for tn in target_norms:
        if tn and (tn in org_norm or org_norm in tn):
            total += 25
            tc_match = True
            break

    return total, {
        "skill_score": s_skill,
        "matched_skills": matched_skills,
        "deadline_label": deadline_label,
        "platform_company": is_platform,
        "target_company_match": tc_match,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def get_matched_opportunities(
    profile: dict[str, Any],
    preferred_types: list[str],
    extra_skills: list[str],
    target_companies: list[str],
    limit: int = 60,
) -> list[dict]:
    all_skills = list({*(profile.get("skills") or []), *extra_skills})
    user_skills = {s.lower() for s in all_skills}
    user_interests = {i.lower() for i in (profile.get("interests") or [])}
    user_year: Optional[int] = profile.get("college_year")
    user_cgpa: Optional[float] = profile.get("cgpa")

    # Pre-normalize target company names once
    target_norms = [_norm(c) for c in target_companies if c]

    db = SessionLocal()
    try:
        query = db.query(Opportunity).filter(Opportunity.is_active == True)   # noqa: E712
        if preferred_types:
            query = query.filter(Opportunity.type.in_(preferred_types))
        # Fetch platform-company records first from DB to aid early sorting
        query = query.order_by(
            Opportunity.is_platform_company.desc(),
            Opportunity.crawled_at.desc(),
        )
        all_opps = query.all()
    finally:
        db.close()

    if not all_opps:
        return []

    scored: list[tuple[float, dict, dict]] = []
    for opp in all_opps:
        sc, meta = _score_opp(
            opp, user_skills, user_interests,
            user_year, user_cgpa, preferred_types, target_norms,
        )
        if sc < 0:
            continue
        scored.append((sc, meta, opp.to_dict()))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[dict] = []
    for sc, meta, opp_dict in scored[:limit]:
        opp_dict["match_score"] = round(sc, 1)
        opp_dict["matched_skills"] = meta.get("matched_skills", [])
        opp_dict["deadline_label"] = meta.get("deadline_label", "")
        opp_dict["platform_company"] = meta.get("platform_company", False)
        opp_dict["target_company_match"] = meta.get("target_company_match", False)
        results.append(opp_dict)

    return results
