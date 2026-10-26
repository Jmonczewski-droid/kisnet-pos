---
allowed: app/schemas/__init__.py, app/schemas/auth.py, app/services/auth.py, app/api/__init__.py, app/api/deps.py, app/api/routes/__init__.py, app/api/routes/auth.py, tests/test_auth.py
verify: venv/bin/python -m pytest -q tests/test_auth.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists.
Create:
- app/schemas/__init__.py (empty), app/schemas/auth.py: ClockInIn(code: str, pin: str), EmployeeOut (from_attributes), TokenOut(token, employee), ClockedOutOut(clocked_out: bool).
- app/services/auth.py: clock_in(session, code, pin) -> (employee, token) raising a custom AuthError(status, detail) for 401/409; clock_out(session, employee); get_employee_by_token(session, token) -> Employee | None; open_entry_for(session, employee_id).
- app/api/__init__.py (empty), app/api/routes/__init__.py (empty), app/api/deps.py: get_current_employee (read Authorization header manually, 401 if missing/invalid), require_roles(*roles) returning a dependency that returns the Employee (admin always allowed; 403 otherwise).
- app/api/routes/auth.py: router with POST /clock-in, POST /clock-out, GET /me. Use get_db from app.db.base. Convert AuthError to HTTPException.
Tests should build their own FastAPI() and include only this router under prefix /api/v1/auth, overriding get_db with the test SessionLocal.
tests/test_auth.py covers: good login returns token and employee without pin_hash; wrong pin 401; unknown code 401; second clock-in while on clock 409; /me with token works; /me without token 401; clock-out then /me 401; clock-out again works after new login.
Do not create other files.

IMPORTANT corrections:
- tests/conftest.py ALREADY provides fixtures db, client and login (login("SRV1") returns headers). Use them. Do NOT modify conftest.py.
- app/core/security.py exposes ONLY hash_pin, verify_pin, new_token, hash_token. There is no decode_token. Tokens are opaque: store hash_token(token) in TimeEntry.token_hash and look it up.
- app/api/deps.py must import Employee (from app.models.employee import Employee) and TimeEntry where used.
- Do not add files outside the allowed list.

ROUTING CONTRACT (fixes 404s seen in the last run):
- app/api/routes/auth.py: `router = APIRouter()` with BARE paths: "/clock-in" (POST), "/clock-out" (POST), "/me" (GET).
  Do NOT put a prefix on the router. The application (app/main.py, written later) mounts it at /api/v1/auth.
- tests/test_auth.py must NOT rely on the shared `client` fixture (app.main does not exist yet). Define in the test
  module its own fixture:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes.auth import router
    @pytest.fixture
    def auth_client(db):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/auth")
        return TestClient(app)
  and use `auth_client` in every test, with the `db` fixture from conftest for data. The get_db dependency uses
  SessionLocal bound to the same temporary engine, so no override is needed.
- Log in with the seed PIN "1234" via auth_client.post("/api/v1/auth/clock-in", json={...}).
