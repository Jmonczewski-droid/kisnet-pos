---
allowed: app/static/app.js, app/static/styles.css
verify: node --check app/static/app.js && grep -q 'emp-edit' app/static/app.js && grep -q 'rec-edit' app/static/app.js && grep -q 'emp-archive' app/static/app.js && grep -q 'rec-archive' app/static/app.js
max_attempts: 4
---
Read the file first. The relevant code is app/static/app.js: renderEmployees, loadRoster, showAddEmployeeForm, saveEmployee, renderRecipes, addIngredientRow, saveRecipe, loadRecipeList (System > Employees and System > Recipes). Helpers already in the file: api(path, options), escapeHtml, roleLabel, isoDay, POSITION_OPTIONS. Vanilla JS, no build step. Keep code short; reuse the existing form code for edit mode rather than duplicating it.

Backend endpoints this UI calls (all admin only; they exist or are being added in the same run):
- GET /api/v1/admin/roster?include_archived=true|false → rows with id, code, name, positions (list), address, dob, hire_date, ssn, active, status ("active" | "inactive" | "archived"), on_clock, week_hours.
- POST /api/v1/admin/employees (exists) — add.
- PATCH /api/v1/admin/employees/{id} — body: any of name, address, dob, hire_date, positions, pin.
- POST /api/v1/admin/employees/{id}/deactivate | /reactivate | /archive.
- GET /api/v1/admin/recipes?include_archived=true|false → rows with id, name, category, price_cents, ingredients [{ingredient, qty, unit}], status.
- POST /api/v1/admin/recipes (exists) — add.
- PUT /api/v1/admin/recipes/{id} — body: name, category, price_cents, ingredients (same as add).
- POST /api/v1/admin/recipes/{id}/deactivate | /reactivate | /archive.

Employees screen (renderEmployees / loadRoster):
- Add a "Show archived" checkbox (id emp-show-archived). Reloading uses include_archived to match it.
- Table gets a Status column and an Actions column. Status shows the status value. Actions per row:
  - Edit (class `emp-edit`, data-id): opens the same form prefilled with that row (name, address, dob, hire date, positions checkboxes ticked). PIN field is blank with the label "PIN (leave blank to keep)". Button text "Save changes" → PATCH. Only the fields the form has are sent; a blank PIN is not sent.
  - Deactivate (class `emp-deactivate`) for active rows; Reactivate (class `emp-reactivate`) for inactive rows.
  - Archive (class `emp-archive`) for active and inactive rows. Ask with window.confirm("Archive X? They will be removed from the roster and cannot log in. The record is kept.") first.
  - No actions for archived rows (show "Archived").
- After any action, reload the roster and show a message in emp-status. Errors from the server go to alert with the detail text (the api helper's error message).

Recipes screen (renderRecipes / loadRecipeList):
- Add a "Show archived" checkbox (id rec-show-archived). The list uses include_archived to match.
- Table gets a Status column and an Actions column with the same rules: Edit (class `rec-edit`, data-id) loads that recipe into the existing add form (name, category, price, ingredient rows), with a "Save changes" button that does PUT and a "Cancel" button that clears edit mode and restores the add form. Deactivate (class `rec-deactivate`), Reactivate (class `rec-reactivate`), Archive (class `rec-archive`, with window.confirm).
- Keep the existing validation in saveRecipe for both add and edit.

Use event delegation on the list boxes (one listener each) rather than binding per button. Escape all user text with escapeHtml. Add minimal CSS in app/static/styles.css only if needed (for example a muted style for archived rows).

Do not change any other file.
