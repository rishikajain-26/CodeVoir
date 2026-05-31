"""
Shared utility: load platform company names from the Codevoir interview dataset.
Used by both the crawler (marks records at ingest time) and the matcher
(reads the pre-computed flag from DB for boosting).

The company list lives in app/data/interview_round_sources.json.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "interview_round_sources.json"


def _norm(name: str) -> str:
    """Lowercase, strip all non-alphanumeric for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


@lru_cache(maxsize=1)
def platform_company_set() -> frozenset[str]:
    """
    Return the normalized names of every company in the Codevoir interview dataset.
    Result is cached for the process lifetime.
    """
    try:
        data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        companies: dict = data.get("companies", {})
        if isinstance(companies, dict):
            return frozenset(_norm(k) for k in companies.keys() if k)
    except Exception:
        pass
    return frozenset()


def is_platform_company(org_name: str) -> bool:
    """
    Return True if org_name matches any company in the Codevoir interview dataset.
    Uses normalized substring matching so 'Amazon Web Services India' matches 'amazon'.
    """
    if not org_name:
        return False
    pset = platform_company_set()
    if not pset:
        return False
    n = _norm(org_name)
    if not n:
        return False
    # Exact match first (fastest)
    if n in pset:
        return True
    # Substring: platform company name appears inside org name or vice versa
    # Only for names >= 4 chars to avoid false positives (e.g. 'IBM' in 'IBMC')
    for pc in pset:
        if len(pc) >= 4 and (pc in n or n in pc):
            return True
    return False
