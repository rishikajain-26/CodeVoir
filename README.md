<<<<<<< HEAD
# Clio — AI Mock Interview Platform

Clio is an agentic AI-powered mock interview platform that simulates real technical interviews with voice interaction, a live code editor, and intelligent adaptive questioning. It conducts DSA (Data Structures & Algorithms), CS Fundamentals, and Project/Behavioral rounds — evaluating candidates in real time and generating detailed feedback reports.

## Features

- **Voice-first interviewing** — Real-time speech recognition (Web Speech API) with ElevenLabs TTS for natural-sounding AI interviewer voice. Time-windowed echo cancellation keeps the conversation smooth.
- **Live code editor** — Monaco Editor with syntax highlighting, multi-language support (Python, JavaScript, Java, C, C++), and in-browser code execution with test case validation.
- **18-node LangGraph pipeline** — Intent resolution, signal extraction, evaluation, contradiction detection, difficulty adjustment, phase tracking, memory compression, and adaptive output generation — all orchestrated as a compiled state graph.
- **Intelligent adaptive questioning** — Tracks 7 interview phases (reading → clarification → brute_force → optimization → coding → testing → closing) and what's been assessed. The LLM uses this to decide what to probe next.
- **Multi-LLM fallback chain** — Claude Sonnet (primary) → OpenAI → Groq/Llama → Gemini Flash, with automatic retry and graceful degradation to hardcoded responses when all providers are unavailable.
- **Behavioral signal analysis** — Tracks speech patterns (WPM, fillers, hesitations, tone), editor behavior (keystrokes, rewrites, approach switches), silence profiles, and confidence trends across turns.
- **Static code analysis** — Tree-sitter powered structural analysis (loop depth, recursion detection, boundary checks, dead code) at zero LLM cost, feeding accurate facts to the evaluator.
- **Contradiction detection** — Catches when a candidate's current claims conflict with prior statements and confronts them directly.
- **Adaptive difficulty & pressure** — Adjusts question difficulty and interviewer pressure based on candidate performance signals.
- **Company-specific personalities** — Interviewer style adapts per target company (e.g., Google, Meta, Amazon).
- **Session persistence** — SQLite with WAL mode for durable session storage across server restarts.
- **Resume parsing** — Upload PDF resumes for context-aware project/behavioral interviews.
- **Detailed feedback reports** — Per-question scoring across problem-solving, coding, communication, debugging, and DSA knowledge, with radar charts, timeline analysis, and hire/reject recommendations.

## Architecture

```
frontend/                React 19 + Vite + Tailwind CSS
  src/App.jsx            Main interview UI — voice, editor, chat, controls
  src/InterviewPage.jsx  Interview session page

backend/                 FastAPI + LangGraph
  main.py                API server — session management, interview endpoints, code execution
  app/
    dsa/
      graph.py           18-node LangGraph state graph (compiled)
      state.py           Pydantic state model (~400 fields across 25+ models)
      llm_text.py        Multi-provider LLM abstraction with fallback chain
      code_analysis.py   Tree-sitter static analysis
      session_adapter.py Session dict ↔ DSAState conversion
      session_actions.py Post-graph problem switching & progress
      progress.py        Question index, time, completion tracking
      schemas_llm.py     Pydantic schemas for structured LLM outputs
      nodes/
        intent.py        Candidate intent resolution
        ingestion.py     Audio, code, and session data ingestion
        signals.py       Speech, editor, silence signal extraction
        evaluation.py    Understanding, approach, complexity, implementation scoring
        memory.py        Turn recording and session memory updates
        compression.py   Memory compaction for long sessions
        contradiction.py Claim consistency tracking
        difficulty.py    Adaptive difficulty adjustment
        output.py        Follow-up generation, hint calibration, contextual response
        report.py        Final feedback report generation
    orchestration/
      dsa_graph.py                  DSA session orchestration (session ↔ graph bridge)
      project_behavioral_graph.py   Behavioral round graph
      cs_fundamentals_graph.py      CS fundamentals round graph
    services/
      session_store.py   SQLite session persistence
      personality_service.py  Company-specific interviewer personalities
      report_service.py  Feedback report builder
      llm_service.py     LLM provider management
      interview_data_service.py  Problem bank and company configs
    runtime/
      sandbox/           Code execution (Docker sandbox)
      languages/         Language adapters (Python, JS, Java, C, C++)
      testcases/         Test case runner
```

## DSA Pipeline (LangGraph)

```
resolve_intent
    |
    +--[advance_question]---> memory_update --> compress --> END
    +--[direct_reply]-------> memory_update --> compress --> END
    +--[escalate_hint]------> hint_calibrator --> compose_hint --> memory_update --> ...
    +--[generate_report]----> report_finalize --> END
    +--[full_eval]----------> ingest --> signals --> evaluate_parallel
                                --> evaluate_dependent --> post_evaluate
                                --> adaptive --> phase_tracker
                                    |
                                    +--[time_pressure_push]
                                    +--[silence_probe]
                                    +--[demand_brute_force]
                                    +--[code_walkthrough]
                                    +--[output_turn]
                                    |
                                    +--> memory_update --> compress_memory --> END
```

## Getting Started
=======
# CodeVoir — AI Career Preparation Platform

CodeVoir helps students practise technical interviews, understand their weak areas, and prepare for real opportunities. It combines company-specific interview rounds, live code execution, feedback reports, resume-aware preparation, and an opportunity recommender in one product.

The project is intentionally organised around three product pillars:

1. **AI Interview Panel** — DSA, CS fundamentals, and project/behavioral interview rounds.
2. **Feedback & Skill Diagnosis** — scoring, transcript history, coding analytics, weak-area detection, and final reports.
3. **Opportunity Preparation Engine** — resume analysis and matching for internships, jobs, hackathons, and competitions.
4. **AI Learning Agent** — source-grounded learning from PDFs, URLs, GitHub repositories, and notes.

## What is included

### Interview rounds

- DSA interview flow with adaptive probing.
- CS fundamentals round.
- Project + behavioral round using resume and job-description context.
- Company-specific round availability and problem datasets.
- Voice input support through the browser Web Speech API.
- Optional ElevenLabs text-to-speech for natural interviewer voice.

### Coding workspace

- Monaco-based code editor.
- Python, Java, C, and C++ support.
- Visible and hidden testcase execution.
- Runtime telemetry and coding analytics.
- Docker sandbox support for safer execution in supported environments.

### AI and orchestration

- FastAPI backend.
- LangGraph-based DSA orchestration.
- Multi-provider LLM support through OpenAI, Anthropic, Groq, and Gemini.
- Offline/demo fallback behavior when external model providers are unavailable.
- Report generation and session persistence.

### Opportunity recommender

- Resume analysis.
- Skills, interests, project, CGPA, branch, year, and experience extraction.
- Opportunity matching and scoring.
- Platform/company mapping utilities.

### AI Learning Agent

- PDF, URL, GitHub repository, and text-note ingestion.
- Source-grounded RAG chat with citations and confidence labels.
- Beginner, advanced, interview, production, and Hinglish explanation modes.
- Notes, summaries, cheatsheets, flashcards, interview questions, revision plans, project pitches, and mindmaps.
- Markdown export for generated material.
- Uses CodeVoir's existing LLM provider fallback service; retrieval still works locally without paid embedding APIs.

## Repository structure

```txt
CodeVoir-main/
  backend/
    main.py                  FastAPI entrypoint and legacy API composition
    app/
      agents/                Interview agents and signal analyzers
      dsa/                   DSA state graph, nodes, schemas, and progress tracking
      orchestration/         DSA, CS, and project/behavioral round orchestration
      opportunities/         Resume analysis and opportunity matching
      learning_agent/         Source ingestion, RAG chat, and revision generators
      realtime/              WebSocket/session event handlers
      runtime/               Code execution, language adapters, sandbox, testcases
      services/              LLM, reporting, session store, analytics services
      data/                  Static datasets only; generated DB files are ignored
    scripts/                 Dataset and backend helper scripts
    tests/                   Scenario and graph tests

  frontend/
    src/
      App.jsx                Current application shell and screen composition
      pages/                 Existing extracted pages
      assets/                UI assets
    public/                  Static frontend assets

  docs/
    ARCHITECTURE.md          System design and data flow
    AI_LEARNING_AGENT.md      Learning agent design and API reference
    DEMO_SCRIPT.md           Suggested judge demo flow
    LIMITATIONS.md           Known limitations and planned improvements
    REFACTOR_NOTES.md        Safe future refactor map
```

## Getting started
>>>>>>> b2a9557 (WIP: saving local work before sync)

### Prerequisites

- Python 3.11+
- Node.js 18+
<<<<<<< HEAD
- At least one LLM API key (OpenAI, Anthropic, Groq, or Gemini)
=======
- At least one LLM API key: OpenAI, Anthropic, Groq, or Gemini
- Chrome is recommended for browser speech recognition
>>>>>>> b2a9557 (WIP: saving local work before sync)

### Backend

```bash
cd backend
python -m venv venv
<<<<<<< HEAD
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

cp .env.example .env
# Edit .env — add at least one LLM API key
=======

# Windows
venv\Scripts\activate

# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Add at least one LLM API key to .env
>>>>>>> b2a9557 (WIP: saving local work before sync)

uvicorn main:app --reload --port 8000
```

<<<<<<< HEAD
=======
Backend API docs will be available at:

```txt
http://127.0.0.1:8000/docs
```

>>>>>>> b2a9557 (WIP: saving local work before sync)
### Frontend

```bash
cd frontend
npm install
<<<<<<< HEAD

# Optional: add ElevenLabs TTS key for natural voice (falls back to browser TTS)
# Create .env.local with:
#   VITE_API_URL=http://127.0.0.1:8000
#   VITE_ELEVENLABS_API_KEY=your_key_here
#   VITE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

npm run dev
```

Open `http://localhost:5173` in Chrome (required for Web Speech API).

### Optional: Docker Services

PostgreSQL and Redis are available via Docker Compose but not required — the app uses SQLite for session persistence by default.

```bash
docker-compose up -d   # starts postgres + redis
```

### Optional: C/C++ Toolchain (Windows)

The backend can compile and run C/C++ submissions if `gcc`/`g++` are on PATH. On Windows, run:
=======
npm run dev
```

Open:

```txt
http://localhost:5173
```

Optional frontend environment variables can be placed in `frontend/.env.local`:

```env
VITE_API_URL=http://127.0.0.1:8000
VITE_ELEVENLABS_API_KEY=your_key_here
VITE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

### Optional Docker services

PostgreSQL and Redis are available through Docker Compose. The app can still run with SQLite session persistence for local demos.

```bash
docker-compose up -d
```

### Optional C/C++ toolchain on Windows
>>>>>>> b2a9557 (WIP: saving local work before sync)

```powershell
.\scripts\setup-w64devkit.ps1
```

<<<<<<< HEAD
Python, JavaScript, and Java support work without this.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | One of these | OpenAI API key |
| `OPENAI_MODEL` | No | OpenAI model name, defaults to `gpt-4o-mini` |
| `GROQ_API_KEY` | One of these | Groq API key (free tier available) |
| `GEMINI_API_KEY` | One of these | Google Gemini API key (free tier available) |
| `ANTHROPIC_API_KEY` | One of these | Claude API key (highest quality, paid) |
| `LLM_PROVIDER` | No | Force a specific provider: `openai`, `anthropic`, `groq`, or `gemini` |
| `DATABASE_URL` | No | PostgreSQL connection string (optional) |
| `VITE_ELEVENLABS_API_KEY` | No | ElevenLabs TTS for natural voice (frontend `.env.local`) |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS, Monaco Editor, Zustand |
| Voice | Web Speech API (recognition), ElevenLabs TTS (synthesis) |
| Backend | FastAPI, Uvicorn, Pydantic v2 |
| AI Pipeline | LangGraph, LangChain |
| LLM Providers | Claude Sonnet, Groq/Llama 3.3, Gemini Flash |
| Code Analysis | Tree-sitter (Python, Java, C, C++) |
| Persistence | SQLite (WAL mode), PostgreSQL (optional) |
| Code Execution | Subprocess sandbox, Docker (optional) |
=======
The backend helper script is path-independent:

```powershell
.\backend\scripts\run_backend.ps1
```

## Environment variables

| Variable | Required | Description |
|---|---:|---|
| `OPENAI_API_KEY` | One provider required | OpenAI API key |
| `OPENAI_MODEL` | No | OpenAI model name, defaults to the configured backend default |
| `ANTHROPIC_API_KEY` | One provider required | Anthropic Claude API key |
| `GROQ_API_KEY` | One provider required | Groq API key |
| `GEMINI_API_KEY` | One provider required | Google Gemini API key |
| `LLM_PROVIDER` | No | Force provider: `openai`, `anthropic`, `groq`, or `gemini` |
| `DATABASE_URL` | No | PostgreSQL connection string; SQLite is used by default |
| `VITE_API_URL` | No | Frontend backend URL |
| `VITE_ELEVENLABS_API_KEY` | No | Optional voice synthesis key |

## Development notes

- Runtime files such as SQLite databases, logs, uploads, and generated vector stores should not be committed.
- `backend/main.py` and `frontend/src/App.jsx` are legacy composition files. They are intentionally left behavior-compatible for the current demo, with a future refactor plan in `docs/REFACTOR_NOTES.md`.
- Keep new features in isolated modules and route files instead of adding more logic to those large entry files.
>>>>>>> b2a9557 (WIP: saving local work before sync)

## License

Private — all rights reserved.
<<<<<<< HEAD
=======

## Out-of-the-Box Demo Features

CodeVoir now includes several committee-wow features inside the AI Learning Agent:

- Source mock interview from uploaded PDFs, URLs, GitHub repos, or notes.
- Weak answer rewriter with scoring and improved answer.
- Skill readiness heatmap.
- 10-second judge/interviewer first-impression simulator.
- Judge demo kit for pitch scripts and wow moments.
- Visual notes, pop-style flashcards, and cleaner mind maps.

See `docs/OUT_OF_THE_BOX_FEATURES.md` for the demo angle.


## Final UI showcase layer

The AI Learning Agent now includes a premium presentation-focused interface: animated flashcards, canvas-style mind maps, readiness heatmaps, a compact evidence drawer, agent progress steps, and full-screen Present Mode for generated outputs. These are designed to make hackathon demos feel polished while keeping source-grounded RAG intact.

## Final Showcase Upgrades

The latest build includes elite developer UI modules:

- Project Architecture Map
- Knowledge Graph
- Evidence Coverage Meter
- Interview Replay Timeline
- Answer Studio with before/after improvement
- Colorful readiness and coverage graphs

See `docs/ELITE_DEVELOPER_UI.md` for demo guidance.


## Provenance

This project includes a cryptographic provenance fingerprint. See `docs/PROVENANCE.md`.
>>>>>>> b2a9557 (WIP: saving local work before sync)
