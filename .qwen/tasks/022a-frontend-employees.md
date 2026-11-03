---
allowed: app/static/app.js, app/static/styles.css
verify: node --check app/static/app.js && grep -q 'emp-edit' app/static/app.js && grep -q 'emp-archive' app/static/app.js && grep -q 'emp-show-archived' app/static/app.js
max_attempts: 1
---
The file is app/static/app.js, relative to the repo root (KISnet-POS). Read it with that exact path. Do not look for other test files; there are none for the frontend. Vanilla JS, no build step. Keep code short.

RULES: Edit only app/static/app.js and app/static/styles.css. Do NOT create or edit anything under .qwen/ (no report, no logs, no notes).

Scope: ONLY the Employees screen. Do not touch renderRecipes or the recipe functions.

Relevant existing code: renderEmployees, loadRoster, showAddEmployeeForm, saveEmployee, and the constant POSITION_OPTIONS. Helpers already in the file: api(path, options), escapeHtml, roleLabel, isoDay.

Backend endpoints (admin only; they exist now):
- GET /api/v1/admin/roster?include_archived=true|false → rows with id, code, name, positions (list), address, dob, hire_date, ssn, active, status ("active" | "inactive" | "archived"), on_clock, week_hours.
- POST /api/v1/admin/employees (exists) — add.
- PATCH /api/v1/admin/employees/{id} — body: any of name, address, dob, hire_date, positions, pin.
- POST /api/v1/admin/employees/{id}/deactivate | /reactivate | /archive.

Changes:
1. A "Show archived" checkbox (id emp-show-archived) above the roster. loadRoster passes include_archived=true when it is checked. Re-load when it changes.
2. The table gets a Status column and an Actions column. Actions per row:
   - Edit: button with class emp-edit and data-id. Opens the same form as Add, prefilled from that row (name, address, dob, hire date, position checkboxes ticked). The PIN field is blank with the label "PIN (leave blank to keep)". The save button says "Save changes" and does PATCH. Send only the fields the form has; send pin only if it is not blank.
   - Deactivate (class emp-deactivate) on active rows; Reactivate (class emp-reactivate) on inactive rows.
   - Archive (class emp-archive) on active and inactive rows. Call window.confirm("Archive NAME? They will be removed from the roster and cannot log in. The record is kept.") first.
   - Archived rows show "Archived" and no buttons.
3. After any action, reload the roster and show the result in emp-status. Server errors go to alert with the error message.
4. Use one event listener on the roster box (event delegation) for the action buttons, not one per button.
5. Escape all user text with escapeHtml. Add CSS to styles.css only if needed (for example a muted style for archived rows).

Do not change any other function or file.
