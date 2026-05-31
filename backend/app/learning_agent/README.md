# CodeVoir AI Learning Agent

This module powers the source-grounded learning workflow inside CodeVoir.

It supports:

- PDF upload and page-level indexing.
- Documentation/article URL ingestion.
- GitHub repository scanning for important source files.
- Plain-text notes ingestion.
- Local deterministic embeddings for zero-cost retrieval.
- RAG chat with source citations and confidence labels.
- Notes, summaries, cheatsheets, flashcards, interview questions, revision plans, project pitches, and flowcharts.
- Interview-session weak-area revision planning.
- Opportunity preparation plans.

The module intentionally uses CodeVoir's existing `llm_service` so Gemini/OpenAI/Groq/Anthropic fallback behavior remains centralized. Retrieval still works without API keys through local hashed embeddings; external LLM keys improve answer quality.
