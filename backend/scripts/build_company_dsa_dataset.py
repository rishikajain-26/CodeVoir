import csv
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "app" / "data"
BASE_DATA_PATH = DATA_DIR / "leetcode_dataset_balanced.json"
OUT_DATA_PATH = DATA_DIR / "company_dsa_dataset.json"
OUT_META_PATH = DATA_DIR / "company_dsa_meta.json"
SOURCE_REPO_PATH = BACKEND_DIR / "tmp_company_wise_problems"

WINDOW_NAMES = {
    "1. Thirty Days.csv": "Thirty Days",
    "2. Three Months.csv": "Three Months",
    "3. Six Months.csv": "Six Months",
    "4. More Than Six Months.csv": "More Than Six Months",
    "5. All.csv": "All",
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"https?://leetcode\.com/problems/([^/]+)/?.*", r"\1", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def problem_keys(problem: dict[str, Any]) -> set[str]:
    keys = {slugify(problem.get("title", "")), slugify(problem.get("id", ""))}
    frontend_id = str(problem.get("frontend_id") or "").strip()
    if frontend_id:
        keys.add(frontend_id)
    return {key for key in keys if key}


def load_base_problems() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    problems = json.loads(BASE_DATA_PATH.read_text(encoding="utf-8"))
    lookup: dict[str, dict[str, Any]] = {}
    for problem in problems:
        for key in problem_keys(problem):
            lookup[key] = problem
    return problems, lookup


def row_keys(row: dict[str, str]) -> list[str]:
    link = row.get("Link", "")
    title = row.get("Title", "")
    return [slugify(link), slugify(title)]


def read_company_rows(company_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for csv_name, window in WINDOW_NAMES.items():
        csv_path = company_dir / csv_name
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                title = (row.get("Title") or "").strip()
                if not title:
                    continue
                rows.append({
                    "company": company_dir.name,
                    "window": window,
                    "title": title,
                    "difficulty": (row.get("Difficulty") or "").strip().title(),
                    "frequency": float(row.get("Frequency") or 0),
                    "acceptance_rate": float(row.get("Acceptance Rate") or 0),
                    "link": (row.get("Link") or "").strip(),
                    "topics": [topic.strip() for topic in (row.get("Topics") or "").split(",") if topic.strip()],
                    "keys": row_keys(row),
                })
    return rows


def main() -> None:
    if not SOURCE_REPO_PATH.exists():
        raise SystemExit(f"Missing {SOURCE_REPO_PATH}. Clone liquidslr/interview-company-wise-problems there first.")
    _base, lookup = load_base_problems()
    merged: dict[str, dict[str, Any]] = {}
    company_stats: dict[str, dict[str, Any]] = {}
    unmatched = []

    for company_dir in sorted(path for path in SOURCE_REPO_PATH.iterdir() if path.is_dir() and not path.name.startswith(".")):
        company_rows = read_company_rows(company_dir)
        matched_ids = set()
        difficulty_counts = Counter()
        for row in company_rows:
            base_problem = next((lookup[key] for key in row["keys"] if key in lookup), None)
            if not base_problem:
                unmatched.append({"company": row["company"], "title": row["title"], "link": row["link"]})
                continue
            problem_id = str(base_problem.get("id") or base_problem.get("title"))
            problem = merged.setdefault(problem_id, deepcopy(base_problem))
            problem.setdefault("companies", [])
            problem.setdefault("company_frequency", {})
            problem.setdefault("company_windows", {})
            problem.setdefault("company_acceptance_rate", {})
            if row["company"] not in problem["companies"]:
                problem["companies"].append(row["company"])
            problem["company_frequency"][row["company"]] = max(float(problem["company_frequency"].get(row["company"], 0)), row["frequency"])
            problem["company_acceptance_rate"][row["company"]] = max(float(problem["company_acceptance_rate"].get(row["company"], 0)), row["acceptance_rate"])
            windows = set(problem["company_windows"].get(row["company"], []))
            windows.add(row["window"])
            problem["company_windows"][row["company"]] = sorted(windows, key=lambda item: list(WINDOW_NAMES.values()).index(item))
            problem["source"] = "liquidslr/interview-company-wise-problems + local executable LeetCode records"
            problem["topics"] = []
            matched_ids.add(problem_id)
            difficulty_counts[problem.get("difficulty", "Unknown")] += 1

        company_stats[company_dir.name] = {
            "count": len(matched_ids),
            "difficulty_counts": dict(difficulty_counts),
        }

    problems = sorted(merged.values(), key=lambda p: (str(p.get("frontend_id", "")).zfill(5), p.get("title", "")))
    for problem in problems:
        problem["companies"] = sorted(problem.get("companies", []))

    meta = {
        "source": "liquidslr/interview-company-wise-problems",
        "source_repo": "https://github.com/liquidslr/interview-company-wise-problems",
        "companies": sorted(company_stats),
        "company_stats": company_stats,
        "matched_problem_count": len(problems),
        "unmatched_count": len(unmatched),
        "unmatched_sample": unmatched[:50],
    }

    OUT_DATA_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(problems)} company-tagged runnable DSA problems")
    print(f"companies={len(company_stats)} unmatched_rows={len(unmatched)}")


if __name__ == "__main__":
    main()
