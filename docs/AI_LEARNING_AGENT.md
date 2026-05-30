# AI Learning Agent

The AI Learning Agent is now integrated into CodeVoir as a source-grounded study and interview-preparation module.

## What it does

Users can add learning sources from:

- PDF files
- Documentation or article URLs
- GitHub repositories
- Plain-text notes

The agent then:

- extracts clean text from the source,
- splits it into chunks,
- creates deterministic local embeddings,
- retrieves relevant chunks for each question,
- generates answers through CodeVoir's existing LLM service,
- shows source citations and confidence,
- generates revision material such as notes, flashcards, interview questions, project pitches, mindmaps, and revision plans.

## Why this design

The module intentionally uses local embeddings so the retrieval pipeline works even without a paid embedding API. If Gemini/OpenAI/Groq/Anthropic keys are configured, CodeVoir's existing `llm_service` improves the final explanations and generated material. If no provider is configured, the agent still returns retrieval-only fallback answers.

## Backend routes

All endpoints are mounted under:

```txt
/api/learning
```

Important endpoints:

```txt
GET  /api/learning/health
GET  /api/learning/sources
POST /api/learning/sources/text
POST /api/learning/sources/pdf
POST /api/learning/sources/url
POST /api/learning/sources/github
POST /api/learning/chat
POST /api/learning/generate
POST /api/learning/from-session/{session_id}
POST /api/learning/prepare-opportunity
```

## Frontend

The page lives at:

```txt
frontend/src/pages/LearningAgentPage.jsx
```

It is accessible from the dashboard through the **Learning Agent** button.

The UI contains:

- source ingestion panel,
- knowledge-base selector,
- RAG chat with modes,
- strict-source toggle,
- generated output panel,
- Markdown export.

## Storage

Generated local learning-agent data is written to:

```txt
backend/app/data/learning_agent/
```

This is a runtime artifact and should not be committed.

## Integration points

Implemented now:

- dashboard → Learning Agent page,
- CodeVoir LLM service reuse,
- learning-agent backend router mounted in the main API,
- source ingestion + RAG chat + generated revision material.

Prepared backend endpoints for next UI polish:

- feedback report → `/api/learning/from-session/{session_id}` for weak-area revision plans,
- opportunity card → `/api/learning/prepare-opportunity` for opportunity-specific prep.

## Visual polish update

The Learning Agent UI now keeps citations out of the main answer flow. Sources are grouped in a compact Evidence panel on the right, so repeated chunks from the same PDF or URL do not fill the center of the page.

Generated material is rendered visually:

- Notes become section cards.
- Flashcards become reveal cards.
- Mind maps become a concept tree with optional Mermaid flow text.
- Feature actions are placed in the center workbench.
