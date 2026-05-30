# Backend application package

`main.py` at the repository backend root is a lightweight Uvicorn entrypoint. The current API implementation lives in `app/server.py` so imports and deployment commands remain stable.

Suggested next split, once the demo is stable:

- `app/api/auth.py`
- `app/api/interview.py`
- `app/api/dashboard.py`
- `app/api/runtime.py`
- `app/api/resume.py`
- `app/api/learning_agent.py`
- `app/services/` for shared business logic
