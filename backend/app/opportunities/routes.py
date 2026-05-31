"""
FastAPI router for the Opportunities feature.
Includes the 7-hour background crawler scheduler.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from .crawler import run_full_crawl
from .database import SessionLocal
from .matcher import get_matched_opportunities
from .models import CrawlLog, Opportunity
from .resume_analyzer import analyze_resume

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

_CRAWL_INTERVAL = 7 * 60 * 60   # 7 hours in seconds
_crawl_lock = asyncio.Lock()
_last_crawl: dict[str, Any] = {}


# ── Scheduler (started by main.py lifespan) ───────────────────────────────────

async def crawl_scheduler() -> None:
    """Runs forever: crawl immediately on start, then every 7 hours."""
    logger.info("Opportunity crawler scheduler started (interval=%dh).", _CRAWL_INTERVAL // 3600)
    await asyncio.sleep(5)   # brief delay for server to finish starting

    while True:
        try:
            logger.info("Running scheduled opportunity crawl...")
            async with _crawl_lock:
                result = await run_full_crawl()
                _last_crawl.update(result)
                _last_crawl["crawled_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Crawl done — Unstop: %d, Devfolio: %d, total: %d",
                result["unstop"], result["devfolio"], result["total"],
            )
        except Exception as exc:
            logger.error("Crawler scheduler error: %s", exc)

        await asyncio.sleep(_CRAWL_INTERVAL)


# ── Resume extraction helper ──────────────────────────────────────────────────

def _extract_resume_text(contents: bytes, filename: str) -> str:
    fname = (filename or "").lower()

    if fname.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(contents)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            pass
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contents))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            logger.warning("PDF parse failed: %s", exc)

    return contents.decode("utf-8", errors="ignore")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def crawl_status() -> dict:
    """Crawl stats + total opportunity count."""
    db = SessionLocal()
    try:
        total = db.query(Opportunity).filter(Opportunity.is_active == True).count()   # noqa: E712
        by_source = {
            "unstop": db.query(Opportunity).filter(
                Opportunity.source == "unstop", Opportunity.is_active == True   # noqa: E712
            ).count(),
            "devfolio": db.query(Opportunity).filter(
                Opportunity.source == "devfolio", Opportunity.is_active == True   # noqa: E712
            ).count(),
        }
        last = db.query(CrawlLog).order_by(CrawlLog.id.desc()).first()
    finally:
        db.close()

    return {
        "total_opportunities": total,
        "by_source": by_source,
        "crawl_in_progress": _crawl_lock.locked(),
        "last_crawl": {
            "source": last.source if last else None,
            "status": last.status if last else None,
            "items": last.items_crawled if last else 0,
            "completed_at": last.completed_at.isoformat() if last and last.completed_at else None,
        },
        "next_crawl_interval_hours": _CRAWL_INTERVAL // 3600,
    }


@router.post("/crawl")
async def trigger_crawl(background_tasks: BackgroundTasks) -> dict:
    """Manually trigger a full crawl (runs in background)."""
    if _crawl_lock.locked():
        return {"status": "already_running", "message": "A crawl is already in progress."}

    async def _do() -> None:
        async with _crawl_lock:
            result = await run_full_crawl()
            _last_crawl.update(result)
            _last_crawl["crawled_at"] = datetime.now(timezone.utc).isoformat()

    background_tasks.add_task(_do)
    return {"status": "started", "message": "Crawl started in background."}


@router.post("/analyze")
async def analyze_opportunities(
    resume: Optional[UploadFile] = File(None),
    skills: str = Form(""),
    target_companies: str = Form(""),
    preferred_types: str = Form(""),
    resume_text_override: str = Form(""),
) -> dict:
    """
    Main endpoint: upload resume + optional filters → get matched opportunities.

    Form fields:
      - resume: PDF or TXT file (optional)
      - skills: comma-separated extra skills (optional)
      - target_companies: comma-separated company names (optional)
      - preferred_types: comma-separated types hackathon|job|internship|competition (optional)
      - resume_text_override: pre-extracted text (optional, skips file upload)
    """
    # 1. Extract resume text
    resume_text = resume_text_override.strip()
    if not resume_text and resume and resume.filename:
        try:
            contents = await resume.read()
            resume_text = _extract_resume_text(contents, resume.filename)
        except Exception as exc:
            logger.warning("Resume read error: %s", exc)

    # 2. Analyse resume
    profile: dict[str, Any] = analyze_resume(resume_text) if resume_text else {}

    # 3. Parse optional fields
    extra_skills = [s.strip().lower() for s in skills.split(",") if s.strip()]
    companies = [c.strip() for c in target_companies.split(",") if c.strip()]
    types = [t.strip() for t in preferred_types.split(",") if t.strip()]

    # 4. Check DB
    db = SessionLocal()
    total_in_db = db.query(Opportunity).filter(Opportunity.is_active == True).count()   # noqa: E712
    db.close()

    if total_in_db == 0:
        # Trigger crawl and ask user to retry
        asyncio.create_task(run_full_crawl())
        return {
            "profile": profile,
            "opportunities": [],
            "total_matched": 0,
            "total_in_db": 0,
            "message": "No opportunities cached yet. A crawl has been started — please try again in ~60 seconds.",
            "crawl_triggered": True,
        }

    # 5. Match & rank
    opportunities = get_matched_opportunities(
        profile=profile,
        preferred_types=types,
        extra_skills=extra_skills,
        target_companies=companies,
        limit=60,
    )

    return {
        "profile": profile,
        "opportunities": opportunities,
        "total_matched": len(opportunities),
        "total_in_db": total_in_db,
        "message": f"Found {len(opportunities)} opportunities matching your profile.",
    }
