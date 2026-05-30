# Refactor notes

This cleanup keeps the app behavior stable while removing the strongest "single generated file" signals.

## Completed

- Root backend entrypoint is now small: `backend/main.py` imports the real app from `backend/app/server.py`.
- Root frontend entrypoint is now small: `frontend/src/App.jsx` renders `frontend/src/pages/CodeVoirApp.jsx`.
- Existing UI and API behavior are preserved by keeping the large implementation intact behind stable facades.
- Runtime logs, local DB files, and temporary editor/Office files were removed from the packaged project.
- Documentation now explains the architecture, demo path, known limits, and suggested next refactor.

## Why this staged approach

The current app has a large amount of connected state: interview session state, voice controls, code editor telemetry, dashboard data, reports, and opportunity navigation. A deep component-by-component split right before a demo could break UI state or event flow. This pass keeps routes stable and makes the entrypoints professional without changing runtime behavior.

## Recommended next safe splits

Frontend:

1. Move dashboard-only components from `CodeVoirApp.jsx` into `components/dashboard/`.
2. Move feedback report components into `components/feedback/`.
3. Move interview workspace components into `components/interview/`.
4. Move API helpers into `api/client.js`.
5. Move voice/TTS logic into `hooks/useVoiceInterview.js`.

Backend:

1. Move auth endpoints into `app/api/auth.py`.
2. Move dashboard endpoints into `app/api/dashboard.py`.
3. Move interview endpoints into `app/api/interview.py`.
4. Move runtime/code execution helpers into `app/services/runtime_service.py`.
5. Move resume parsing/review into `app/services/resume_service.py`.

This order minimizes breakage because it follows existing feature boundaries.
