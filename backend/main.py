import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.interview_data_service import (
    get_cs_fundamentals_config,
    get_dsa_config,
    get_project_behavioral_config,
    interview_data_service,
    list_companies_for_round,
)
from app.services.llm_service import llm_service
from app.services.report_service import build_feedback_report_async
from app.services.session_store import (
    load_all_sessions,
    save_session as _db_save_session,
)

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from app.realtime.websocket.routes import router as websocket_router
except Exception:
    websocket_router = None

try:
    from app.orchestration.project_behavioral_graph import run_project_behavioral_turn
except Exception:
    run_project_behavioral_turn = None

try:
    from app.orchestration.cs_fundamentals_graph import run_cs_fundamentals_turn
except Exception:
    run_cs_fundamentals_turn = None


APP_VERSION = "1.1.0-mvp"
SESSIONS: dict[str, dict[str, Any]] = load_all_sessions()


def _persist(session: dict[str, Any]) -> None:
    """Write-through: save session to SQLite after each mutation."""
    _db_save_session(session)
SUPPORTED_LANGUAGES = {"python", "cpp", "c", "java"}
LANGUAGE_LABELS = {
    "python": "Python",
    "cpp": "C++",
    "c": "C",
    "java": "Java",
}
DATA_DIR = Path(__file__).parent / "app" / "data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_TOOLCHAIN_BIN = PROJECT_ROOT / "tools" / "w64devkit" / "bin"
PROBLEM_DATA_PATH = DATA_DIR / "leetcode_dataset_balanced.json"
COMPANY_PROBLEM_DATA_PATH = DATA_DIR / "company_dsa_dataset.json"
COMPANY_META_PATH = DATA_DIR / "company_dsa_meta.json"
FALLBACK_PROBLEM_DATA_PATH = DATA_DIR / "leetcode_problems.json"
DATASET_SOURCE_LABEL = "liquidslr/interview-company-wise-problems"
DATASET_DISPLAY_LABEL = "company-wise DSA interview problems"

def _load_problem_dataset() -> list[dict[str, Any]]:
    path = COMPANY_PROBLEM_DATA_PATH if COMPANY_PROBLEM_DATA_PATH.exists() else PROBLEM_DATA_PATH if PROBLEM_DATA_PATH.exists() else FALLBACK_PROBLEM_DATA_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    problems = raw.get("questions", raw) if isinstance(raw, dict) else raw
    normalized = [_normalize_problem(p) for p in problems]
    return [p for p in normalized if _is_runnable_problem(p)]


def _is_runnable_problem(problem: dict[str, Any]) -> bool:
    starter_code = problem.get("starter_code") or {}
    testcases = problem.get("testcases") or []
    return bool(
        problem.get("id")
        and problem.get("title")
        and problem.get("prompt")
        and isinstance(starter_code, dict)
        and starter_code.get("python")
        and testcases
    )


def _normalize_problem(problem: dict[str, Any]) -> dict[str, Any]:
    if "description" not in problem:
        return problem

    examples = []
    testcases = []
    for raw_example in problem.get("examples", [])[:4]:
        text = raw_example.get("example_text", "") if isinstance(raw_example, dict) else str(raw_example)
        parsed = _parse_example_text(text)
        examples.append(parsed)
        if parsed["input"] and parsed["output"]:
            testcases.append({
                "input": parsed["input"].replace("Input:", "").strip() + "\n",
                "expected_output": parsed["output"].replace("Output:", "").strip(),
                "visible": True,
            })

    snippets = problem.get("code_snippets", {}) or {}
    starter_code = {
        "python": snippets.get("python3") or snippets.get("python") or "# Write a complete program or adapt this LeetCode method.\n",
        "cpp": snippets.get("cpp") or "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n",
        "c": snippets.get("c") or "#include <stdio.h>\n\nint main(void) {\n    return 0;\n}\n",
        "java": snippets.get("java") or "class Main {\n    public static void main(String[] args) {\n    }\n}\n",
    }

    return {
        "id": problem.get("problem_slug") or problem.get("frontend_id") or problem.get("problem_id"),
        "title": problem.get("title", ""),
        "frontend_id": problem.get("frontend_id", ""),
        "difficulty": problem.get("difficulty", "Medium"),
        "source": DATASET_SOURCE_LABEL,
        "topics": problem.get("topics", []),
        "prompt": _clean_problem_text(problem.get("description", "")),
        "constraints": problem.get("constraints", []),
        "examples": examples,
        "starter_code": starter_code,
        "testcases": testcases,
        "hints": problem.get("hints", []),
    }


def _clean_problem_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_example_text(text: str) -> dict[str, str]:
    clean = _clean_problem_text(text).replace(" Example ", "\nExample ")
    input_match = re.search(r"Input:\s*(.*?)(?:Output:|$)", clean, re.I)
    output_match = re.search(r"Output:\s*(.*?)(?:Explanation:|$)", clean, re.I)
    explanation_match = re.search(r"Explanation:\s*(.*)$", clean, re.I)
    return {
        "input": (input_match.group(1).strip() if input_match else clean.strip()),
        "output": (output_match.group(1).strip() if output_match else ""),
        "explanation": (explanation_match.group(1).strip() if explanation_match else ""),
    }


DSA_PROBLEMS = _load_problem_dataset()
COMPANY_META = json.loads(COMPANY_META_PATH.read_text(encoding="utf-8")) if COMPANY_META_PATH.exists() else {"companies": [], "company_stats": {}}
COMPANY_LOOKUP = {re.sub(r"[^a-z0-9]+", "", company.lower()): company for company in COMPANY_META.get("companies", [])}


def _load_local_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_env()


class StartSessionRequest(BaseModel):
    job_role: str = "Software Engineer"
    experience_level: str = "fresher"
    target_company: str = ""
    job_description: str = ""
    round_type: str = Field(default="dsa", pattern="^(dsa|combined|project_behavioral|cs_fundamentals)$")
    difficulty: str = "medium"
    timer_minutes: int = Field(default=35, ge=10, le=90)


class MessageRequest(BaseModel):
    session_id: str
    user_text: str
    behavioral_metrics: dict[str, Any] = {}
    code_context: dict[str, Any] = {}
    scratchpad: dict[str, Any] = {}


class CodeSubmitRequest(BaseModel):
    session_id: str
    code: str
    language: str = Field(default="python", pattern="^(python|cpp|c|java)$")
    problem_id: str | None = None


class ViolationRequest(BaseModel):
    session_id: str
    event_type: str
    detail: dict[str, Any] = {}


app = FastAPI(title="AI Interview Platform", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if websocket_router:
    app.include_router(websocket_router)


@app.get("/")
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "ai-interview-platform", "version": APP_VERSION, "problems_count": len(DSA_PROBLEMS)}


@app.get("/api/problems/meta")
async def problems_meta():
    counts: dict[str, int] = {}
    for problem in DSA_PROBLEMS:
        counts[problem.get("difficulty", "Unknown")] = counts.get(problem.get("difficulty", "Unknown"), 0) + 1
    return {
        "count": len(DSA_PROBLEMS),
        "difficulty_counts": counts,
        "source": DATASET_SOURCE_LABEL,
        "label": DATASET_DISPLAY_LABEL,
        "languages": LANGUAGE_LABELS,
        "companies": COMPANY_META.get("companies", []),
        "company_stats": COMPANY_META.get("company_stats", {}),
    }


@app.get("/api/problems/companies")
async def problem_companies():
    return {
        "companies": COMPANY_META.get("companies", []),
        "company_stats": COMPANY_META.get("company_stats", {}),
        "source": DATASET_SOURCE_LABEL,
    }


@app.get("/api/interview/round-options")
async def interview_round_options():
    summary = interview_data_service.get_summary()
    return {
        "rounds": [
            {
                "id": "dsa",
                "label": "DSA",
                "company_count": len(list_companies_for_round("dsa")),
                "requires_resume": False,
                "requires_job_description": False,
                "has_live_round": True,
            },
            {
                "id": "project_behavioral",
                "legacy_ids": ["combined"],
                "label": "Project + Behavioural",
                "company_count": len(list_companies_for_round("project_behavioral")),
                "requires_resume": True,
                "requires_job_description": True,
                "has_live_round": True,
            },
            {
                "id": "cs_fundamentals",
                "label": "CS Fundamentals",
                "company_count": len(list_companies_for_round("cs_fundamentals")),
                "requires_resume": False,
                "requires_job_description": False,
                "has_live_round": True,
            },
        ],
        "dataset": summary,
    }


@app.get("/api/interview/companies")
async def interview_companies(round_type: str = "dsa"):
    normalized_round = interview_data_service.normalize_round_type(round_type)
    companies = list_companies_for_round(normalized_round)
    return {
        "round_type": normalized_round,
        "companies": companies,
        "company_count": len(companies),
    }


@app.get("/api/interview/company-config")
async def interview_company_config(company: str, round_type: str = "dsa"):
    normalized_round = interview_data_service.normalize_round_type(round_type)
    return {
        "round_type": normalized_round,
        "company": interview_data_service.resolve_company(company) or company,
        "config": interview_data_service.get_round_config(company, normalized_round),
    }


@app.get("/api/llm/status")
async def llm_status():
    return llm_service.status()


@app.post("/api/session/start")
async def start_session(payload: StartSessionRequest):
    session_id = str(uuid.uuid4())
    normalized_round_type = interview_data_service.normalize_round_type(payload.round_type)
    target_company = _resolve_company(payload.target_company) if normalized_round_type == "dsa" else (interview_data_service.resolve_company(payload.target_company) or payload.target_company)
    problem = _select_problem(payload.difficulty, target_company)
    SESSIONS[session_id] = {
        "session_id": session_id,
        "created_at": _now(),
        "job_role": payload.job_role,
        "experience_level": payload.experience_level,
        "target_company": target_company or payload.target_company,
        "job_description": payload.job_description,
        "round_type": normalized_round_type,
        "requested_round_type": payload.round_type,
        "round_config": _round_config_for_session(normalized_round_type, target_company or payload.target_company),
        "difficulty": payload.difficulty,
        "timer_minutes": payload.timer_minutes,
        "phase": "dsa" if normalized_round_type == "dsa" else "warmup",
        "question_count": 0,
        "exchange_count": 0,
        "messages": [],
        "resume_text": "",
        "resume_data": {},
        "scores": {"clarity": [], "depth": [], "relevance": [], "structure": [], "confidence": []},
        "weak_areas": [],
        "strong_answers": [],
        "contradictions": [],
        "behavioral_signals": {"filler_words": 0, "hesitations": 0, "focus_loss": 0, "paste_events": 0, "voice_turns": 0, "avg_voice_turn_ms": 0, "large_pastes": 0, "idle_gaps": 0, "delete_events": 0, "coding_events": 0},
        "violations": [],
        "behavior_log": [],
        "code_snapshots": [],
        "hint_count": 0,
        "started_intro": False,
        "llm_enabled": llm_service.is_configured(),
        "project_behavioral": {},
        "cs_fundamentals": {},
        "problem": problem,
        "code_runs": [],
        "used_problem_ids": [],
    }
    session = SESSIONS[session_id]
    dsa_progress = _init_dsa_session_progress(session) if normalized_round_type == "dsa" else {}
    _persist(session)
    opening = _opening_prompt(session)
    if normalized_round_type == "dsa" and dsa_progress:
        opening = (
            f"{opening} This {session.get('target_company') or 'company'}-style round has "
            f"{dsa_progress['total_questions']} coding question(s) and about {dsa_progress['allocated_minutes']} minutes total."
        )
    if normalized_round_type == "cs_fundamentals":
        try:
            opening = _cs_opening_question(session)
        except Exception:
            pass
    return {
        "session_id": session_id,
        "status": "created",
        "problem": problem,
        "dataset_size": len(DSA_PROBLEMS),
        "dataset_label": DATASET_DISPLAY_LABEL,
        "target_company": target_company,
        "languages": LANGUAGE_LABELS,
        "round_config": session.get("round_config", {}),
        "dsa_progress": dsa_progress,
        "ai_text": opening,
    }


@app.post("/api/resume/upload")
async def upload_resume(session_id: str = Form(...), file: UploadFile = File(...)):
    session = _require_session(session_id)
    contents = await file.read()
    text = _extract_resume_text(contents, file.filename or "")
    if len(text.strip()) < 40:
        raise HTTPException(status_code=422, detail="Resume text could not be extracted. Use a text-based PDF or TXT file.")
    data = _parse_resume(text)
    session["resume_text"] = text
    session["resume_data"] = data
    _persist(session)
    return {"status": "parsed", "name": data.get("name", ""), "skills_count": len(data["skills"]), "projects_count": len(data["projects"])}


@app.post("/api/resume/review")
async def review_resume(file: UploadFile = File(...)):
    contents = await file.read()
    text = _extract_resume_text(contents, file.filename or "")
    data = _parse_resume(text)
    return {"resume_data": data, "review": _resume_review(text, data)}


@app.get("/api/interview/progress")
async def interview_progress(session_id: str):
    session = _require_session(session_id)
    progress = _dsa_progress_payload(session)
    return {
        "session_id": session_id,
        "round_type": session.get("round_type"),
        "phase": session.get("phase"),
        "dsa_progress": progress,
        "round_config": session.get("round_config", {}),
    }


@app.post("/api/interview/message")
async def interview_message(payload: MessageRequest):
    session = _require_session(payload.session_id)
    user_text = payload.user_text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="user_text is required")
    session["messages"].append({"role": "candidate", "content": user_text, "ts": _now()})
    session["exchange_count"] = int(session.get("exchange_count", 0) or 0) + 1
    session["question_count"] = session["exchange_count"]
    _ingest_code_context(session, payload.code_context, source="message")
    _ingest_scratchpad(session, payload.scratchpad)
    _update_behavior(session, user_text, payload.behavioral_metrics)
    prior_problem_id = str((session.get("problem") or {}).get("id", ""))
    ai_text = await _next_interview_turn(session, user_text, payload.scratchpad, payload.behavioral_metrics)
    session["messages"].append({"role": "interviewer", "content": ai_text, "ts": _now()})
    progress = _dsa_progress_payload(session)
    if progress.get("time_expired") and session.get("round_type") == "dsa":
        session["phase"] = "complete"
        ai_text = (
            f"{ai_text} We have reached the company time limit for this round. "
            "Please wrap up, and end the interview to generate your report."
        ).strip()
    new_problem_id = str((session.get("problem") or {}).get("id", ""))
    problem_changed = new_problem_id != prior_problem_id and bool(new_problem_id)
    degraded = session.pop("_last_reply_degraded", False)
    _persist(session)
    return {
        "ai_text": ai_text,
        "phase": session["phase"],
        "round_complete": session["phase"] == "complete",
        "question_count": session["question_count"],
        "exchange_count": session["exchange_count"],
        "behavioral_signals": session["behavioral_signals"],
        "weak_areas": session["weak_areas"][-5:],
        "dsa_progress": progress,
        "problem": session.get("problem") if problem_changed else None,
        "problem_changed": problem_changed,
        "degraded": degraded,
    }


@app.post("/api/interview/submit-code")
async def submit_code(payload: CodeSubmitRequest):
    session = _require_session(payload.session_id)
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}.")
    problem = session["problem"]
    if payload.problem_id and str(payload.problem_id) != str(problem.get("id")):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The active question changed. I resynced the editor to the current starter code; submit again after reviewing it.",
                "current_problem": problem,
            },
        )
    session["code_snapshots"].append({"language": payload.language, "code": payload.code[-8000:], "ts": _now()})
    session["latest_code_analysis"] = _code_insights(payload.code, payload.language, problem)
    result = _run_code_tests(payload.code, problem["testcases"], payload.language, problem)
    session["code_runs"].append(result)
    session["latest_code_run"] = result
    review = _code_review(payload.code, result, problem, payload.language)
    progress = _dsa_progress_payload(session)
    if session.get("round_type") == "dsa" and session.get("llm_enabled"):
        graph_reply = await _dsa_graph_code_submit_turn(
            session,
            code=payload.code,
            language=payload.language,
            result=result,
            problem=problem,
            fallback_review=review,
        )
        if graph_reply:
            review = graph_reply
        progress = session.get("dsa_progress", progress)
    session["messages"].append({"role": "candidate", "content": f"Ran code for {problem['title']}", "ts": _now()})
    session["messages"].append({"role": "interviewer", "content": review, "ts": _now()})
    _persist(session)
    return {
        "ai_text": review,
        "result": result,
        "phase": session["phase"],
        "round_complete": session.get("phase") == "complete",
        "dsa_progress": progress,
        "problem": session.get("problem"),
        "problem_changed": False,
    }


@app.post("/api/interview/run-tests")
async def run_tests_only(payload: CodeSubmitRequest):
    """Run code against visible test cases. Records the run into the session so the
    interviewer AI can see what was run and its output on the next turn, but does not
    itself trigger an AI response."""
    session = _require_session(payload.session_id)
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}.")
    problem = session["problem"]
    if payload.problem_id and str(payload.problem_id) != str(problem.get("id")):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The active question changed. Resynced the editor to the current starter code.",
                "current_problem": problem,
            },
        )
    result = _run_code_tests(payload.code, problem["testcases"], payload.language, problem)
    session["code_snapshots"].append({"language": payload.language, "code": payload.code[-8000:], "ts": _now()})
    session["latest_code_analysis"] = _code_insights(payload.code, payload.language, problem)
    session["code_runs"].append(result)
    session["latest_code_run"] = result
    _persist(session)
    return {"result": result}


@app.post("/api/interview/violation")
async def log_violation(payload: ViolationRequest):
    session = _require_session(payload.session_id)
    event = {"type": payload.event_type, "detail": payload.detail, "ts": _now()}
    session["violations"].append(event)
    signals = session["behavioral_signals"]
    if payload.event_type in {"tab_hidden", "window_blur", "copy"}:
        session["behavioral_signals"]["focus_loss"] += 1
    if payload.event_type == "paste":
        signals["paste_events"] = signals.get("paste_events", 0) + 1
        session["behavior_log"].append({"ts": _now(), "type": "paste", "detail": payload.detail})
    if payload.event_type == "code_telemetry":
        detail = payload.detail or {}
        signals["coding_events"] = max(signals.get("coding_events", 0), int(detail.get("edits", 0) or 0))
        signals["large_pastes"] = max(signals.get("large_pastes", 0), int(detail.get("largePastes", 0) or 0))
        signals["idle_gaps"] = max(signals.get("idle_gaps", 0), int(detail.get("idleGaps", 0) or 0))
        signals["delete_events"] = max(signals.get("delete_events", 0), int(detail.get("deletions", 0) or 0))
        session["behavior_log"].append({"ts": _now(), "type": "code_telemetry", "detail": detail})
        _ingest_code_context(session, detail, source="telemetry")
    _persist(session)
    return {"logged": True, "violations_count": len(session["violations"])}



@app.get("/api/sessions")
async def list_sessions():
    """List active sessions (lightweight metadata only)."""
    return [
        {
            "session_id": s.get("session_id"),
            "created_at": s.get("created_at"),
            "round_type": s.get("round_type"),
            "target_company": s.get("target_company"),
            "phase": s.get("phase"),
            "exchange_count": s.get("exchange_count", 0),
        }
        for s in SESSIONS.values()
    ]


@app.get("/api/feedback/{session_id}")
async def get_feedback(session_id: str):
    session = _require_session(session_id)
    return await _feedback_report(session)


@app.post("/api/livekit/token")
async def livekit_token(session_id: str = Form(...)):
    _require_session(session_id)
    if not (os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET") and os.getenv("LIVEKIT_URL")):
        return {"available": False, "fallback": "web_speech", "reason": "LiveKit credentials are not configured."}
    return {"available": False, "fallback": "web_speech", "reason": "Token signing is intentionally disabled in the local MVP until credentials are supplied."}


def _require_session(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        from app.services.session_store import load_session
        session = load_session(session_id)
        if session:
            SESSIONS[session_id] = session
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _round_config_for_session(round_type: str, company: str) -> dict[str, Any]:
    if round_type == "dsa":
        return get_dsa_config(company)
    if round_type == "project_behavioral":
        return get_project_behavioral_config(company)
    if round_type == "cs_fundamentals":
        return get_cs_fundamentals_config(company)
    return interview_data_service.get_round_config(company, round_type)


def _init_dsa_session_progress(session: dict[str, Any]) -> dict[str, Any]:
    from app.dsa.progress import build_dsa_progress

    progress = build_dsa_progress(
        round_config=session.get("round_config", {}),
        timer_minutes=int(session.get("timer_minutes", 35) or 35),
    )
    session["dsa_progress"] = progress
    session["used_problem_ids"] = [session.get("problem", {}).get("id")]
    return progress


def _dsa_progress_payload(session: dict[str, Any]) -> dict[str, Any]:
    from app.dsa.progress import refresh_dsa_progress

    if session.get("round_type") != "dsa":
        return {}
    return refresh_dsa_progress(session)


def _select_problem_excluding(
    difficulty: str,
    target_company: str = "",
    exclude_ids: list[Any] | None = None,
) -> dict[str, Any]:
    exclude = {str(item) for item in (exclude_ids or []) if item}
    wanted = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}.get(difficulty.lower(), "Medium")
    pool = DSA_PROBLEMS
    if target_company:
        company_pool = [p for p in DSA_PROBLEMS if target_company in p.get("companies", [])]
        if company_pool:
            pool = company_pool
    candidates = [p for p in pool if p.get("difficulty") == wanted] or pool or DSA_PROBLEMS
    fresh = [p for p in candidates if str(p.get("id")) not in exclude]
    if fresh:
        candidates = fresh
    if target_company:
        weights = [max(1.0, float(problem.get("company_frequency", {}).get(target_company, 1))) for problem in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
    return random.choice(candidates)


def _maybe_advance_dsa_question(session: dict[str, Any], *, reason: str) -> dict[str, Any]:
    from app.dsa.progress import advance_dsa_question, refresh_dsa_progress

    progress = advance_dsa_question(session, reason=reason)
    if progress.get("round_complete"):
        session["phase"] = "complete"
        return progress

    next_problem = _select_problem_excluding(
        session.get("difficulty", "medium"),
        session.get("target_company", ""),
        session.get("used_problem_ids", []),
    )
    session["problem"] = next_problem
    session.setdefault("used_problem_ids", []).append(next_problem.get("id"))
    session["code_snapshots"] = []
    session["code_runs"] = []
    session["latest_code_analysis"] = {}
    refresh_dsa_progress(session)
    return progress


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_company(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    key = re.sub(r"[^a-z0-9]+", "", raw.lower())
    if key in COMPANY_LOOKUP:
        return COMPANY_LOOKUP[key]
    for lookup_key, company in COMPANY_LOOKUP.items():
        if key and (key in lookup_key or lookup_key in key):
            return company
    return raw


def _select_problem(difficulty: str, target_company: str = "") -> dict[str, Any]:
    wanted = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}.get(difficulty.lower(), "Medium")
    pool = DSA_PROBLEMS
    if target_company:
        company_pool = [p for p in DSA_PROBLEMS if target_company in p.get("companies", [])]
        if company_pool:
            pool = company_pool
    candidates = [p for p in pool if p.get("difficulty") == wanted] or pool or DSA_PROBLEMS
    if target_company:
        weights = [max(1.0, float(problem.get("company_frequency", {}).get(target_company, 1))) for problem in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
    return random.choice(candidates)


def _opening_prompt(session: dict[str, Any]) -> str:
    if session["round_type"] == "dsa":
        p = session["problem"]
        company_text = f" for {session['target_company']}" if session.get("target_company") else ""
        return f"Hi, I am your AI interviewer. We will begin with a quick intro, then discuss a company-tagged coding problem{company_text} visible on the left: {p['title']}. Please introduce yourself briefly and tell me your first approach. I will ask clarifying questions and offer hints only if you request them."
    if session["round_type"] == "cs_fundamentals":
        company_text = f" for {session['target_company']}" if session.get("target_company") else ""
        config = session.get("round_config", {})
        raw_topics = config.get("topics", []) or []
        topics = [
            topic.get("topic", "") if isinstance(topic, dict) else str(topic)
            for topic in raw_topics
            if (topic.get("topic") if isinstance(topic, dict) else str(topic))
        ] or config.get("fallback_topics", ["DBMS", "OOP", "Operating Systems", "Computer Networks"])
        topic_text = ", ".join(topics[:4])
        return f"We will start the CS Fundamentals round{company_text}. I will ask concept, comparison, and practical scenario questions across {topic_text}. You can answer verbally or use the scratchpad whenever it helps; I will evaluate it as text, not execute it."
    company_text = f" for {session['target_company']}" if session.get("target_company") else ""
    jd_text = " I will also use the pasted job description." if session.get("job_description", "").strip() else ""
    return f"We will start the Project + Behavioural round{company_text}. Walk me through your resume and strongest project first.{jd_text} I will probe project ownership, tradeoffs, measurable impact, and realistic behavioral examples."


def _cs_opening_question(session: dict[str, Any]) -> str:
    """Generate the very first CS Fundamentals question without running the evaluation/memory nodes."""
    config = session.get("round_config", {})
    raw_topics = config.get("topics", []) or []
    topics = [
        topic.get("topic", "") if isinstance(topic, dict) else str(topic)
        for topic in raw_topics
        if (topic.get("topic") if isinstance(topic, dict) else str(topic))
    ] or config.get("fallback_topics", ["DBMS", "OOP", "Operating Systems", "Computer Networks"])
    first_topic = random.choice(topics) if topics else "DBMS"

    subtopic_map = {
        "DBMS": "ACID properties and transactions",
        "OOP": "polymorphism and interfaces",
        "Operating Systems": "processes, threads, and scheduling",
        "Computer Networks": "HTTP, TCP, and how a request travels from browser to server",
    }
    subtopic = subtopic_map.get(first_topic, first_topic)
    company_text = f" for {session['target_company']}" if session.get("target_company") else ""

    if session.get("llm_enabled") and llm_service.is_configured():
        prompt_ctx = {
            "round": f"CS Fundamentals{company_text}",
            "role": session.get("job_role"),
            "experience": session.get("experience_level"),
            "topic": first_topic,
            "subtopic": subtopic,
            "question_type": "concept",
            "goal": f"establish baseline clarity in {first_topic}",
        }
        question = llm_service.generate(
            "You are a concise CS fundamentals interviewer opening the interview. Ask exactly ONE focused concept question to establish the candidate's baseline. Be direct — no intro, just the question.",
            str(prompt_ctx),
            fallback="",
            temperature=0.4,
            max_tokens=180,
        )
        if question.strip():
            return question.strip()

    return (
        f"Let's begin with {first_topic}. Explain {subtopic}: "
        "what it means, why it matters in practice, and give one real system or scenario where it has direct impact."
    )


def _extract_resume_text(contents: bytes, filename: str) -> str:
    if filename.lower().endswith(".txt"):
        return contents.decode("utf-8", errors="ignore")
    if filename.lower().endswith(".pdf"):
        if pdfplumber:
            with pdfplumber.open(io.BytesIO(contents)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        if PdfReader:
            reader = PdfReader(io.BytesIO(contents))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        raise HTTPException(status_code=500, detail="No PDF parser is available. Install pdfplumber or pypdf.")
    return contents.decode("utf-8", errors="ignore")


def _parse_resume(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    skills = sorted(set(re.findall(r"\b(Python|Java|JavaScript|React|Node|FastAPI|Django|Flask|SQL|PostgreSQL|MongoDB|AWS|Docker|Kubernetes|LangChain|LangGraph|TensorFlow|PyTorch|Machine Learning|LLM|Redis|Kafka)\b", text, re.I)), key=str.lower)
    projects = []
    for line in lines:
        if re.search(r"\b(project|built|developed|implemented|designed)\b", line, re.I):
            projects.append({"name": line[:80], "description": line, "technologies": [s for s in skills if s.lower() in line.lower()], "claims": _claims(line), "questions_asked": []})
        if len(projects) >= 5:
            break
    return {
        "name": lines[0] if lines else "",
        "email": (re.search(r"[\w.-]+@[\w.-]+", text) or [""])[0],
        "skills": skills[:20],
        "projects": projects,
        "experience": [line for line in lines if re.search(r"\b(intern|engineer|developer|analyst|founder)\b", line, re.I)][:5],
        "education": [line for line in lines if re.search(r"\b(university|college|b\.?tech|degree|school)\b", line, re.I)][:5],
    }


def _claims(text: str) -> list[str]:
    return re.findall(r"[^.]*\b(?:increased|reduced|improved|scaled|optimized|led|managed|deployed|users|%|x)\b[^.]*", text, re.I)


def _update_behavior(session: dict[str, Any], text: str, metrics: dict[str, Any]) -> None:
    filler_count = len(re.findall(r"\b(um|uh|like|basically|actually|you know)\b", text, re.I))
    anxiety_terms = len(re.findall(r"\b(stuck|confused|nervous|panic|blank|don't know|dont know|hard|lost)\b", text, re.I))
    signals = session["behavioral_signals"]
    signals["filler_words"] += filler_count
    signals["hesitations"] += int(metrics.get("hesitations", 0))
    signals["nervous_markers"] = signals.get("nervous_markers", 0) + anxiety_terms
    if metrics.get("voice_turn"):
        duration = int(metrics.get("speech_duration_ms", 0) or 0)
        previous_turns = signals.get("voice_turns", 0)
        previous_avg = signals.get("avg_voice_turn_ms", 0)
        signals["voice_turns"] = previous_turns + 1
        signals["avg_voice_turn_ms"] = round(((previous_avg * previous_turns) + duration) / signals["voice_turns"])
    if filler_count or anxiety_terms or metrics:
        session["behavior_log"].append({"ts": _now(), "filler_words": filler_count, "nervous_markers": anxiety_terms, "metrics": metrics, "text_sample": text[:240]})
    words = len(text.split())
    session["scores"]["clarity"].append(4 if words > 35 else 2)
    session["scores"]["depth"].append(4 if any(x in text.lower() for x in ["because", "tradeoff", "complexity", "scaled", "designed"]) else 2)
    session["scores"]["relevance"].append(4 if words > 15 else 2)
    session["scores"]["structure"].append(4 if any(x in text.lower() for x in ["first", "then", "result", "therefore"]) else 2)
    session["scores"]["confidence"].append(max(1, 4 - min(3, filler_count)))


def _ingest_code_context(session: dict[str, Any], context: dict[str, Any], source: str) -> None:
    if not context:
        return
    code_text = str(context.get("code") or context.get("code_excerpt") or "")
    language = str(context.get("language") or context.get("selected_language") or "python")
    if not code_text.strip():
        return
    snapshot = {
        "language": language,
        "code": code_text[-12000:],
        "source": source,
        "ts": _now(),
        "cursor": context.get("cursor"),
        "telemetry": {k: v for k, v in context.items() if k not in {"code", "code_excerpt"}},
    }
    session["code_snapshots"].append(snapshot)
    session["code_snapshots"] = session["code_snapshots"][-12:]
    session["latest_code_analysis"] = _code_insights(code_text, language, session["problem"])


def _ingest_scratchpad(session: dict[str, Any], scratchpad: dict[str, Any]) -> None:
    if not scratchpad:
        return
    content = str(scratchpad.get("content", "") or "").strip()
    if not content:
        return
    mode = str(scratchpad.get("mode", "text") or "text").lower()
    session.setdefault("scratchpad_history", []).append({
        "mode": mode[:30],
        "content": content[-4000:],
        "ts": _now(),
    })
    session["scratchpad_history"] = session["scratchpad_history"][-20:]


async def _next_interview_turn(
    session: dict[str, Any],
    user_text: str,
    scratchpad: dict[str, Any] | None = None,
    behavioral_metrics: dict[str, Any] | None = None,
) -> str:
    import asyncio

    lower = user_text.lower()
    if session["round_type"] == "dsa":
        direct = _answer_dsa_question(session["problem"], lower)
        if direct:
            return direct
        if session.get("llm_enabled"):
            graph_reply = await _dsa_graph_interview_turn(session, user_text, behavioral_metrics)
            if graph_reply:
                return graph_reply
            # Retry once after 1.5s delay (rate limit cooldown)
            await asyncio.sleep(1.5)
            graph_reply = await _dsa_graph_interview_turn(session, user_text, behavioral_metrics)
            if graph_reply:
                return graph_reply
        llm_answer = _llm_interview_turn(session, user_text)
        if llm_answer:
            return llm_answer
        session["_last_reply_degraded"] = True
        return _varied_dsa_fallback(session, user_text, lower)

    if session["round_type"] == "cs_fundamentals":
        if run_cs_fundamentals_turn:
            result = run_cs_fundamentals_turn(session, user_text, scratchpad or {})
            return result.get("ai_text", _cs_fallback_turn(session))
        session["phase"] = "cs_fundamentals"
        return _cs_fallback_turn(session)

    if run_project_behavioral_turn:
        result = run_project_behavioral_turn(session, user_text)
        return result.get("ai_text", "Tell me more about your strongest project, your exact ownership, and one measurable result.")

    projects = session.get("resume_data", {}).get("projects", [])
    if session["question_count"] <= 2:
        session["phase"] = "projects"
        project = projects[0]["name"] if projects else "your strongest project"
        return f"Let's go deeper on {project}. What was the hardest technical decision, what alternatives did you reject, and what measurable result did it create?"
    if session["question_count"] <= 5:
        return "I want specifics. Describe one production failure or limitation in that project and how you would redesign it today."
    if session["question_count"] <= 8:
        session["phase"] = "behavioural"
        return "Now answer in STAR format: tell me about a conflict, deadline pressure, or ambiguous requirement from your actual experience."
    session["phase"] = "closing"
    return "We are near the end. Ask me two thoughtful questions you would ask a real interviewer, then I will generate your feedback report."


def _dsa_select_next_problem(session: dict[str, Any]) -> dict[str, Any]:
    return _select_problem_excluding(
        session.get("difficulty", "medium"),
        session.get("target_company", ""),
        session.get("used_problem_ids", []),
    )


async def _dsa_graph_interview_turn(
    session: dict[str, Any],
    user_text: str,
    behavioral_metrics: dict[str, Any] | None = None,
) -> str:
    try:
        from app.orchestration.dsa_graph import run_dsa_turn_async

        latest_code = session["code_snapshots"][-1]["code"] if session.get("code_snapshots") else ""
        result = await run_dsa_turn_async(
            session=session,
            candidate_code=latest_code,
            candidate_explanation=user_text,
            problem_statement=session.get("problem", {}).get("prompt", ""),
            editor_context=json.dumps(session.get("latest_code_analysis", {}), ensure_ascii=False)[:2000],
            metrics=behavioral_metrics or {},
            trigger="message",
            select_next_problem=_dsa_select_next_problem,
        )
        reply = (result.get("interviewer_reply") or result.get("followup") or "").strip()
        if result.get("next_action") == "generate_report":
            session["phase"] = "complete"
        return reply
    except Exception as exc:
        session.setdefault("llm_errors", []).append({"ts": _now(), "provider": "dsa_graph", "error": str(exc)[:300]})
        return ""


async def _dsa_graph_code_submit_turn(
    session: dict[str, Any],
    *,
    code: str,
    language: str,
    result: dict[str, Any],
    problem: dict[str, Any],
    fallback_review: str,
) -> str:
    try:
        from app.orchestration.dsa_graph import run_dsa_turn_async

        passed = int(result.get("passed_testcases", 0) or 0)
        total = int(result.get("total_testcases", 0) or 0)
        explanation = (
            f"I submitted my {language} solution for '{problem.get('title', 'the problem')}'. "
            f"Runnable tests: {passed}/{total}. "
            "I want feedback on correctness and edge cases, then one follow-up question on this same problem."
        )
        graph_result = await run_dsa_turn_async(
            session=session,
            candidate_code=code,
            candidate_explanation=explanation,
            problem_statement=problem.get("prompt", ""),
            editor_context=json.dumps({**session.get("latest_code_analysis", {}), "submission": result}, ensure_ascii=False)[
                :2000
            ],
            trigger="code_submit",
            select_next_problem=_dsa_select_next_problem,
        )
        reply = (graph_result.get("interviewer_reply") or graph_result.get("followup") or "").strip()
        return reply or fallback_review
    except Exception as exc:
        session.setdefault("llm_errors", []).append({"ts": _now(), "provider": "dsa_graph_submit", "error": str(exc)[:300]})
        return ""


def _answer_dsa_question(problem: dict[str, Any], lower_text: str) -> str:
    asks_for_cases = any(term in lower_text for term in ["test case", "test cases", "sample", "samples", "examples"])
    is_question = "?" in lower_text or any(term in lower_text for term in ["where", "what", "show", "give", "provide", "list", "can i see"])
    wants_cases_list = asks_for_cases and any(
        term in lower_text for term in ["show", "give", "provide", "list", "can i see", "what are", "tell me the"]
    )
    if wants_cases_list and is_question:
        visible = [tc for tc in problem["testcases"] if tc.get("visible", True)]
        cases = " | ".join(f"Input: {tc['input'].strip()} => Expected: {tc['expected_output']}" for tc in visible)
        return f"Yes. The visible test cases are: {cases}. I will also run hidden edge cases after submission, so your solution should handle the full constraints."
    asks_language = any(term in lower_text for term in ["language", "change the language", "choose language"])
    mentions_language = any(term in lower_text for term in ["python", "java", "c++", "cpp", " c "])
    if asks_language or (is_question and mentions_language):
        return "Use the language selector above the editor. This build supports Python, C++, C, and Java. If your machine is missing gcc, g++, or a JDK, submissions will show a clear compiler-missing message instead of silently failing."
    if any(term in lower_text for term in ["constraint", "constraints", "limit"]):
        return "Constraints: " + "; ".join(problem.get("constraints", []))
    if any(term in lower_text for term in ["what is the problem", "problem statement", "question incomplete"]):
        return "The full statement is visible on the left. In short, identify the input/output contract and constraints, then propose a pattern. I can clarify examples or constraints, but I will avoid giving away the full solution."
    if any(term in lower_text for term in ["explain the problem", "explain this problem", "understand the problem", "what are they asking", "what is it asking"]):
        summary = _problem_summary(problem)
        return f"Sure. In plain terms: {summary} Focus first on the input, output, and constraints. I will not give the solution, but tell me what state or recurrence you think could count the valid outcomes."
    return ""


def _sounds_like_dsa_reasoning(lower_text: str) -> bool:
    terms = [
        "approach", "complexity", "o(", "time", "space", "stack", "queue", "hash", "map", "set",
        "dfs", "bfs", "graph", "tree", "dynamic", "dp", "two pointer", "sliding", "sort", "greedy",
        "edge case", "test case", "example", "constraint", "input", "output", "code",
    ]
    return any(term in lower_text for term in terms) or len(lower_text.split()) > 45


def _problem_summary(problem: dict[str, Any]) -> str:
    prompt = problem.get("prompt", "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", prompt)
    useful = []
    for sentence in sentences:
        if len(sentence) < 8:
            continue
        useful.append(sentence)
        if len(" ".join(useful)) > 260:
            break
    return " ".join(useful)[:420] or f"You need to solve {problem.get('title', 'the displayed problem')} according to the examples and constraints shown on the left."


def _asks_for_hint(lower_text: str) -> bool:
    return any(term in lower_text for term in ["hint", "help", "stuck", "not sure", "confused", "where to start"])


def _sounds_stuck(lower_text: str) -> bool:
    return any(term in lower_text for term in ["i don't know", "i dont know", "blank", "lost", "can't think", "cannot think"])


def _varied_dsa_fallback(session: dict[str, Any], user_text: str, lower: str) -> str:
    """Rotate through 6 distinct follow-up prompts to avoid repeating the same line."""
    exchange = int(session.get("exchange_count", session.get("question_count", 0)) or 0)
    if exchange <= 1 and not _sounds_like_dsa_reasoning(lower):
        return (
            "Thanks for the intro. Now look at the problem statement on the left and tell me "
            "your initial approach: what pattern or data structure are you considering, and what makes it fit?"
        )
    if _asks_for_hint(lower) or _sounds_stuck(lower):
        session["hint_count"] += 1
        return _hint_for_problem(session["problem"], session["hint_count"])
    latest_code = session["code_snapshots"][-1]["code"] if session.get("code_snapshots") else ""
    if latest_code:
        probe = _code_probe(latest_code, session["problem"])
        if probe:
            return probe
    if "o(" not in lower and "complex" not in lower:
        session["weak_areas"].append("Did not state complexity clearly in DSA answer.")
    prompts = [
        "Before writing more code, state the expected time and space complexity and explain why that bound is achievable.",
        "Walk me through one concrete example using the first visible test case. What does your algorithm do at each individual step?",
        "What edge cases does your current approach handle? Name at least two: one with empty or minimum input, one with unexpected ordering.",
        "If your approach is O(n²), how would you reduce it? Which data structure or technique removes the inner scan?",
        "Explain your invariant: what property must always hold true at each iteration or recursive call in your solution?",
        "Code aside — what is the hardest part of this problem? Tell me exactly where a subtle bug would most likely hide.",
    ]
    return prompts[exchange % len(prompts)]


def _cs_fallback_turn(session: dict[str, Any]) -> str:
    """Return a rotating real CS question so the interview never repeats itself without LLM."""
    exchange = int(session.get("exchange_count", session.get("question_count", 0)) or 0)
    questions = [
        "Explain what ACID properties mean in a database. Give a real example of a transaction that would violate atomicity if partial writes were allowed.",
        "Compare a B-tree index to a full-table scan. When does adding an index hurt write performance more than it helps read speed?",
        "What is the difference between a process and a thread? Give a concrete scenario where you would choose threads over processes in a backend service.",
        "Explain how a deadlock occurs in an OS. State the four Coffman conditions and say which one is typically easiest to break in practice.",
        "Walk me through an HTTP request from browser to server step by step — include DNS resolution, TCP handshake, and TLS if applicable.",
        "Explain polymorphism with a real code example. What problem does it solve compared to a long if-else or switch chain?",
        "What is the difference between TCP and UDP? Name one application protocol that must use TCP and one that benefits from UDP.",
        "Explain database normalization up to 3NF. Give a denormalized table example and show how you would split it to remove a transitive dependency.",
        "What is the difference between a mutex and a semaphore? When would using a binary semaphore instead of a mutex cause subtle correctness bugs?",
        "Describe encapsulation and its practical benefit. How does hiding internal state prevent bugs in a multi-developer codebase?",
    ]
    return questions[exchange % len(questions)]


def _hint_for_problem(problem: dict[str, Any], hint_count: int) -> str:
    topics = [t.lower() for t in problem.get("topics", [])]
    if hint_count == 1:
        if "stack" in topics:
            return "Hint 1: Think about what must be remembered until a matching closing item appears. What data structure naturally supports last-opened, first-closed behavior?"
        if "sliding window" in topics:
            return "Hint 1: Try maintaining a window that is always valid, then move one boundary only when the condition breaks."
        if "hash table" in topics:
            return "Hint 1: Ask yourself what value you need to find quickly for each current element. Avoid nested scanning if a lookup can remember prior work."
        return "Hint 1: Start from the constraints. If brute force is too slow, what repeated work can you cache or avoid?"
    if hint_count == 2:
        return "Hint 2: Walk one visible example by hand and name the exact state you would update at each step. Do not jump to code until that state is clear."
    return "Final hint: implement the invariant you just described, then test the smallest edge case and one tricky ordering case. I still want you to supply the code and complexity."


def _code_probe(code: str, problem: dict[str, Any]) -> str:
    insights = _code_insights(code, "unknown", problem)
    if insights["optimization_prompts"]:
        return insights["optimization_prompts"][0]
    code_lower = code.lower()
    topics = [t.lower() for t in problem.get("topics", [])]
    if "stack" in topics and "stack" not in code_lower and ".append" not in code_lower and "push" not in code_lower:
        return "I notice your code does not seem to maintain a stack-like structure. For this problem, how will your implementation remember the most recent unmatched opening symbol?"
    if "hash table" in topics and not any(x in code_lower for x in ["dict", "map", "unordered_map", "hashmap", "object", "set"]):
        return "Your code does not appear to use a lookup structure yet. Can you explain how it avoids repeated scanning under the input constraints?"
    if "sliding window" in topics and not any(x in code_lower for x in ["left", "right", "window", "start"]):
        return "I do not see a clear moving-window boundary. What invariant tells you when to advance the left side?"
    return "Based on the code you have typed, explain the main invariant and one edge case that could break it. I will challenge that before accepting the submission."


def _code_insights(code: str, language: str, problem: dict[str, Any]) -> dict[str, Any]:
    code_lower = code.lower()
    lines = [line for line in code.splitlines() if line.strip()]
    topics = [str(t).lower() for t in problem.get("topics", [])]
    signals = []
    prompts = []

    loop_count = len(re.findall(r"\b(for|while)\b", code_lower))
    nested_loop = bool(re.search(r"\b(for|while)\b[\s\S]{0,350}\b(for|while)\b", code_lower))
    recursion = bool(re.search(r"\b(\w+)\s*\([^;{}]*\)\s*\{[\s\S]*\b\1\s*\(", code))
    uses_memo = any(term in code_lower for term in ["memo", "cache", "dp", "unordered_map", "map<", "dict", "lru_cache"])
    uses_hash = any(term in code_lower for term in ["unordered_map", "unordered_set", "hashmap", "hashset", "dict", "set("])
    uses_sort = "sort(" in code_lower or ".sort(" in code_lower
    uses_binary_search = any(term in code_lower for term in ["binary_search", "lower_bound", "upper_bound", "left", "right", "mid"])
    mutates_input = any(term in code_lower for term in ["sort(", ".sort(", "reverse(", ".reverse("])
    pass_vector_by_value = bool(re.search(r"vector\s*<[^>]+>\s+\w+\s*(?:,|\))", code)) and "&" not in code[: max(1, code.find("{"))]
    large_method = len(lines) > 70

    if nested_loop:
        signals.append("nested loops present")
    if recursion:
        signals.append("recursive/helper style")
    if uses_memo:
        signals.append("memoization or DP-like state present")
    if uses_hash:
        signals.append("hash lookup structure present")
    if uses_sort:
        signals.append("sorting/mutation present")
    if pass_vector_by_value:
        signals.append("possible vector pass-by-value copy")
    if large_method:
        signals.append("large method; harder to explain/debug live")

    if ("dynamic programming" in topics or "dp" in topics) and not uses_memo:
        prompts.append("Your current code does not show an obvious DP or memo table yet. What repeated state are you avoiding, and where is it stored?")
    if ("hash table" in topics or "hash" in topics) and not uses_hash:
        prompts.append("This problem is tagged with hash-style lookup, but your code does not show a hash structure. Are you intentionally trading time for simpler scanning?")
    if ("binary search" in topics) and not uses_binary_search:
        prompts.append("I do not see a clear binary-search boundary. What monotonic condition would let you cut the search space?")
    if nested_loop and any(term in topics for term in ["array", "string", "hash table", "two pointers", "sliding window"]):
        prompts.append("I see nested iteration. Under the stated constraints, can this be reduced with a lookup, two pointers, prefix state, or a sliding window?")
    if recursion and not uses_memo and any(term in topics for term in ["dynamic programming", "backtracking", "dfs"]):
        prompts.append("Your recursion does not show memoization. Which subproblems can repeat, and what key would you cache?")
    if pass_vector_by_value and language in {"cpp", "unknown"}:
        prompts.append("Your C++ signature or helper may copy vectors by value. Which parameters should be passed by reference to avoid unnecessary O(n) copies?")
    if mutates_input:
        prompts.append("You mutate or sort input data. Is the original order important for this problem, and can sorting change the meaning of the answer?")
    if not prompts:
        prompts.append("Based on your current code, explain the invariant, the main edge case, and the exact time and space complexity before you continue.")

    return {
        "language": language,
        "line_count": len(lines),
        "loop_count": loop_count,
        "signals": signals,
        "optimization_prompts": prompts[:4],
        "code_excerpt": code[-3000:],
    }


def _active_llm_provider() -> str:
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return "local"


def _llm_interview_turn(session: dict[str, Any], user_text: str) -> str:
    if os.getenv("GROQ_API_KEY"):
        groq_answer = _groq_interview_turn(session, user_text)
        if groq_answer:
            return groq_answer
    if os.getenv("GEMINI_API_KEY"):
        gemini_answer = _gemini_interview_turn(session, user_text)
        if gemini_answer:
            return gemini_answer
    # Both providers failed — retry Gemini once (it has higher RPM than Groq free tier)
    if os.getenv("GEMINI_API_KEY"):
        time.sleep(1.0)
        return _gemini_interview_turn(session, user_text)
    return ""


def _build_interviewer_prompt(session: dict[str, Any], user_text: str) -> dict[str, Any]:
    problem = session["problem"]
    latest_code = session["code_snapshots"][-1] if session["code_snapshots"] else {}
    recent_messages = session["messages"][-8:]
    system = (
        "You are a strict but helpful live DSA interviewer. "
        "Do not solve the problem outright and do not reveal final code. "
        "Answer clarification questions directly, offer progressive hints only when asked or when the candidate is stuck, "
        "cross-question based on the candidate's current editor code, coding habits, and behavior, and keep replies under 120 words. "
        "When code is present, refer to concrete patterns in it: missing memoization, nested loops, mutation, pass-by-value copies, weak invariants, edge cases, or optimization opportunities. "
        "If asked for the full answer, refuse and ask a probing question instead."
    )
    return {
        "system": system,
        "problem": {
            "title": problem.get("title"),
            "difficulty": problem.get("difficulty"),
            "topics": problem.get("topics", []),
            "prompt": problem.get("prompt", "")[:1600],
            "constraints": problem.get("constraints", [])[:8],
            "examples": problem.get("examples", [])[:2],
        },
        "candidate_latest": user_text,
        "recent_conversation": recent_messages,
        "latest_code": latest_code,
        "latest_code_analysis": session.get("latest_code_analysis", {}),
        "behavioral_signals": session.get("behavioral_signals", {}),
        "hint_count": session.get("hint_count", 0),
    }


def _groq_interview_turn(session: dict[str, Any], user_text: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return ""
    prompt = _build_interviewer_prompt(session, user_text)
    try:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": json.dumps({k: v for k, v in prompt.items() if k != "system"}, ensure_ascii=False)},
            ],
            "temperature": 0.35,
            "max_tokens": 220,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "User-Agent": "ClioInterviewLab/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload["choices"][0]["message"]["content"].strip()
        if not text:
            return ""
        return _guard_interviewer_text(text)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(exc)
        session.setdefault("llm_errors", []).append({"ts": _now(), "provider": "groq", "error": f"HTTP {exc.code}: {detail}"[:500]})
        return ""
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        session.setdefault("llm_errors", []).append({"ts": _now(), "provider": "groq", "error": str(exc)[:300]})
        return ""


def _gemini_interview_turn(session: dict[str, Any], user_text: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return ""
    prompt = _build_interviewer_prompt(session, user_text)
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": 220},
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            return ""
        return _guard_interviewer_text(text)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        session.setdefault("llm_errors", []).append({"ts": _now(), "error": str(exc)[:300]})
        return ""


def _guard_interviewer_text(text: str) -> str:
    blocked = ["here is the complete solution", "final code", "copy this code"]
    lowered = text.lower()
    if any(term in lowered for term in blocked):
        return "I cannot give you the final solution. Tell me your current invariant and I will challenge or refine it."
    return text[:900]


def _run_code_tests(code: str, testcases: list[dict[str, str]], language: str, problem: dict[str, Any] | None = None) -> dict[str, Any]:
    visible_testcases = [testcase for testcase in testcases if testcase.get("visible", True)]
    testcases = visible_testcases or testcases
    results = []
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        if language == "python" and problem and problem.get("execution_mode") == "leetcode" and "class Solution" in code:
            return _run_python_visible_leetcode_tests(code, testcases, Path(tmp), problem)
        if language == "cpp" and "class Solution" in code and not re.search(r"\bmain\s*\(", code):
            return _run_cpp_leetcode_tests(code, testcases, Path(tmp), problem)
        if language == "java" and problem and problem.get("execution_mode") == "leetcode" and not re.search(r"\bmain\s*\(", code):
            return _run_java_leetcode_tests(code, testcases, Path(tmp), problem)
        if language == "c" and problem and problem.get("execution_mode") == "leetcode" and not re.search(r"\bmain\s*\(", code):
            return _run_c_leetcode_tests(code, testcases, Path(tmp), problem)

        setup = _prepare_language_command(code, language, Path(tmp))
        if setup.get("error"):
            return {
                "language": language,
                "passed_testcases": 0,
                "total_testcases": max(1, len(testcases)),
                "overall_score": 0,
                "testcase_results": [{
                    "input": "",
                    "expected_output": "",
                    "actual_output": "",
                    "stderr": setup["error"],
                    "passed": False,
                    "visible": True,
                    "execution_time_ms": 0,
                }],
            }
        command = setup["command"]
        if not testcases:
            testcases = [{"input": "", "expected_output": "", "visible": True}]

        path = setup["path"]
        path.write_text(code, encoding="utf-8")
        for testcase in testcases:
            stdin = testcase["input"]
            if re.search(r"\bmain\s*\(", code):
                stdin = _coerce_named_input_for_stdin(testcase["input"])
            start = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    input=stdin,
                    text=True,
                    capture_output=True,
                    timeout=2,
                )
                actual = completed.stdout.strip()
                stderr = completed.stderr.strip()
                timed_out = False
            except subprocess.TimeoutExpired:
                actual, stderr, timed_out = "", "Execution timed out after 2 seconds.", True
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            ok = (not timed_out) and _outputs_equal(actual, testcase["expected_output"])
            passed += int(ok)
            results.append({"input": testcase["input"], "stdin_used": stdin, "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": language, "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


def _run_python_visible_leetcode_tests(code: str, testcases: list[dict[str, str]], tmp: Path, problem: dict[str, Any]) -> dict[str, Any]:
    signature = _parse_python_solution_signature(code, problem)
    if not signature:
        return _runner_error("python", "Could not find a LeetCode-style Solution method in the Python code.", testcases)
    results = []
    passed = 0
    for index, testcase in enumerate(testcases):
        try:
            harness = _build_python_leetcode_harness(code, signature, testcase["input"])
            source = tmp / f"solution_{index}.py"
            source.write_text(harness, encoding="utf-8")
            start = time.perf_counter()
            completed = subprocess.run([sys.executable, str(source)], text=True, capture_output=True, timeout=4)
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            actual = completed.stdout.strip()
            stderr = completed.stderr.strip()
            ok = completed.returncode == 0 and _outputs_equal(actual, testcase["expected_output"])
        except subprocess.TimeoutExpired:
            elapsed = 4000
            actual = ""
            stderr = "Execution timed out after 4 seconds."
            ok = False
        except Exception as exc:
            elapsed = 0
            actual = ""
            stderr = str(exc)
            ok = False
        passed += int(ok)
        results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": "python", "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


def _parse_python_solution_signature(code: str, problem: dict[str, Any] | None = None) -> dict[str, Any] | None:
    wanted = str((problem or {}).get("entry_point") or "")
    search_area = code
    solution_match = re.search(r"class\s+Solution\s*:\s*([\s\S]*)", code)
    if solution_match:
        search_area = solution_match.group(1)
    candidates = []
    for match in re.finditer(r"def\s+(\w+)\s*\(\s*self\s*(?:,\s*(.*?))?\)\s*(?:->\s*([^:]+))?:", search_area, re.S):
        method = match.group(1)
        raw_params = match.group(2) or ""
        params = []
        for part in _split_top_level(raw_params):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, annotation = part.split(":", 1)
                params.append({"name": name.strip(), "type": annotation.strip().strip("'\"")})
            else:
                params.append({"name": part.strip(), "type": "Any"})
        return_type = (match.group(3) or "Any").strip().strip("'\"")
        score = 100 if wanted and method == wanted else 0
        if re.search(r"\b(helper|dfs|solve|backtrack|rec)\b", method, re.I):
            score -= 20
        candidates.append((score, match.start(), {"method": method, "params": params, "return_type": return_type}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _build_python_leetcode_harness(code: str, signature: dict[str, Any], raw_input: str) -> str:
    assignments = _parse_leetcode_assignments(raw_input)
    declarations = []
    arg_names = []
    for index, param in enumerate(signature["params"]):
        value = assignments.get(param["name"])
        if value is None and len(assignments) == 1 and len(signature["params"]) == 1:
            value = next(iter(assignments.values()))
        if value is None:
            raise ValueError(f"Could not find testcase value for Python parameter '{param['name']}' in: {raw_input.strip()}")
        parsed = _parse_literal_value(value)
        arg_name = f"arg{index}"
        declarations.append(f"{arg_name} = {_python_literal(parsed, param.get('type', 'Any'))}")
        arg_names.append(arg_name)
    return f"""{_python_leetcode_support()}

{code}

{chr(10).join(declarations)}
result = Solution().{signature['method']}({', '.join(arg_names)})
print_value(result)
"""


def _python_literal(value: Any, annotation: str) -> str:
    cleaned = annotation.replace("typing.", "").replace(" ", "").strip("'\"")
    if cleaned in {"TreeNode", "Optional[TreeNode]"}:
        return f"tree_node({repr(value)})"
    if cleaned in {"ListNode", "Optional[ListNode]"}:
        return f"list_node({repr(value)})"
    return repr(value)


def _run_python_leetcode_tests(code: str, testcases: list[dict[str, str]], tmp: Path, problem: dict[str, Any]) -> dict[str, Any]:
    check_code = str(problem.get("python_check") or "")
    entry_point = str(problem.get("entry_point") or "")
    if not check_code or not entry_point:
        return _runner_error("python", "This LeetCode problem is missing its Python test harness.", testcases)
    source = tmp / "solution.py"
    harness = f"""{_python_leetcode_support()}

{code}

{check_code}

if __name__ == "__main__":
    candidate = {entry_point}
    check(candidate)
"""
    source.write_text(harness, encoding="utf-8")
    start = time.perf_counter()
    try:
        completed = subprocess.run([sys.executable, str(source)], text=True, capture_output=True, timeout=4)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        ok = completed.returncode == 0
        stderr = completed.stderr.strip()
    except subprocess.TimeoutExpired:
        elapsed = 4000
        ok = False
        stderr = "Execution timed out after 4 seconds."
    if ok:
        return {
            "language": "python",
            "passed_testcases": len(testcases),
            "total_testcases": len(testcases),
            "overall_score": 100,
            "testcase_results": [
                {"input": tc["input"], "expected_output": tc["expected_output"], "actual_output": tc["expected_output"], "stderr": "", "passed": True, "visible": tc.get("visible", True), "execution_time_ms": elapsed}
                for tc in testcases
            ],
        }
    results = []
    for index, tc in enumerate(testcases):
        results.append({
            "input": tc["input"],
            "expected_output": tc["expected_output"],
            "actual_output": "",
            "stderr": stderr or "LeetCode assertion failed.",
            "passed": False,
            "visible": tc.get("visible", True),
            "execution_time_ms": elapsed if index == 0 else 0,
        })
    return {"language": "python", "passed_testcases": 0, "total_testcases": len(testcases), "overall_score": 0, "testcase_results": results}


def _python_leetcode_support() -> str:
    return r'''
from typing import *
from collections import *
from functools import *
from itertools import *
from heapq import *
from bisect import *
import math
import random
import json

class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def list_node(values):
    dummy = ListNode()
    cur = dummy
    for value in values:
        cur.next = ListNode(value)
        cur = cur.next
    return dummy.next

def is_same_list(a, b):
    while a and b:
        if a.val != b.val:
            return False
        a = a.next
        b = b.next
    return a is None and b is None

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def tree_node(values):
    if not values:
        return None
    nodes = [None if value is None else TreeNode(value) for value in values]
    kids = nodes[::-1]
    root = kids.pop()
    for node in nodes:
        if node:
            if kids:
                node.left = kids.pop()
            if kids:
                node.right = kids.pop()
    return root

def is_same_tree(a, b):
    if not a or not b:
        return a is b
    return a.val == b.val and is_same_tree(a.left, b.left) and is_same_tree(a.right, b.right)

def list_values(node):
    out = []
    while node:
        out.append(node.val)
        node = node.next
    return out

def tree_values(root):
    if root is None:
        return []
    out = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            out.append(None)
            continue
        out.append(node.val)
        queue.append(node.left)
        queue.append(node.right)
    while out and out[-1] is None:
        out.pop()
    return out

def print_value(value):
    if isinstance(value, ListNode):
        value = list_values(value)
    elif isinstance(value, TreeNode):
        value = tree_values(value)
    if isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(json.dumps(value, separators=(",", ":")))
'''


def _run_cpp_leetcode_tests(code: str, testcases: list[dict[str, str]], tmp: Path, problem: dict[str, Any] | None = None) -> dict[str, Any]:
    compiler = _find_tool("g++")
    if not compiler:
        return _runner_error("cpp", "g++ was not found on PATH. Install MinGW-w64, MSYS2, or LLVM to run C++ locally.", testcases)
    first_input = testcases[0]["input"] if testcases else ""
    official_cpp = ((problem or {}).get("starter_code") or {}).get("cpp", "")
    signature = _parse_cpp_solution_signature(official_cpp, first_input) if official_cpp else None
    if not signature:
        signature = _parse_cpp_solution_signature(code, first_input)
    if not signature:
        return _runner_error("cpp", "Could not detect the C++ Solution method signature. Use a LeetCode-style public method or provide a full main().", testcases)
    if not testcases:
        testcases = [{"input": "", "expected_output": "", "visible": True}]

    results = []
    passed = 0
    for index, testcase in enumerate(testcases):
        source = tmp / f"solution_{index}.cpp"
        exe = tmp / f"solution_{index}.exe"
        try:
            harness = _build_cpp_leetcode_harness(code, signature, testcase["input"])
        except ValueError as exc:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": str(exc), "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        source.write_text(harness, encoding="utf-8")
        try:
            compiled = subprocess.run([compiler, str(source), "-std=c++17", "-O2", "-o", str(exe)], capture_output=True, text=True, timeout=30, env=_tool_env())
        except subprocess.TimeoutExpired:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": "C++ compilation timed out after 30 seconds.", "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        if compiled.returncode != 0:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": compiled.stderr.strip() or "C++ compilation failed.", "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        start = time.perf_counter()
        try:
            completed = subprocess.run([str(exe)], text=True, capture_output=True, timeout=2, env=_tool_env())
            actual = completed.stdout.strip()
            stderr = completed.stderr.strip()
            timed_out = False
        except subprocess.TimeoutExpired:
            actual, stderr, timed_out = "", "Execution timed out after 2 seconds.", True
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        ok = (not timed_out) and _outputs_equal(actual, testcase["expected_output"])
        passed += int(ok)
        results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": "cpp", "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


def _run_java_leetcode_tests(code: str, testcases: list[dict[str, str]], tmp: Path, problem: dict[str, Any] | None = None) -> dict[str, Any]:
    javac = shutil.which("javac")
    java = shutil.which("java")
    if not javac or not java:
        return _runner_error("java", "Java JDK was not found on PATH. Install a JDK to run Java LeetCode harnesses locally.", testcases)
    official_java = ((problem or {}).get("starter_code") or {}).get("java", "")
    signature = _parse_java_solution_signature(code) or _parse_java_solution_signature(official_java)
    if not signature:
        return _runner_error("java", "Could not detect a Java Solution method signature.", testcases)
    if not testcases:
        testcases = [{"input": "", "expected_output": "", "visible": True}]

    results = []
    passed = 0
    for index, testcase in enumerate(testcases):
        source = tmp / "Main.java"
        try:
            harness = _build_java_leetcode_harness(code, signature, testcase["input"])
        except ValueError as exc:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": str(exc), "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        source.write_text(harness, encoding="utf-8")
        compiled = subprocess.run([javac, str(source)], capture_output=True, text=True, timeout=20)
        if compiled.returncode != 0:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": compiled.stderr.strip() or "Java compilation failed.", "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        start = time.perf_counter()
        try:
            completed = subprocess.run([java, "-cp", str(tmp), "Main"], capture_output=True, text=True, timeout=3)
            actual = completed.stdout.strip()
            stderr = completed.stderr.strip()
            timed_out = False
        except subprocess.TimeoutExpired:
            actual, stderr, timed_out = "", "Execution timed out after 3 seconds.", True
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        ok = (not timed_out) and _outputs_equal(actual, testcase["expected_output"])
        passed += int(ok)
        results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": "java", "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


def _run_c_leetcode_tests(code: str, testcases: list[dict[str, str]], tmp: Path, problem: dict[str, Any] | None = None) -> dict[str, Any]:
    compiler = _find_tool("gcc")
    if not compiler:
        return _runner_error("c", "gcc was not found on PATH. Install MinGW-w64, MSYS2, or LLVM to run C locally.", testcases)
    signature = _parse_c_solution_signature(code)
    if not signature:
        return _runner_error("c", "Could not detect a C function signature for this LeetCode-style problem.", testcases)
    if not testcases:
        testcases = [{"input": "", "expected_output": "", "visible": True}]

    results = []
    passed = 0
    for index, testcase in enumerate(testcases):
        source = tmp / f"solution_{index}.c"
        exe = tmp / f"solution_{index}.exe"
        try:
            harness = _build_c_leetcode_harness(code, signature, testcase["input"])
        except ValueError as exc:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": str(exc), "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        source.write_text(harness, encoding="utf-8")
        compiled = subprocess.run([compiler, str(source), "-std=c11", "-O2", "-o", str(exe)], capture_output=True, text=True, timeout=20, env=_tool_env())
        if compiled.returncode != 0:
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": "", "stderr": compiled.stderr.strip() or "C compilation failed.", "passed": False, "visible": testcase.get("visible", True), "execution_time_ms": 0})
            continue
        start = time.perf_counter()
        try:
            completed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=3, env=_tool_env())
            actual = completed.stdout.strip()
            stderr = completed.stderr.strip()
            timed_out = False
        except subprocess.TimeoutExpired:
            actual, stderr, timed_out = "", "Execution timed out after 3 seconds.", True
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        ok = (not timed_out) and _outputs_equal(actual, testcase["expected_output"])
        passed += int(ok)
        results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": "c", "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


def _runner_error(language: str, message: str, testcases: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "language": language,
        "passed_testcases": 0,
        "total_testcases": max(1, len(testcases)),
        "overall_score": 0,
        "testcase_results": [{"input": "", "expected_output": "", "actual_output": "", "stderr": message, "passed": False, "visible": True, "execution_time_ms": 0}],
    }


def _prepare_language_command(code: str, language: str, tmp: Path) -> dict[str, Any]:
    if language == "python":
        return {"path": tmp / "solution.py", "command": [sys.executable, str(tmp / "solution.py")]}
    if language == "cpp":
        compiler = _find_tool("g++")
        if not compiler:
            return {"error": "g++ was not found on PATH. Install MinGW-w64, MSYS2, or LLVM to run C++ locally."}
        source = tmp / "solution.cpp"
        exe = tmp / "solution.exe"
        source.write_text(code, encoding="utf-8")
        try:
            compiled = subprocess.run([compiler, str(source), "-std=c++17", "-O2", "-o", str(exe)], capture_output=True, text=True, timeout=30, env=_tool_env())
        except subprocess.TimeoutExpired:
            return {"error": "C++ compilation timed out after 30 seconds."}
        if compiled.returncode != 0:
            return {"error": compiled.stderr.strip() or "C++ compilation failed."}
        return {"path": source, "command": [str(exe)]}
    if language == "c":
        compiler = _find_tool("gcc")
        if not compiler:
            return {"error": "gcc was not found on PATH. Install MinGW-w64, MSYS2, or LLVM to run C locally."}
        source = tmp / "solution.c"
        exe = tmp / "solution.exe"
        source.write_text(code, encoding="utf-8")
        compiled = subprocess.run([compiler, str(source), "-std=c11", "-O2", "-o", str(exe)], capture_output=True, text=True, timeout=10, env=_tool_env())
        if compiled.returncode != 0:
            return {"error": compiled.stderr.strip() or "C compilation failed."}
        return {"path": source, "command": [str(exe)]}
    if language == "java":
        javac = shutil.which("javac")
        java = shutil.which("java")
        if not javac or not java:
            return {"error": "Java JDK was not found on PATH. Install a JDK to run Java submissions locally."}
        source = tmp / "Main.java"
        source.write_text(_coerce_java_main(code), encoding="utf-8")
        compiled = subprocess.run([javac, str(source)], capture_output=True, text=True, timeout=10)
        if compiled.returncode != 0:
            return {"error": compiled.stderr.strip() or "Java compilation failed. Use class Main for full-program submissions."}
        return {"path": source, "command": [java, "-cp", str(tmp), "Main"]}
    return {"error": f"Unsupported language: {language}"}


def _parse_java_solution_signature(code: str) -> dict[str, Any] | None:
    for match in re.finditer(r"public\s+([\w\[\]<>]+)\s+(\w+)\s*\(([^)]*)\)\s*\{", code):
        method = match.group(2)
        if method == "main":
            continue
        params = []
        raw_params = match.group(3).strip()
        if raw_params:
            for item in _split_top_level(raw_params):
                parts = item.strip().split()
                if len(parts) < 2:
                    return None
                params.append({"type": " ".join(parts[:-1]), "name": parts[-1]})
        return {"return_type": match.group(1), "method": method, "params": params}
    return None


def _build_java_leetcode_harness(code: str, signature: dict[str, Any], raw_input: str) -> str:
    assignments = _parse_leetcode_assignments(raw_input)
    declarations = []
    arg_names = []
    for index, param in enumerate(signature["params"]):
        value = assignments.get(param["name"])
        if value is None and len(assignments) == 1 and len(signature["params"]) == 1:
            value = next(iter(assignments.values()))
        if value is None:
            raise ValueError(f"Could not find testcase value for Java parameter '{param['name']}' in: {raw_input.strip()}")
        arg_name = f"arg{index}"
        declarations.append(f"{param['type']} {arg_name} = {_java_literal(value, param['type'])};")
        arg_names.append(arg_name)
    result_line = f"{signature['return_type']} result = new Solution().{signature['method']}({', '.join(arg_names)});"
    return f"""{_java_leetcode_support()}

{_ensure_java_solution_class(code)}

public class Main {{
    public static void main(String[] args) {{
        {' '.join(declarations)}
        {result_line}
        HarnessSupport.printValue(result);
    }}
}}
"""


def _ensure_java_solution_class(code: str) -> str:
    code = code.strip()
    if re.search(r"\bclass\s+Solution\b", code):
        return code.replace("public class Solution", "class Solution")
    return f"class Solution {{\n{code}\n}}\n"


def _java_literal(value: str, java_type: str) -> str:
    parsed = _parse_literal_value(value)
    cleaned = java_type.replace(" ", "")
    if cleaned == "int":
        return str(int(parsed))
    if cleaned == "long":
        return f"{int(parsed)}L"
    if cleaned in {"double", "float"}:
        return str(parsed)
    if cleaned == "boolean":
        return "true" if bool(parsed) else "false"
    if cleaned == "String":
        return json.dumps(str(parsed))
    if cleaned == "int[]":
        return "new int[]{" + ",".join(str(int(x)) for x in parsed) + "}"
    if cleaned == "String[]":
        return "new String[]{" + ",".join(json.dumps(str(x)) for x in parsed) + "}"
    if cleaned == "boolean[]":
        return "new boolean[]{" + ",".join("true" if x else "false" for x in parsed) + "}"
    if cleaned == "int[][]":
        return "new int[][]{" + ",".join("new int[]{" + ",".join(str(int(x)) for x in row) + "}" for row in parsed) + "}"
    if cleaned == "String[][]":
        return "new String[][]{" + ",".join("new String[]{" + ",".join(json.dumps(str(x)) for x in row) + "}" for row in parsed) + "}"
    if cleaned == "ListNode":
        return "HarnessSupport.buildList(new int[]{" + ",".join(str(int(x)) for x in parsed) + "})"
    if cleaned == "TreeNode":
        return "HarnessSupport.buildTree(new Integer[]{" + ",".join("null" if x is None else str(int(x)) for x in parsed) + "})"
    raise ValueError(f"Unsupported Java harness type: {java_type}")


def _java_leetcode_support() -> str:
    return r'''
import java.util.*;

class ListNode {
    int val;
    ListNode next;
    ListNode() {}
    ListNode(int val) { this.val = val; }
    ListNode(int val, ListNode next) { this.val = val; this.next = next; }
}

class TreeNode {
    int val;
    TreeNode left;
    TreeNode right;
    TreeNode() {}
    TreeNode(int val) { this.val = val; }
    TreeNode(int val, TreeNode left, TreeNode right) { this.val = val; this.left = left; this.right = right; }
}

class HarnessSupport {
    static ListNode buildList(int[] values) {
        ListNode dummy = new ListNode();
        ListNode tail = dummy;
        for (int value : values) {
            tail.next = new ListNode(value);
            tail = tail.next;
        }
        return dummy.next;
    }

    static TreeNode buildTree(Integer[] values) {
        if (values.length == 0 || values[0] == null) return null;
        TreeNode root = new TreeNode(values[0]);
        Queue<TreeNode> queue = new ArrayDeque<>();
        queue.add(root);
        int i = 1;
        while (!queue.isEmpty() && i < values.length) {
            TreeNode current = queue.remove();
            if (i < values.length && values[i] != null) {
                current.left = new TreeNode(values[i]);
                queue.add(current.left);
            }
            i++;
            if (i < values.length && values[i] != null) {
                current.right = new TreeNode(values[i]);
                queue.add(current.right);
            }
            i++;
        }
        return root;
    }

    static void printValue(Object value) {
        if (value == null) { System.out.print("null"); return; }
        if (value instanceof int[]) { System.out.print(Arrays.toString((int[]) value).replace(" ", "")); return; }
        if (value instanceof long[]) { System.out.print(Arrays.toString((long[]) value).replace(" ", "")); return; }
        if (value instanceof double[]) { System.out.print(Arrays.toString((double[]) value).replace(" ", "")); return; }
        if (value instanceof boolean[]) { System.out.print(Arrays.toString((boolean[]) value).replace(" ", "")); return; }
        if (value instanceof Object[]) { System.out.print(Arrays.deepToString((Object[]) value).replace(" ", "")); return; }
        if (value instanceof ListNode) { printList((ListNode) value); return; }
        if (value instanceof TreeNode) { printTree((TreeNode) value); return; }
        System.out.print(String.valueOf(value));
    }

    static void printList(ListNode node) {
        System.out.print("[");
        boolean first = true;
        while (node != null) {
            if (!first) System.out.print(",");
            first = false;
            System.out.print(node.val);
            node = node.next;
        }
        System.out.print("]");
    }

    static void printTree(TreeNode root) {
        if (root == null) { System.out.print("[]"); return; }
        ArrayList<String> out = new ArrayList<>();
        Queue<TreeNode> queue = new LinkedList<>();
        queue.add(root);
        while (!queue.isEmpty()) {
            TreeNode cur = queue.remove();
            if (cur == null) {
                out.add("null");
            } else {
                out.add(String.valueOf(cur.val));
                queue.add(cur.left);
                queue.add(cur.right);
            }
        }
        while (!out.isEmpty() && out.get(out.size() - 1).equals("null")) out.remove(out.size() - 1);
        System.out.print("[" + String.join(",", out) + "]");
    }
}

'''


def _parse_c_solution_signature(code: str) -> dict[str, Any] | None:
    pattern = r"((?:struct\s+TreeNode\s*\*|struct\s+ListNode\s*\*|int\s*\*\*|int\s*\*|char\s*\*\*|char\s*\*|bool|int)\s*)\s+(\w+)\s*\(([^)]*)\)\s*\{"
    for match in re.finditer(pattern, code):
        method = match.group(2)
        if method == "main":
            continue
        params = []
        raw_params = match.group(3).strip()
        if raw_params and raw_params != "void":
            for item in _split_top_level(raw_params):
                cleaned = " ".join(item.strip().replace("*", " * ").split())
                param_match = re.match(r"(.+?)\s+([A-Za-z_]\w*)$", cleaned)
                if not param_match:
                    return None
                params.append({"type": _normalize_c_type(param_match.group(1)), "name": param_match.group(2)})
        return {"return_type": _normalize_c_type(match.group(1)), "method": method, "params": params}
    return None


def _normalize_c_type(value: str) -> str:
    cleaned = " ".join(value.replace("*", " * ").split())
    cleaned = cleaned.replace(" * *", "**").replace(" *", "*")
    return cleaned


def _build_c_leetcode_harness(code: str, signature: dict[str, Any], raw_input: str) -> str:
    assignments = _parse_leetcode_assignments(raw_input)
    declarations = []
    call_args = []
    skip_next_size = set()
    return_size_name = ""
    for index, param in enumerate(signature["params"]):
        if index in skip_next_size:
            continue
        name = param["name"]
        ctype = param["type"].replace(" ", "")
        if ctype == "int*" and name == "returnSize":
            declarations.append("int returnSize = 0;")
            call_args.append("&returnSize")
            return_size_name = "returnSize"
            continue
        value = assignments.get(name)
        if value is None and (name.endswith("Size") or name.endswith("ColSize")):
            continue
        if ctype == "int*" and value is not None:
            parsed = _parse_literal_value(value)
            declarations.append(f"int {name}[] = {{{','.join(str(int(x)) for x in parsed)}}};")
            size_name = f"{name}Size"
            declarations.append(f"int {size_name} = {len(parsed)};")
            call_args.extend([name, size_name])
            if index + 1 < len(signature["params"]) and signature["params"][index + 1]["name"] == size_name:
                skip_next_size.add(index + 1)
            continue
        if ctype == "int**" and value is not None:
            parsed = _parse_literal_value(value)
            rows = [list(row) for row in parsed]
            declarations.append(f"int {name}Size = {len(rows)};")
            col_name = f"{name}ColSize"
            declarations.append(f"int {col_name}[] = {{{','.join(str(len(row)) for row in rows)}}};")
            for row_index, row in enumerate(rows):
                declarations.append(f"int {name}_row{row_index}[] = {{{','.join(str(int(x)) for x in row)}}};")
            declarations.append(f"int* {name}[] = {{{','.join(f'{name}_row{row_index}' for row_index in range(len(rows)))}}};")
            call_args.extend([name, f"{name}Size", col_name])
            for offset in (1, 2):
                if index + offset < len(signature["params"]):
                    next_name = signature["params"][index + offset]["name"]
                    if next_name in {f"{name}Size", col_name}:
                        skip_next_size.add(index + offset)
            continue
        if ctype == "char**" and value is not None:
            parsed = _parse_literal_value(value)
            declarations.append(f"char* {name}[] = {{{','.join(json.dumps(str(x)) for x in parsed)}}};")
            size_name = f"{name}Size"
            declarations.append(f"int {size_name} = {len(parsed)};")
            call_args.extend([name, size_name])
            if index + 1 < len(signature["params"]) and signature["params"][index + 1]["name"] == size_name:
                skip_next_size.add(index + 1)
            continue
        if ctype == "structTreeNode*" and value is not None:
            parsed = _parse_literal_value(value)
            declarations.append(f"int {name}Values[] = {{{','.join('INT_MIN' if x is None else str(int(x)) for x in parsed)}}};")
            declarations.append(f"struct TreeNode* {name} = buildTree({name}Values, {len(parsed)});")
            call_args.append(name)
            continue
        if ctype == "structListNode*" and value is not None:
            parsed = _parse_literal_value(value)
            declarations.append(f"int {name}Values[] = {{{','.join(str(int(x)) for x in parsed)}}};")
            declarations.append(f"struct ListNode* {name} = buildList({name}Values, {len(parsed)});")
            call_args.append(name)
            continue
        if value is None:
            raise ValueError(f"Could not find testcase value for C parameter '{name}' in: {raw_input.strip()}")
        if ctype == "int":
            declarations.append(f"int {name} = {int(_parse_literal_value(value))};")
        elif ctype == "bool":
            declarations.append(f"bool {name} = {'true' if _parse_literal_value(value) else 'false'};")
        elif ctype == "char*":
            declarations.append(f"char* {name} = {json.dumps(str(_parse_literal_value(value)))};")
        else:
            raise ValueError(f"Unsupported C harness type: {param['type']}")
        call_args.append(name)

    return_type = signature["return_type"].replace(" ", "")
    if return_type == "int*":
        if not return_size_name:
            declarations.append("int returnSize = 0;")
            call_args.append("&returnSize")
            return_size_name = "returnSize"
        result_line = f"int* result = {signature['method']}({', '.join(call_args)}); printIntArray(result, {return_size_name});"
    elif return_type == "bool":
        result_line = f"bool result = {signature['method']}({', '.join(call_args)}); printf(result ? \"true\" : \"false\");"
    elif return_type == "char*":
        result_line = f"char* result = {signature['method']}({', '.join(call_args)}); printf(\"\\\"%s\\\"\", result);"
    elif return_type == "structTreeNode*":
        result_line = f"struct TreeNode* result = {signature['method']}({', '.join(call_args)}); printTree(result);"
    elif return_type == "structListNode*":
        result_line = f"struct ListNode* result = {signature['method']}({', '.join(call_args)}); printList(result);"
    else:
        result_line = f"int result = {signature['method']}({', '.join(call_args)}); printf(\"%d\", result);"

    return f"""{_c_leetcode_support()}

{code}

int main(void) {{
    {' '.join(declarations)}
    {result_line}
    return 0;
}}
"""


def _c_leetcode_support() -> str:
    return r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

struct ListNode {
    int val;
    struct ListNode *next;
};

struct TreeNode {
    int val;
    struct TreeNode *left;
    struct TreeNode *right;
};

struct ListNode* buildList(int* values, int size) {
    struct ListNode dummy;
    struct ListNode* tail = &dummy;
    dummy.next = NULL;
    for (int i = 0; i < size; ++i) {
        tail->next = malloc(sizeof(struct ListNode));
        tail = tail->next;
        tail->val = values[i];
        tail->next = NULL;
    }
    return dummy.next;
}

struct TreeNode* buildTree(int* values, int size) {
    if (size == 0 || values[0] == INT_MIN) return NULL;
    struct TreeNode** nodes = calloc(size, sizeof(struct TreeNode*));
    for (int i = 0; i < size; ++i) {
        if (values[i] != INT_MIN) {
            nodes[i] = malloc(sizeof(struct TreeNode));
            nodes[i]->val = values[i];
            nodes[i]->left = NULL;
            nodes[i]->right = NULL;
        }
    }
    int child = 1;
    for (int i = 0; i < size && child < size; ++i) {
        if (!nodes[i]) continue;
        if (child < size) nodes[i]->left = nodes[child++];
        if (child < size) nodes[i]->right = nodes[child++];
    }
    struct TreeNode* root = nodes[0];
    free(nodes);
    return root;
}

void printIntArray(int* values, int size) {
    printf("[");
    for (int i = 0; i < size; ++i) {
        if (i) printf(",");
        printf("%d", values[i]);
    }
    printf("]");
}

void printList(struct ListNode* node) {
    printf("[");
    int first = 1;
    while (node) {
        if (!first) printf(",");
        first = 0;
        printf("%d", node->val);
        node = node->next;
    }
    printf("]");
}

void printTree(struct TreeNode* root) {
    if (!root) {
        printf("[]");
        return;
    }
    struct TreeNode** queue = calloc(10000, sizeof(struct TreeNode*));
    char** out = calloc(10000, sizeof(char*));
    int head = 0, tail = 0, count = 0;
    queue[tail++] = root;
    while (head < tail && tail < 9990) {
        struct TreeNode* cur = queue[head++];
        out[count] = calloc(24, sizeof(char));
        if (!cur) {
            sprintf(out[count++], "null");
            continue;
        }
        sprintf(out[count++], "%d", cur->val);
        queue[tail++] = cur->left;
        queue[tail++] = cur->right;
    }
    while (count > 0 && strcmp(out[count - 1], "null") == 0) count--;
    printf("[");
    for (int i = 0; i < count; ++i) {
        if (i) printf(",");
        printf("%s", out[i]);
    }
    printf("]");
}
'''


def _parse_cpp_solution_signature(code: str, raw_input: str = "") -> dict[str, Any] | None:
    assignments = _parse_leetcode_assignments(raw_input) if raw_input else {}
    candidates = []
    for match in re.finditer(r"([\w:<>,\s&*]+?)\s+(\w+)\s*\(([^)]*)\)\s*\{", code, re.S):
        signature = _cpp_signature_from_match(match)
        if not signature:
            continue
        if signature["method"] in {"main", "operator"}:
            continue
        score = _score_cpp_signature(signature, assignments)
        candidates.append((score, match.start(), signature))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _cpp_signature_from_match(match: re.Match[str]) -> dict[str, Any] | None:
    return_type = " ".join(match.group(1).split())
    return_type = re.sub(r".*(?:public|private|protected)\s*:\s*", "", return_type)
    if "{" in return_type:
        return_type = return_type.rsplit("{", 1)[-1].strip()
    method = match.group(2)
    params_raw = match.group(3).strip()
    params = []
    if params_raw:
        for item in _split_top_level(params_raw):
            cleaned = " ".join(item.strip().split())
            param_match = re.match(r"(.+?)([A-Za-z_]\w*)$", cleaned)
            if not param_match:
                return None
            params.append({"type": param_match.group(1).strip(), "name": param_match.group(2)})
    return {"return_type": return_type, "method": method, "params": params}


def _score_cpp_signature(signature: dict[str, Any], assignments: dict[str, str]) -> int:
    params = signature["params"]
    if not params:
        return -50
    score = 0
    names = {param["name"] for param in params}
    if assignments:
        matched = len(names & set(assignments.keys()))
        missing = len(params) - matched
        score += matched * 20
        score -= missing * 12
        if len(assignments) == len(params) and missing == 0:
            score += 25
        if len(assignments) == 1 and len(params) == 1:
            score += 20
    score -= max(0, len(params) - max(1, len(assignments))) * 8
    if signature["return_type"].strip() == "bool":
        score -= 8
    if re.search(r"\b(helper|solve|dfs|backtrack|rec)\b", signature["method"], re.I):
        score -= 18
    return score


def _build_cpp_leetcode_harness(code: str, signature: dict[str, Any], raw_input: str) -> str:
    assignments = _parse_leetcode_assignments(raw_input)
    declarations = []
    arg_names = []
    for index, param in enumerate(signature["params"]):
        value = assignments.get(param["name"])
        if value is None and len(assignments) == 1 and len(signature["params"]) == 1:
            value = next(iter(assignments.values()))
        if value is None:
            raise ValueError(f"Could not find testcase value for parameter '{param['name']}' in: {raw_input.strip()}")
        arg_name = f"arg{index}"
        declarations.append(f"{_cpp_value_type(param['type'])} {arg_name} = {_cpp_literal(value, param['type'])};")
        arg_names.append(arg_name)

    body = _ensure_cpp_preamble(code)
    printer = _cpp_print_expression("result", signature["return_type"])
    return f"""{body}

int main() {{
    Solution sol;
    {' '.join(declarations)}
    auto result = sol.{signature['method']}({', '.join(arg_names)});
    {printer}
    return 0;
}}
"""


def _ensure_cpp_preamble(code: str) -> str:
    preamble = "#include <bits/stdc++.h>\nusing namespace std;\n"
    preamble += """
struct ListNode {
    int val;
    ListNode *next;
    ListNode() : val(0), next(nullptr) {}
    ListNode(int x) : val(x), next(nullptr) {}
    ListNode(int x, ListNode *next) : val(x), next(next) {}
};

struct TreeNode {
    int val;
    TreeNode *left;
    TreeNode *right;
    TreeNode() : val(0), left(nullptr), right(nullptr) {}
    TreeNode(int x) : val(x), left(nullptr), right(nullptr) {}
    TreeNode(int x, TreeNode *left, TreeNode *right) : val(x), left(left), right(right) {}
};

template <class T>
void printCppValue(ostream& os, const T& value) {
    os << value;
}

void printCppValue(ostream& os, const string& value) {
    os << '"';
    for (char ch : value) {
        if (ch == '"' || ch == '\\\\') os << '\\\\';
        os << ch;
    }
    os << '"';
}

template <class T>
ostream& operator<<(ostream& os, const vector<T>& values) {
    os << '[';
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) os << ',';
        printCppValue(os, values[i]);
    }
    os << ']';
    return os;
}

ListNode* buildList(const vector<int>& values) {
    ListNode dummy;
    ListNode* tail = &dummy;
    for (int value : values) {
        tail->next = new ListNode(value);
        tail = tail->next;
    }
    return dummy.next;
}

void printList(ListNode* node) {
    cout << '[';
    bool first = true;
    while (node) {
        if (!first) cout << ',';
        first = false;
        cout << node->val;
        node = node->next;
    }
    cout << ']';
}

TreeNode* buildTree(const vector<long long>& values) {
    if (values.empty() || values[0] == LLONG_MIN) return nullptr;
    TreeNode* root = new TreeNode((int)values[0]);
    queue<TreeNode*> q;
    q.push(root);
    size_t i = 1;
    while (!q.empty() && i < values.size()) {
        TreeNode* cur = q.front();
        q.pop();
        if (i < values.size() && values[i] != LLONG_MIN) {
            cur->left = new TreeNode((int)values[i]);
            q.push(cur->left);
        }
        ++i;
        if (i < values.size() && values[i] != LLONG_MIN) {
            cur->right = new TreeNode((int)values[i]);
            q.push(cur->right);
        }
        ++i;
    }
    return root;
}

void printTree(TreeNode* root) {
    if (!root) {
        cout << "[]";
        return;
    }
    vector<string> out;
    queue<TreeNode*> q;
    q.push(root);
    while (!q.empty()) {
        TreeNode* cur = q.front();
        q.pop();
        if (!cur) {
            out.push_back("null");
            continue;
        }
        out.push_back(to_string(cur->val));
        q.push(cur->left);
        q.push(cur->right);
    }
    while (!out.empty() && out.back() == "null") out.pop_back();
    cout << '[';
    for (size_t i = 0; i < out.size(); ++i) {
        if (i) cout << ',';
        cout << out[i];
    }
    cout << ']';
}
"""
    return preamble + "\n" + code


def _parse_leetcode_assignments(raw_input: str) -> dict[str, str]:
    text = raw_input.strip()
    text = re.sub(r"^Input:\s*", "", text, flags=re.I).strip()
    assignments = {}
    for part in _split_top_level(text):
        if "=" in part:
            name, value = part.split("=", 1)
            assignments[name.strip()] = value.strip()
    if not assignments and text:
        assignments["arg0"] = text
    return assignments


def _coerce_named_input_for_stdin(raw_input: str) -> str:
    assignments = _parse_leetcode_assignments(raw_input)
    if not assignments:
        return raw_input
    chunks = []
    for _name, value in assignments.items():
        parsed = _parse_literal_value(value)
        chunks.extend(_stdin_tokens(parsed))
    return "\n".join(chunks).strip() + "\n"


def _parse_literal_value(value: str) -> Any:
    text = value.strip()
    try:
        jsonish = re.sub(r"\bNone\b", "null", text.replace("'", '"'))
        jsonish = re.sub(r"\bTrue\b", "true", jsonish)
        jsonish = re.sub(r"\bFalse\b", "false", jsonish)
        return json.loads(jsonish)
    except Exception:
        lowered = text.lower()
        if lowered in {"none", "null"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        if re.fullmatch(r"-?\d+\.\d+", text):
            return float(text)
        return text.strip('"')


def _stdin_tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        if value and all(isinstance(row, list) for row in value):
            rows = len(value)
            cols = len(value[0]) if value[0] else 0
            tokens = [str(rows), str(cols)]
            for row in value:
                tokens.extend(str(item).lower() if isinstance(item, bool) else str(item) for item in row)
            return tokens
        return [str(len(value)), *[str(item).lower() if isinstance(item, bool) else str(item) for item in value]]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    return [str(value)]


def _split_top_level(text: str) -> list[str]:
    parts = []
    start = 0
    depth = 0
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in "[({<":
            depth += 1
        elif char in "])}>":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _cpp_value_type(cpp_type: str) -> str:
    cleaned = cpp_type.replace("const ", "").replace("&", "").strip()
    return " ".join(cleaned.split())


def _cpp_literal(value: str, cpp_type: str) -> str:
    value = value.strip()
    normalized_type = _cpp_value_type(cpp_type).replace(" ", "")
    if normalized_type == "ListNode*":
        return f"buildList({_jsonish_to_cpp_initializer(value)})"
    if normalized_type == "TreeNode*":
        return f"buildTree({_tree_cpp_initializer(value)})"
    if normalized_type.startswith("vector<"):
        return _jsonish_to_cpp_initializer(value)
    if normalized_type == "string":
        return _quote_cpp_string(value.strip('"'))
    if normalized_type == "char":
        return f"'{value.strip(chr(39)).strip(chr(34))}'"
    if normalized_type == "bool":
        return value.lower()
    return value


def _jsonish_to_cpp_initializer(value: str) -> str:
    converted = value.replace("[", "{").replace("]", "}")
    converted = re.sub(r"\btrue\b", "true", converted, flags=re.I)
    converted = re.sub(r"\bfalse\b", "false", converted, flags=re.I)
    return converted


def _tree_cpp_initializer(value: str) -> str:
    converted = _jsonish_to_cpp_initializer(value)
    return re.sub(r"\bnull\b", "LLONG_MIN", converted, flags=re.I)


def _quote_cpp_string(value: str) -> str:
    return json.dumps(value)


def _cpp_print_expression(name: str, return_type: str) -> str:
    cleaned = _cpp_value_type(return_type).replace(" ", "")
    if cleaned == "bool":
        return f"cout << ({name} ? \"true\" : \"false\");"
    if cleaned == "ListNode*":
        return f"printList({name});"
    if cleaned == "TreeNode*":
        return f"printTree({name});"
    return f"cout << {name};"


def _find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    portable = PORTABLE_TOOLCHAIN_BIN / f"{name}.exe"
    if portable.exists():
        return str(portable)
    return None


def _tool_env() -> dict[str, str]:
    env = os.environ.copy()
    if PORTABLE_TOOLCHAIN_BIN.exists():
        env["PATH"] = f"{PORTABLE_TOOLCHAIN_BIN}{os.pathsep}{env.get('PATH', '')}"
    return env


def _coerce_java_main(code: str) -> str:
    if "class Main" in code:
        return code
    return code.replace("public class Solution", "class Main").replace("class Solution", "class Main")


def _outputs_equal(actual: str, expected: str) -> bool:
    actual_clean = _normalize_output_text(actual)
    expected_clean = _normalize_output_text(expected)
    if actual_clean == expected_clean:
        return True
    if actual_clean.lower() == expected_clean.lower():
        return True
    try:
        return json.loads(actual_clean) == json.loads(expected_clean)
    except Exception:
        return False


def _normalize_output_text(value: str) -> str:
    text = str(value).strip()
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    return text


def _code_review(code: str, result: dict[str, Any], problem: dict[str, Any], language: str) -> str:
    insights = _code_insights(code, language, problem)
    probe = insights["optimization_prompts"][0] if insights["optimization_prompts"] else "Explain your main invariant and one edge case."
    if result["passed_testcases"] == result["total_testcases"]:
        return f"Your {LANGUAGE_LABELS.get(language, language)} code passed the runnable tests. I am not done yet: {probe} Then state the exact time and space complexity."
    first_fail = next((tc for tc in result["testcase_results"] if not tc["passed"]), {})
    detail = first_fail.get("stderr") or f"expected {first_fail.get('expected_output')}, got {first_fail.get('actual_output')}"
    return f"{result['passed_testcases']} of {result['total_testcases']} tests passed. The first issue is: {detail}. Before changing code, {probe}"


def _resume_review(text: str, data: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if len(data["skills"]) < 6:
        issues.append("Skills section is thin or hard to extract. Add a concise skills block grouped by language, backend, frontend, AI, and tools.")
    if not data["projects"]:
        issues.append("Projects are not clearly discoverable. Use project names with bullets for impact, architecture, and measurable result.")
    if not re.search(r"\d+%|\d+x|\d+\+|users|latency|revenue|accuracy", text, re.I):
        issues.append("Impact metrics are weak. Add numbers for scale, latency, accuracy, users, cost, or reliability where honest.")
    return {"score": max(45, 90 - len(issues) * 12), "critical_issues": issues, "best_next_steps": ["Make each project bullet answer: built what, using what, for whom, with what result.", "Prepare interview defenses for every metric and technology claim."]}


async def _feedback_report(session: dict[str, Any]) -> dict[str, Any]:
    return await build_feedback_report_async(session)
