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


APP_VERSION = "1.1.0-mvp"
SESSIONS: dict[str, dict[str, Any]] = {}
SUPPORTED_LANGUAGES = {"python", "javascript", "cpp", "c", "java"}
LANGUAGE_LABELS = {
    "python": "Python",
    "javascript": "JavaScript",
    "cpp": "C++",
    "c": "C",
    "java": "Java",
}
DATA_DIR = Path(__file__).parent / "app" / "data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_TOOLCHAIN_BIN = PROJECT_ROOT / "tools" / "w64devkit" / "bin"
PROBLEM_DATA_PATH = DATA_DIR / "neenza_merged_problems.json"
FALLBACK_PROBLEM_DATA_PATH = DATA_DIR / "leetcode_problems.json"

def _load_problem_dataset() -> list[dict[str, Any]]:
    path = PROBLEM_DATA_PATH if PROBLEM_DATA_PATH.exists() else FALLBACK_PROBLEM_DATA_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    problems = raw.get("questions", raw) if isinstance(raw, dict) else raw
    normalized = [_normalize_problem(p) for p in problems]
    return [p for p in normalized if p.get("title") and p.get("prompt")]


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
        "javascript": snippets.get("javascript") or "// Write a complete program or adapt this LeetCode function.\n",
        "cpp": snippets.get("cpp") or "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n",
        "c": snippets.get("c") or "#include <stdio.h>\n\nint main(void) {\n    return 0;\n}\n",
        "java": snippets.get("java") or "class Main {\n    public static void main(String[] args) {\n    }\n}\n",
    }

    return {
        "id": problem.get("problem_slug") or problem.get("frontend_id") or problem.get("problem_id"),
        "title": problem.get("title", ""),
        "frontend_id": problem.get("frontend_id", ""),
        "difficulty": problem.get("difficulty", "Medium"),
        "source": "neenza/leetcode-problems public dataset",
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
    round_type: str = Field(default="dsa", pattern="^(dsa|combined)$")
    difficulty: str = "medium"
    timer_minutes: int = Field(default=35, ge=10, le=90)


class MessageRequest(BaseModel):
    session_id: str
    user_text: str
    behavioral_metrics: dict[str, Any] = {}


class CodeSubmitRequest(BaseModel):
    session_id: str
    code: str
    language: str = Field(default="python", pattern="^(python|javascript|cpp|c|java)$")
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
    return {"count": len(DSA_PROBLEMS), "difficulty_counts": counts, "source": "neenza/leetcode-problems", "languages": LANGUAGE_LABELS}


@app.get("/api/llm/status")
async def llm_status():
    provider = _active_llm_provider()
    return {
        "provider": provider,
        "configured": bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile") if provider == "groq" else os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "fallback": "guarded_local_interviewer",
    }


@app.post("/api/session/start")
async def start_session(payload: StartSessionRequest):
    session_id = str(uuid.uuid4())
    problem = _select_problem(payload.difficulty)
    SESSIONS[session_id] = {
        "session_id": session_id,
        "created_at": _now(),
        "job_role": payload.job_role,
        "experience_level": payload.experience_level,
        "target_company": payload.target_company,
        "round_type": payload.round_type,
        "difficulty": payload.difficulty,
        "timer_minutes": payload.timer_minutes,
        "phase": "dsa" if payload.round_type == "dsa" else "warmup",
        "question_count": 0,
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
        "llm_enabled": bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "problem": problem,
        "code_runs": [],
    }
    return {
        "session_id": session_id,
        "status": "created",
        "problem": problem,
        "dataset_size": len(DSA_PROBLEMS),
        "languages": LANGUAGE_LABELS,
        "ai_text": _opening_prompt(SESSIONS[session_id]),
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
    return {"status": "parsed", "name": data.get("name", ""), "skills_count": len(data["skills"]), "projects_count": len(data["projects"])}


@app.post("/api/resume/review")
async def review_resume(file: UploadFile = File(...)):
    contents = await file.read()
    text = _extract_resume_text(contents, file.filename or "")
    data = _parse_resume(text)
    return {"resume_data": data, "review": _resume_review(text, data)}


@app.post("/api/interview/message")
async def interview_message(payload: MessageRequest):
    session = _require_session(payload.session_id)
    user_text = payload.user_text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="user_text is required")
    session["messages"].append({"role": "candidate", "content": user_text, "ts": _now()})
    session["question_count"] += 1
    _update_behavior(session, user_text, payload.behavioral_metrics)
    ai_text = _next_interview_turn(session, user_text)
    session["messages"].append({"role": "interviewer", "content": ai_text, "ts": _now()})
    return {
        "ai_text": ai_text,
        "phase": session["phase"],
        "round_complete": session["phase"] == "complete",
        "question_count": session["question_count"],
        "behavioral_signals": session["behavioral_signals"],
        "weak_areas": session["weak_areas"][-5:],
    }


@app.post("/api/interview/submit-code")
async def submit_code(payload: CodeSubmitRequest):
    session = _require_session(payload.session_id)
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}.")
    problem = session["problem"]
    session["code_snapshots"].append({"language": payload.language, "code": payload.code[-8000:], "ts": _now()})
    result = _run_code_tests(payload.code, problem["testcases"], payload.language, problem)
    session["code_runs"].append(result)
    review = _code_review(payload.code, result, problem, payload.language)
    session["messages"].append({"role": "candidate", "content": f"Submitted code for {problem['title']}", "ts": _now()})
    session["messages"].append({"role": "interviewer", "content": review, "ts": _now()})
    return {"ai_text": review, "result": result, "phase": session["phase"], "round_complete": False}


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
    return {"logged": True, "violations_count": len(session["violations"])}


@app.get("/api/feedback/{session_id}")
async def get_feedback(session_id: str):
    session = _require_session(session_id)
    return _feedback_report(session)


@app.post("/api/livekit/token")
async def livekit_token(session_id: str = Form(...)):
    _require_session(session_id)
    if not (os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET") and os.getenv("LIVEKIT_URL")):
        return {"available": False, "fallback": "web_speech", "reason": "LiveKit credentials are not configured."}
    return {"available": False, "fallback": "web_speech", "reason": "Token signing is intentionally disabled in the local MVP until credentials are supplied."}


def _require_session(session_id: str) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_problem(difficulty: str) -> dict[str, Any]:
    wanted = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}.get(difficulty.lower(), "Medium")
    candidates = [p for p in DSA_PROBLEMS if p.get("difficulty") == wanted]
    return random.choice(candidates or DSA_PROBLEMS)


def _opening_prompt(session: dict[str, Any]) -> str:
    if session["round_type"] == "dsa":
        p = session["problem"]
        return f"Hi, I am your AI interviewer. We will begin with a quick intro, then discuss the coding problem visible on the left: {p['title']}. Please introduce yourself briefly and tell me your first approach. I will ask clarifying questions and offer hints only if you request them."
    return "We will start with your background. Walk me through your resume, then I will challenge the project claims and move into behavioral scenarios."


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


def _next_interview_turn(session: dict[str, Any], user_text: str) -> str:
    lower = user_text.lower()
    if session["round_type"] == "dsa":
        direct = _answer_dsa_question(session["problem"], lower)
        if direct:
            return direct
        llm_answer = _llm_interview_turn(session, user_text)
        if llm_answer:
            return llm_answer
        if session["question_count"] == 1 and not _sounds_like_dsa_reasoning(lower):
            return "Thanks for the intro. Now look at the problem statement on the left and tell me your initial approach: what pattern or data structure are you considering, and what makes it fit?"
        if _asks_for_hint(lower) or _sounds_stuck(lower):
            session["hint_count"] += 1
            return _hint_for_problem(session["problem"], session["hint_count"])
        if "o(" not in lower and "complex" not in lower:
            session["weak_areas"].append("Did not state complexity clearly in DSA answer.")
            return "Good direction. Before coding further, tell me the expected time and space complexity. I am looking for reasoning, not the final answer."
        latest_code = session["code_snapshots"][-1]["code"] if session["code_snapshots"] else ""
        if latest_code:
            return _code_probe(latest_code, session["problem"])
        return "Now start coding. I will watch for edge cases, complexity, and whether your implementation matches the approach you described."

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


def _answer_dsa_question(problem: dict[str, Any], lower_text: str) -> str:
    asks_for_cases = any(term in lower_text for term in ["test case", "test cases", "sample", "input", "example"])
    is_question = "?" in lower_text or any(term in lower_text for term in ["where", "what", "show", "give", "provide", "list", "can i see"])
    if asks_for_cases and is_question:
        visible = [tc for tc in problem["testcases"] if tc.get("visible", True)]
        cases = " | ".join(f"Input: {tc['input'].strip()} => Expected: {tc['expected_output']}" for tc in visible)
        return f"Yes. The visible test cases are: {cases}. I will also run hidden edge cases after submission, so your solution should handle the full constraints."
    if any(term in lower_text for term in ["language", "python", "javascript", "java", "c++", "cpp", " c ", "change the language", "choose language"]):
        return "Use the language selector above the editor. This build supports Python, JavaScript, C++, C, and Java. If your machine is missing gcc or g++, C/C++ submissions will show a clear compiler-missing message instead of silently failing."
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
    code_lower = code.lower()
    topics = [t.lower() for t in problem.get("topics", [])]
    if "stack" in topics and "stack" not in code_lower and ".append" not in code_lower and "push" not in code_lower:
        return "I notice your code does not seem to maintain a stack-like structure. For this problem, how will your implementation remember the most recent unmatched opening symbol?"
    if "hash table" in topics and not any(x in code_lower for x in ["dict", "map", "unordered_map", "hashmap", "object", "set"]):
        return "Your code does not appear to use a lookup structure yet. Can you explain how it avoids repeated scanning under the input constraints?"
    if "sliding window" in topics and not any(x in code_lower for x in ["left", "right", "window", "start"]):
        return "I do not see a clear moving-window boundary. What invariant tells you when to advance the left side?"
    return "Based on the code you have typed, explain the main invariant and one edge case that could break it. I will challenge that before accepting the submission."


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
        "cross-question based on candidate code and behavior, and keep replies under 120 words. "
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
    results = []
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        if language == "cpp" and "class Solution" in code and not re.search(r"\bmain\s*\(", code):
            return _run_cpp_leetcode_tests(code, testcases, Path(tmp), problem)

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
            start = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    input=testcase["input"],
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
            results.append({"input": testcase["input"], "expected_output": testcase["expected_output"], "actual_output": actual, "stderr": stderr, "passed": ok, "visible": testcase.get("visible", True), "execution_time_ms": elapsed})
    return {"language": language, "passed_testcases": passed, "total_testcases": len(testcases), "overall_score": round((passed / len(testcases)) * 100, 1), "testcase_results": results}


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
    if language == "javascript":
        if not shutil.which("node"):
            return {"error": "Node.js is not installed or not on PATH, so JavaScript submissions cannot run."}
        return {"path": tmp / "solution.js", "command": ["node", str(tmp / "solution.js")]}
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
    preamble = ""
    if "#include" not in code:
        preamble += "#include <bits/stdc++.h>\n"
    if "using namespace std" not in code:
        preamble += "using namespace std;\n"
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
    actual_clean = actual.strip()
    expected_clean = expected.strip()
    if actual_clean == expected_clean:
        return True
    if actual_clean.lower() == expected_clean.lower():
        return True
    try:
        return json.loads(actual_clean) == json.loads(expected_clean)
    except Exception:
        return False


def _code_review(code: str, result: dict[str, Any], problem: dict[str, Any], language: str) -> str:
    if result["passed_testcases"] == result["total_testcases"]:
        return f"Your {LANGUAGE_LABELS.get(language, language)} code passed the runnable tests. I am not done yet: explain the invariant, time and space complexity, and one hidden edge case that could still break a weaker solution."
    first_fail = next((tc for tc in result["testcase_results"] if not tc["passed"]), {})
    detail = first_fail.get("stderr") or f"expected {first_fail.get('expected_output')}, got {first_fail.get('actual_output')}"
    return f"{result['passed_testcases']} of {result['total_testcases']} tests passed. The first issue is: {detail}. Before changing code, tell me what condition your current logic failed to handle."


def _resume_review(text: str, data: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if len(data["skills"]) < 6:
        issues.append("Skills section is thin or hard to extract. Add a concise skills block grouped by language, backend, frontend, AI, and tools.")
    if not data["projects"]:
        issues.append("Projects are not clearly discoverable. Use project names with bullets for impact, architecture, and measurable result.")
    if not re.search(r"\d+%|\d+x|\d+\+|users|latency|revenue|accuracy", text, re.I):
        issues.append("Impact metrics are weak. Add numbers for scale, latency, accuracy, users, cost, or reliability where honest.")
    return {"score": max(45, 90 - len(issues) * 12), "critical_issues": issues, "best_next_steps": ["Make each project bullet answer: built what, using what, for whom, with what result.", "Prepare interview defenses for every metric and technology claim."]}


def _feedback_report(session: dict[str, Any]) -> dict[str, Any]:
    def avg(values: list[int]) -> float:
        return round(sum(values) / len(values), 1) if values else 0

    scores = {key: avg(value) for key, value in session["scores"].items()}
    integrity_penalty = min(30, len(session["violations"]) * 5)
    overall = round((sum(scores.values()) / max(1, len(scores))) * 20 - integrity_penalty, 1)
    return {
        "session_id": session["session_id"],
        "overall_score": max(0, overall),
        "hiring_signal": "Strong hire" if overall >= 80 else "Leaning hire" if overall >= 65 else "Needs more preparation",
        "scores": scores,
        "weak_areas": session["weak_areas"] or ["Add more precise examples, complexity analysis, and measurable outcomes."],
        "behavioral_signals": session["behavioral_signals"],
        "behavior_log": session.get("behavior_log", []),
        "hint_count": session.get("hint_count", 0),
        "integrity": {"violations": session["violations"], "score": max(0, 100 - integrity_penalty)},
        "code_runs": session["code_runs"],
        "study_plan": ["Practice explaining tradeoffs aloud.", "Prepare STAR stories from real resume experiences.", "Solve 10 timed DSA problems and always state edge cases before coding."],
        "conversation": session["messages"],
    }
