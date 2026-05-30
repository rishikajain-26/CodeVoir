# Known Limitations

These limitations are documented so the demo is transparent and easier to improve.

## Current limitations

- `backend/main.py` and `frontend/src/App.jsx` are large legacy composition files. New features should be added as separate modules/pages rather than expanding these files further.
- Browser speech recognition works best in Chrome and may require microphone permission.
- Code execution is suitable for controlled demos. Production deployment should enforce Docker isolation, CPU limits, memory limits, network restrictions, and filesystem restrictions.
- LLM availability depends on configured API keys and provider quotas.
- Offline/demo fallback responses are intentionally present so the app remains usable when model providers are unavailable.
- Large resumes or unusual PDF formatting may produce incomplete extraction.
- Opportunity recommendations depend on the available crawler/source data and profile extraction quality.
- SQLite is used for local persistence by default. PostgreSQL is recommended for multi-user deployment.

## Planned improvements

- Move API sections from `backend/main.py` into dedicated routers.
- Split `frontend/src/App.jsx` into smaller page and component files.
- Add the AI Learning Agent as a separate RAG module.
- Persist user-specific generated notes, flashcards, and learning plans.
- Add stronger sandboxing for all code execution.
- Add richer source citations and confidence scoring for AI-generated explanations.
