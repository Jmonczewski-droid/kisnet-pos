---
allowed: tests/test_employee_lifecycle.py
verify: venv/bin/python -m pytest -q tests/test_employee_lifecycle.py
max_attempts: 4
---
Read tests/test_maintenance.py (the api fixture, _bearer and _new_employee helpers) and tests/conftest.py (db and login fixtures; there is no client fixture). Read app/api/routes/admin.py and app/services/admin.py to see the behaviour under test.

RULES: Edit only tests/test_employee_lifecycle.py. Do not edit app code. Do NOT create or edit anything under .qwen/ (no report.md, no logs, no notes). If a test fails because the app code is wrong, leave the app code alone and say so in your final message.

Each route that changes an employee returns ONE roster row. Its keys are: id, code, name, positions (a list), address, dob, hire_date, ssn, active, status, archived_at, on_clock, clocked_in_at, week_hours. There is NO "role" key in that row. Check `positions` instead; for "role follows the first position", assert positions[0] == "bartender" after changing positions to ["bartender", "server"].

Create tests/test_employee_lifecycle.py with the api fixture from tests/test_maintenance.py (auth, admin and menu routers). Test:
- PATCH name and positions: response code and ssn unchanged; name updated; positions updated (see above).
- PATCH pin: old PIN gets 401 at clock-in, new PIN works (200).
- Deactivate: clock-in with that code returns 401; GET /api/v1/employees does not list them; roster row status == "inactive".
- Deactivate while on the clock: after deactivating, GET /api/v1/admin/on-clock does NOT contain their id (assert absence, not presence).
- Deactivate, then reactivate: clock-in works again (200).
- Archive: roster row status == "archived"; absent from the default GET /api/v1/admin/roster; present with ?include_archived=true; PATCH returns 409; reactivate returns 409; clock-in returns 401.
- Deactivate or archive while they are the server on an open party returns 409. Create the party by inserting app.models.party.Party through the db session (read app/models/party.py for required columns; closed_at None; server_id = the employee's id).
- A non-admin (login("SRV1")) gets 403 on PATCH and on deactivate, reactivate, archive.
- PATCH on an unknown id returns 404.
