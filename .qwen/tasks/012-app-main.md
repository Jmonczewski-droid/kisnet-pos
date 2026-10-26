---
allowed: app/main.py, app/api/routes/health.py, tests/test_app.py, tests/conftest.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_app.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. All route modules from earlier tasks exist.
Create:
- app/api/routes/health.py: router with GET /health returning {"status": "OK"}.
- app/main.py: app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json"). Include routers from health, auth, seats, parties, orders, tickets, menu, admin, reports under settings.API_V1_STR (health also at root: GET /health). Mount StaticFiles(directory=<app/static path>) at /static, creating nothing in it. GET / returns FileResponse of app/static/index.html only if that file exists, else 404. Do NOT run seed on startup.
tests/test_app.py: uses the client fixture. Assert /health and /api/v1/health return status OK; /api/v1/menu requires auth (401 without header); openapi JSON served at /api/v1/openapi.json; openapi paths include /api/v1/auth/clock-in, /api/v1/parties, /api/v1/tickets, /api/v1/reports/daily-sales.
Do not create other files.

IMPORTANT: tests/conftest.py has NO client fixture. Add one to tests/conftest.py: a `client` fixture (depends on `db`)
that does `from app.main import app` lazily and returns fastapi.testclient.TestClient(app). Keep the conftest
otherwise unchanged. Add `tests/conftest.py` to this task's allowed list is required for this change: it is allowed.
