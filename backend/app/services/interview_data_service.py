from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "interview_round_sources.json"
ROUND_ALIASES = {
    "combined": "project_behavioral",
    "projectbehavioral": "project_behavioral",
    "projects": "project_behavioral",
    "project": "project_behavioral",
    "behavioural": "project_behavioral",
    "behavioral": "project_behavioral",
    "project+behavioral": "project_behavioral",
    "project+behavioural": "project_behavioral",
    "cse": "cs_fundamentals",
    "cs": "cs_fundamentals",
    "csfundamentals": "cs_fundamentals",
    "cs_fundamental": "cs_fundamentals",
    "csfundamental": "cs_fundamentals",
    "fundamentals": "cs_fundamentals",
    "coding": "dsa",
}


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


class InterviewDataService:
    """Central read-only access layer for company-wise interview round data."""

    def __init__(self, data_path: Path = DATA_PATH):
        self.data_path = data_path
        self._data = self._load_data()
        self._company_index = self._build_company_index()

    def list_companies(self) -> list[str]:
        return sorted(self._companies().keys())

    def list_companies_for_round(self, round_type: str | None) -> list[str]:
        normalized_round = self.normalize_round_type(round_type)
        if normalized_round == "project_behavioral":
            return self.list_companies()
        companies = []
        for company, profile in self._companies().items():
            config = profile.get("rounds", {}).get(normalized_round, {})
            if normalized_round == "dsa":
                if config.get("enabled", True):
                    companies.append(company)
            elif config.get("enabled"):
                companies.append(company)
        return sorted(companies)

    def resolve_company(self, company_name: str | None) -> str:
        if not company_name:
            return ""
        key = normalize_key(company_name)
        if not key:
            return ""
        if key in self._company_index:
            return self._company_index[key]
        for indexed_key, canonical in self._company_index.items():
            if key in indexed_key or indexed_key in key:
                return canonical
        return ""

    def normalize_round_type(self, round_type: str | None) -> str:
        key = normalize_key(round_type or "")
        if not key:
            return "dsa"
        return ROUND_ALIASES.get(key, key)

    def get_company_profile(self, company_name: str | None) -> dict[str, Any]:
        company = self.resolve_company(company_name)
        if not company:
            return {"company": company_name or "", "tier": "default", "rounds": deepcopy(self._defaults())}
        return deepcopy(self._companies()[company])

    def get_round_config(self, company_name: str | None, round_type: str) -> dict[str, Any]:
        normalized_round = self.normalize_round_type(round_type)
        profile = self.get_company_profile(company_name)
        rounds = profile.get("rounds", {})
        config = rounds.get(normalized_round)
        if config is None:
            config = self._defaults().get(normalized_round, {})
        result = deepcopy(config)
        result.setdefault("round_type", normalized_round)
        result.setdefault("company", profile.get("company") or company_name or "")
        result.setdefault("tier", profile.get("tier", "default"))
        return result

    def get_dsa_config(self, company_name: str | None) -> dict[str, Any]:
        return self.get_round_config(company_name, "dsa")

    def get_project_behavioral_config(self, company_name: str | None) -> dict[str, Any]:
        return self.get_round_config(company_name, "project_behavioral")

    def get_cs_fundamentals_config(self, company_name: str | None) -> dict[str, Any]:
        return self.get_round_config(company_name, "cs_fundamentals")

    def get_cs_topics(self, company_name: str | None) -> list[dict[str, Any]]:
        config = self.get_cs_fundamentals_config(company_name)
        topics = config.get("topics") or []
        if topics:
            return deepcopy(topics)
        return [{"topic": topic, "subtopics": [], "matched_keywords": [], "source_urls": [], "evidence_count": 0} for topic in config.get("fallback_topics", [])]

    def get_summary(self) -> dict[str, Any]:
        companies = self._companies()
        cs_enabled = sum(1 for item in companies.values() if item.get("rounds", {}).get("cs_fundamentals", {}).get("enabled"))
        dsa_tagged = sum(1 for item in companies.values() if item.get("rounds", {}).get("dsa", {}).get("problem_bank", {}).get("has_company_tagged_problems"))
        return {
            "schema_version": self._data.get("schema_version", ""),
            "company_count": len(companies),
            "cs_enabled_company_count": cs_enabled,
            "dsa_tagged_company_count": dsa_tagged,
            "source_path": str(self.data_path),
        }

    def _load_data(self) -> dict[str, Any]:
        if not self.data_path.exists():
            raise FileNotFoundError(f"Interview round source data not found: {self.data_path}")
        return json.loads(self.data_path.read_text(encoding="utf-8-sig"))

    def _companies(self) -> dict[str, Any]:
        return self._data.get("companies", {})

    def _defaults(self) -> dict[str, Any]:
        return self._data.get("defaults", {})

    def _build_company_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for company, profile in self._companies().items():
            index[normalize_key(company)] = company
            display_name = profile.get("company")
            if display_name:
                index[normalize_key(display_name)] = company
        for company, profile in self._companies().items():
            for alias in self._aliases_from_profile(profile):
                index.setdefault(normalize_key(alias), company)
        return {key: value for key, value in index.items() if key}

    def _aliases_from_profile(self, profile: dict[str, Any]) -> list[str]:
        aliases = profile.get("aliases", [])
        if isinstance(aliases, list):
            return [str(alias) for alias in aliases if alias]
        if isinstance(aliases, dict):
            return [str(alias) for alias in aliases.values() if alias]
        if isinstance(aliases, str):
            return [aliases]
        return []


interview_data_service = InterviewDataService()


def list_companies() -> list[str]:
    return interview_data_service.list_companies()


def list_companies_for_round(round_type: str | None) -> list[str]:
    return interview_data_service.list_companies_for_round(round_type)


def resolve_company(company_name: str | None) -> str:
    return interview_data_service.resolve_company(company_name)


def get_round_config(company_name: str | None, round_type: str) -> dict[str, Any]:
    return interview_data_service.get_round_config(company_name, round_type)


def get_dsa_config(company_name: str | None) -> dict[str, Any]:
    return interview_data_service.get_dsa_config(company_name)


def get_project_behavioral_config(company_name: str | None) -> dict[str, Any]:
    return interview_data_service.get_project_behavioral_config(company_name)


def get_cs_fundamentals_config(company_name: str | None) -> dict[str, Any]:
    return interview_data_service.get_cs_fundamentals_config(company_name)
