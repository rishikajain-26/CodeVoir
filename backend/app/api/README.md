# API Routers

This package is reserved for gradually extracting route groups out of `backend/main.py`.

Recommended future routers:

- `auth.py`
- `dashboard.py`
- `interview.py`
- `reports.py`
- `runtime.py`
- `opportunities.py`
- `learning_agent.py`

Keep new features in route modules and register them from `main.py` with `app.include_router(...)`.
