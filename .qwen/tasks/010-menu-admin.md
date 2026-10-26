---
allowed: app/services/admin.py, app/api/routes/menu.py, app/api/routes/admin.py, tests/test_menu_admin.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_menu_admin.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists; services/menu_import.py exists.
Create:
- app/services/admin.py: list_employees(session, role: str | None) (active employees, sorted by name); on_clock(session) -> list of dicts per conventions; force_clock_out(session, employee_id) (404 if none open; sets clocked_out_at = utcnow()).
- app/api/routes/menu.py: router. GET /menu (auth, optional category query, active items sorted by name). GET /menu/export (admin, PlainTextResponse media_type text/csv). POST /menu/import (admin, raw body via `await request.body()` decoded utf-8; call import_menu; return {"items", "recipe_lines"}; ValueError -> 422 with message).
- app/api/routes/admin.py: router. GET /employees?role= (any authenticated user; EmployeeOut list via list_employees). GET /admin/on-clock (admin). POST /admin/clock-out/{employee_id} (admin, returns {"clocked_out": true}).
Use require_roles("admin") for admin routes; get_current_employee for the rest.
tests/test_menu_admin.py: FastAPI() including menu and admin routers under /api/v1 with get_db override. Cover: GET /menu?category=cold includes Caesar Salad with price_cents 1000; non-admin (SRV1 login) gets 403 on /menu/export; export starts with the header line name,type; POST /menu/import with a small valid CSV (raw body, content-type text/csv) returns counts; bad CSV returns 422; GET /employees?role=server lists SRV1; on-clock lists ADM1 after login; clock-out via admin route makes on-clock empty of that user; clock-out of an employee not on clock -> 404.
Do not create other files.

IMPORTANT (same rules as the other router tasks):
- Do NOT edit app/main.py or app/api/routes/__init__.py. Do NOT import app.main or modules not in this task.
- Routers use BARE paths; the app is assembled later under /api/v1.
- tests/conftest.py has NO client fixture. In this test module define a fixture named `client`:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    @pytest.fixture
    def client(db):
        app = FastAPI()
        app.include_router(<router>, prefix="/api/v1")   # include every router this test needs
        return TestClient(app)
  Use the `db` and `login` fixtures from conftest.

EXACT PATHS: menu.py: "/menu" (GET), "/menu/export" (GET), "/menu/import" (POST). admin.py: "/employees" (GET),
"/admin/on-clock" (GET), "/admin/clock-out/{employee_id}" (POST). Test app includes menu and admin routers.
Do NOT edit tests/conftest.py.
