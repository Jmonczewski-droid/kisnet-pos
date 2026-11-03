---
allowed: app/api/routes/admin.py
verify: venv/bin/python -m pytest -q tests/test_maintenance.py tests/test_menu_admin.py && venv/bin/python -c "import app.api.routes.admin"
max_attempts: 4
---
Read app/api/routes/admin.py and app/services/admin.py (the functions update_employee, deactivate_employee, reactivate_employee, archive_employee, roster, employee_status, AdminError already exist; do not change the service). Read .qwen/CONVENTIONS.md (Auth section) only if needed. Keep code short. Do NOT edit anything under .qwen/ and do not write report or log files. Only app/api/routes/admin.py changes.

Changes, all admin-only via require_roles("admin"):
- GET /admin/roster: add query parameter `include_archived: bool = False`, pass it to roster(db, include_archived).
- PATCH /admin/employees/{employee_id}: body EmployeeEdit (import it from app.schemas.admin). Calls update_employee. Returns the single roster row for that employee.
- POST /admin/employees/{employee_id}/deactivate, /reactivate, /archive: call the matching service function. Return the single roster row.
- For the single row: `next(row for row in roster(db, include_archived=True) if row["id"] == employee_id)`.
- Wrap each service call in try/except AdminError as e: raise HTTPException(status_code=e.status_code, detail=e.detail), as create_recipe does.

Verify only with the commands in the header. Do not add test files.
