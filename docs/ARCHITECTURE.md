# CodeVoir Architecture

CodeVoir is organised as a career-preparation platform with four connected systems: interviews, diagnosis, opportunity preparation, and source-grounded learning.

## Product flow

```txt
User signs in or enters guest mode
        ↓
Chooses company, role, round, difficulty
        ↓
Interview engine starts selected round
        ↓
Candidate speaks, types, codes, and submits answers
        ↓
Backend evaluates signals, code, transcript, and round state
        ↓
Feedback report is generated
        ↓
Weak areas and next steps are shown
        ↓
Opportunity recommender can match internships, jobs, hackathons, and competitions
        ↓
AI Learning Agent can teach weak topics from PDFs, URLs, GitHub repositories, and notes
```

## Backend overview

```txt
FastAPI app
  ├── Authentication and session endpoints
  ├── Interview setup and dashboard endpoints
  ├── Realtime interview/message endpoints
  ├── Code execution endpoints
  ├── Feedback/report endpoints
  ├── Opportunity recommendation endpoints
  └── AI Learning Agent source/RAG/generation endpoints
```

### Important backend packages

```txt
app/dsa/
  LangGraph-style DSA interview state, nodes, schema models, progress, memory, and evaluation.

app/orchestration/
  Bridges API sessions to DSA, CS fundamentals, and project/behavioral interview rounds.

app/runtime/
  Language adapters, sandbox execution, test case runner, and coding telemetry.

app/services/
  LLM provider management, report building, session persistence, analytics, and data loading.

app/opportunities/
  Resume parsing, opportunity crawling/matching, platform/company helpers, and opportunity API routes.

app/learning_agent/
  PDF/URL/GitHub/text ingestion, local embeddings, retrieval, RAG answers, and revision-material generation.

app/realtime/
  WebSocket, session, message, code, and telemetry event handling.
```

## Frontend overview

The frontend currently uses a Vite + React + Tailwind single-shell UI. The UI is functional and polished, but the app shell is still centralized.

```txt
src/App.jsx
  ├── Welcome screen
  ├── Dashboard screen
  ├── Interview setup
  ├── Live interview workspace
  ├── Transcript/chat drawers
  ├── Feedback screens
  └── Navigation into extracted pages

src/pages/
  ├── InterviewPage.jsx
  ├── OpportunitiesPage.jsx
  └── LearningAgentPage.jsx
```

## AI provider flow

```txt
Application request
        ↓
LLM service selects configured provider
        ↓
Provider call: OpenAI / Anthropic / Groq / Gemini
        ↓
If provider is unavailable, app falls back to demo/offline behavior where supported
        ↓
Response is returned to orchestration/reporting layers
```

## Code execution flow

```txt
Candidate submits code
        ↓
Runtime identifies language adapter
        ↓
Starter/testcase wrapper is prepared
        ↓
Execution runs with timeout and captured stdout/stderr
        ↓
Visible and hidden testcase results are scored
        ↓
Analytics are added to the interview session
```

## Opportunity recommendation flow

```txt
Resume is uploaded or profile data is available
        ↓
Resume analyzer extracts structured candidate profile
        ↓
Matcher compares skills/interests/projects against opportunity metadata
        ↓
Recommendations are scored and returned to the frontend
```

## AI Learning Agent flow

```txt
User adds PDF / URL / GitHub repo / notes
        ↓
Learning loader extracts clean text
        ↓
Chunker splits text and attaches metadata
        ↓
Local deterministic embeddings are stored with chunks
        ↓
Question is embedded and relevant chunks are retrieved
        ↓
CodeVoir LLM service generates a source-grounded answer
        ↓
Frontend shows answer, confidence, and source citations
```

Generation actions reuse the same indexed context to create notes, cheatsheets, flashcards, interview questions, revision plans, project pitches, and mindmaps.

Primary integration points:

1. Dashboard → Learning Agent page.
2. Feedback report → weak topics → learning plan endpoint.
3. Opportunity card → prepare for this opportunity endpoint.
4. GitHub project upload → project interview explanation.
