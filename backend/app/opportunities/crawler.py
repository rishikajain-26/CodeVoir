"""
Crawls Unstop and Devfolio for live opportunities.
Verified against the real API responses (May 2026).

Unstop endpoint : GET https://unstop.com/api/public/opportunity/search-result
                  param  opportunity = hackathons | jobs | internships | competitions
                  response: data.data.data[]  (paginated, ~10 000 each type)

Devfolio endpoint: GET https://api.devfolio.co/api/hackathons
                   param  status = open | upcoming
                   (times out occasionally — handled gracefully)
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import requests

from .database import SessionLocal
from .models import CrawlLog, Opportunity
from .platform_companies import is_platform_company as _is_platform

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://unstop.com/",
}

_UNSTOP_BASE = "https://unstop.com/api/public/opportunity/search-result"
_DEVFOLIO_BASE = "https://api.devfolio.co/api/hackathons"

# Map Unstop's `type` value → our internal type
_UNSTOP_TYPE_MAP = {
    "hackathons": "hackathon",
    "hackathon": "hackathon",
    "competitions": "competition",
    "competition": "competition",
    "quizzes": "competition",
    "quiz": "competition",
    "jobs": "job",
    "job": "job",
    "internships": "internship",
    "internship": "internship",
    "mentorships": "hackathon",
    "workshops": "hackathon",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _make_id(source: str, raw_id: Any) -> str:
    return f"{source}_{raw_id}"


def _parse_unstop_eligible_years(filters: list) -> list:
    """
    Unstop 'filters' list contains eligibility tags like:
    {'name': 'Undergraduate', 'type': 'eligible', ...}
    {'name': 'Postgraduate', 'type': 'eligible', ...}
    We map these to year lists.
    """
    if not filters:
        return [1, 2, 3, 4]
    elig_names = {
        f["name"].lower()
        for f in filters
        if isinstance(f, dict) and f.get("type") == "eligible"
    }
    if not elig_names:
        return [1, 2, 3, 4]
    years = []
    if any(k in elig_names for k in ("undergraduate", "ug", "student")):
        years.extend([1, 2, 3, 4])
    if any(k in elig_names for k in ("postgraduate", "pg", "mtech", "mba")):
        # graduate students — we treat as year 4 eligible too
        if 4 not in years:
            years.append(4)
    return sorted(set(years)) or [1, 2, 3, 4]


# ── Unstop crawler ────────────────────────────────────────────────────────────

def _crawl_unstop_page(opportunity_type: str, page: int) -> list:
    """opportunity_type must be plural: hackathons | jobs | internships | competitions"""
    params: dict[str, Any] = {
        "opportunity": opportunity_type,
        "per_page": 50,
        "page": page,
    }
    try:
        resp = requests.get(_UNSTOP_BASE, params=params, headers=_HEADERS, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Unstop %s page %d: %s", opportunity_type, page, exc)
        return []

    raw_items: list = []
    try:
        raw_items = data["data"]["data"]
    except (KeyError, TypeError):
        logger.warning("Unstop unexpected shape for %s p%d", opportunity_type, page)
        return []

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            opp_id = item.get("id")
            if not opp_id:
                continue

            # URL: seo_url is always the full canonical URL
            url = item.get("seo_url") or f"https://unstop.com/{item.get('public_url', '')}"

            # Organisation
            org = item.get("organisation") or {}
            org_name = org.get("name", "") if isinstance(org, dict) else ""

            # Cover image: try organisation logo
            cover = org.get("logoUrl2") if isinstance(org, dict) else ""
            if not cover:
                cover = item.get("thumb") or item.get("logoUrl2") or ""

            # Type — use the opportunity_type we queried as the ground truth fallback
            raw_type = item.get("type", opportunity_type)
            opp_type = _UNSTOP_TYPE_MAP.get(raw_type, _UNSTOP_TYPE_MAP.get(opportunity_type, "hackathon"))

            # Deadline
            deadline = item.get("end_date") or ""

            # Prize pool from `prizes` list
            prizes_raw = item.get("prizes") or []
            prize_str = ""
            if prizes_raw and isinstance(prizes_raw, list):
                first_prize = prizes_raw[0] if prizes_raw else {}
                if isinstance(first_prize, dict):
                    amt = first_prize.get("amount") or first_prize.get("title") or ""
                    prize_str = str(amt)[:200]

            # Stipend for jobs/internships
            stipend = ""
            opp_config = item.get("opportunity_config") or {}
            if isinstance(opp_config, dict):
                stipend = str(opp_config.get("stipend") or opp_config.get("salary") or "")

            # Skills from `required_skills`
            skills_raw = item.get("required_skills") or []
            skills = []
            for s in skills_raw:
                if isinstance(s, dict):
                    name = s.get("skill") or s.get("skill_name") or ""
                    if name:
                        skills.append(name)
                elif isinstance(s, str):
                    skills.append(s)

            # Tags from `workfunction`
            wf = item.get("workfunction") or []
            tags = []
            for w in wf:
                if isinstance(w, dict):
                    name = w.get("name") or ""
                    if name:
                        tags.append(name)

            # Eligibility
            eligible_years = _parse_unstop_eligible_years(item.get("filters") or [])

            # Location / remote
            region = (item.get("region") or "").lower()
            is_remote = region in ("online", "remote", "virtual") or "online" in region

            # Team size
            regn = item.get("regnRequirements") or {}
            if isinstance(regn, dict):
                lo_t = regn.get("min_team_size", 1) or 1
                hi_t = regn.get("max_team_size", 1) or 1
                team_size = f"{lo_t}–{hi_t}" if lo_t != hi_t else str(lo_t)
            else:
                team_size = ""

            # Description
            description = _strip_html(item.get("details") or "")[:1200]

            items.append({
                "id": _make_id("unstop", opp_id),
                "title": (item.get("title") or "").strip(),
                "type": opp_type,
                "source": "unstop",
                "url": str(url),
                "description": description,
                "organization": org_name,
                "deadline": str(deadline),
                "prize_pool": prize_str,
                "stipend": stipend[:200],
                "skills_required": json.dumps(skills[:20]),
                "min_cgpa": 0.0,
                "eligible_years": json.dumps(eligible_years),
                "tags": json.dumps(tags[:20]),
                "location": region.capitalize() or "Online",
                "is_remote": is_remote,
                "team_size": team_size[:50],
                "cover_image": str(cover)[:500],
                "is_platform_company": _is_platform(org_name),
            })
        except Exception as exc:
            logger.debug("Skip Unstop item %s: %s", item.get("id"), exc)

    return items


# ── Devfolio crawler ──────────────────────────────────────────────────────────

def _crawl_devfolio_page(status: str, page: int) -> list:
    params: dict[str, Any] = {
        "status": status,
        "page": page,
        "page_size": 50,
    }
    try:
        resp = requests.get(
            _DEVFOLIO_BASE, params=params, headers=_HEADERS, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Devfolio %s page %d: %s", status, page, exc)
        return []

    raw_items: list = []
    if isinstance(data, dict):
        raw_items = (
            data.get("results")
            or data.get("hackathons")
            or data.get("data")
            or []
        )
    elif isinstance(data, list):
        raw_items = data

    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            opp_id = item.get("id") or item.get("slug")
            if not opp_id:
                continue

            slug = item.get("slug") or re.sub(
                r"[^a-z0-9]+", "-", (item.get("name") or "").lower()
            ).strip("-")
            url = f"https://devfolio.co/hackathons/{slug}"

            deadline = item.get("ends_at") or item.get("end_date") or ""

            prize_raw = item.get("prize") or item.get("prizes") or item.get("prize_pool") or ""
            prize_str = (
                prize_raw[0] if isinstance(prize_raw, list) and prize_raw else str(prize_raw)
            )[:200]

            skills = []
            for s in (item.get("skills") or item.get("tags") or []):
                name = s.get("title") or s.get("name") if isinstance(s, dict) else s
                if name:
                    skills.append(str(name))

            cover = item.get("banner_url") or item.get("banner") or item.get("logo_url") or ""
            is_online = item.get("is_online", True)
            location = "Online" if is_online else (item.get("city") or item.get("location") or "")

            ts = item.get("team_size") or {}
            team_size = (
                f"{ts.get('min', 1)}–{ts.get('max', 5)}"
                if isinstance(ts, dict) else "1–4"
            )

            description = _strip_html(
                item.get("description") or item.get("about") or item.get("tagline") or ""
            )[:1200]

            _org = item.get("organization") or item.get("org_name") or "Devfolio"
            items.append({
                "id": _make_id("devfolio", opp_id),
                "title": (item.get("name") or item.get("title") or "").strip(),
                "type": "hackathon",
                "source": "devfolio",
                "url": url,
                "description": description,
                "organization": _org,
                "deadline": str(deadline),
                "prize_pool": prize_str,
                "stipend": "",
                "skills_required": json.dumps(skills[:20]),
                "min_cgpa": 0.0,
                "eligible_years": json.dumps([1, 2, 3, 4]),
                "tags": json.dumps(skills[:20]),
                "location": str(location)[:200],
                "is_remote": bool(is_online),
                "team_size": team_size,
                "cover_image": str(cover)[:500],
                "is_platform_company": _is_platform(_org),
            })
        except Exception as exc:
            logger.debug("Skip Devfolio item: %s", exc)

    return items


# ── DB upsert ─────────────────────────────────────────────────────────────────

def _upsert_opportunities(db, items: list) -> int:
    count = 0
    now = datetime.utcnow()
    for item in items:
        if not item.get("id") or not item.get("title"):
            continue
        existing = db.query(Opportunity).filter(Opportunity.id == item["id"]).first()
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
            existing.crawled_at = now
            existing.is_active = True
        else:
            db.add(Opportunity(**item, crawled_at=now, is_active=True))
        count += 1
    db.commit()
    return count


# ── Public crawl functions ────────────────────────────────────────────────────

def crawl_unstop() -> int:
    db = SessionLocal()
    log = CrawlLog(source="unstop", started_at=datetime.utcnow(), status="running")
    db.add(log)
    db.commit()

    total = 0
    try:
        # 4 types × 3 pages × 50 per page = up to 600 from Unstop
        for opp_type in ("hackathons", "competitions", "internships", "jobs"):
            for page in range(1, 4):
                items = _crawl_unstop_page(opp_type, page)
                if not items:
                    break
                total += _upsert_opportunities(db, items)
                logger.info("Unstop %s p%d → %d new", opp_type, page, len(items))
                time.sleep(1.0)   # polite delay
    except Exception as exc:
        log.status = "error"
        log.error_message = str(exc)
        logger.error("Unstop crawl error: %s", exc)
    else:
        log.status = "success"

    log.completed_at = datetime.utcnow()
    log.items_crawled = total
    db.commit()
    db.close()
    logger.info("Unstop crawl complete: %d items", total)
    return total


def crawl_devfolio() -> int:
    db = SessionLocal()
    log = CrawlLog(source="devfolio", started_at=datetime.utcnow(), status="running")
    db.add(log)
    db.commit()

    total = 0
    try:
        for status in ("open", "upcoming"):
            for page in range(1, 4):
                items = _crawl_devfolio_page(status, page)
                if not items:
                    break
                total += _upsert_opportunities(db, items)
                time.sleep(0.8)
    except Exception as exc:
        log.status = "error"
        log.error_message = str(exc)
        logger.warning("Devfolio crawl error (non-fatal): %s", exc)
    else:
        log.status = "success"

    log.completed_at = datetime.utcnow()
    log.items_crawled = total
    db.commit()
    db.close()
    logger.info("Devfolio crawl complete: %d items", total)
    return total


async def run_full_crawl() -> dict:
    loop = asyncio.get_event_loop()
    unstop_count = await loop.run_in_executor(None, crawl_unstop)
    devfolio_count = await loop.run_in_executor(None, crawl_devfolio)
    return {
        "unstop": unstop_count,
        "devfolio": devfolio_count,
        "total": unstop_count + devfolio_count,
    }
