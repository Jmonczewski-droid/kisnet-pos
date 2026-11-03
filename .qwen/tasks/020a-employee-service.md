---
allowed: app/schemas/admin.py, app/services/admin.py
verify: venv/bin/python -m pytest -q tests/test_maintenance.py tests/test_menu_admin.py tests/test_auth.py && venv/bin/python -c "from app.services.admin import update_employee, deactivate_employee, reactivate_employee, archive_employee, roster, employee_status; from app.schemas.admin import EmployeeEdit"
max_attempts: 4
---
Read .qwen/CONVENTIONS.md (Stack/rules, Auth sections) first. Then read app/services/admin.py and app/schemas/admin.py. Extend them; keep code short; no dead code. Do NOT edit anything under .qwen/ and do not write report or log files. Only the two allowed files change.

Employee states, shown as `status`:
- "active": active=True, archived_at None.
- "inactive": active=False, archived_at None. Cannot clock in; can be reactivated.
- "archived": archived_at set (active=False). Permanent: cannot be edited, reactivated or deleted. Records kept.
Never delete an employee row.

Schema (app/schemas/admin.py): `EmployeeEdit` with every field optional: name (min_length 1), address, dob (date), hire_date (date), positions (list of str, min 1 when given), pin (str, min_length 4 when given). Positions use the same known-positions check as EmployeeIn: move that check into a module-level function and use it in both classes.

Services (app/services/admin.py). Errors: raise AdminError(status_code, detail).
- `employee_status(employee) -> str`: "archived" if archived_at, else "active" if active, else "inactive".
- `update_employee(session, employee_id, data) -> Employee`: 404 "Employee not found" if missing. 409 "Archived employees cannot be changed" if archived. Apply only the fields sent (`data.model_dump(exclude_unset=True)`). name is stripped. pin, if sent, sets pin_hash = hash_pin(pin). positions, if sent: order them by ROLES as add_employee does; role = first; positions = comma-joined string. code, number and ssn_last never change. Commit, refresh, return.
- `_leave_job(session, employee)` (used by deactivate and archive, does not commit): if an open TimeEntry exists (clocked_out_at IS NULL) set its clocked_out_at = utcnow(). If any Party has server_id == employee.id and closed_at IS NULL, raise AdminError(409, "Close or move this employee's open tables first").
- `deactivate_employee(session, employee_id) -> Employee`: 404 if missing; 409 "Archived employees cannot be changed" if archived; 409 "Already inactive" if not active. Call _leave_job, set active=False, commit, return.
- `reactivate_employee(session, employee_id) -> Employee`: 404 if missing; 409 "Archived employees cannot be reactivated" if archived; 409 "Already active" if active. Set active=True, commit, return.
- `archive_employee(session, employee_id) -> Employee`: 404 if missing; 409 "Already archived" if archived. Call _leave_job, set active=False and archived_at = utcnow(), commit, return.
- `roster(session, include_archived: bool = False)`: leave out archived rows unless include_archived. Each row gains "status": employee_status(employee) and "archived_at" (isoformat string or None). Keep every existing key.
- Leave list_employees unchanged.

Do not touch routes or tests in this task.
