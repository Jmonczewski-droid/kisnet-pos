---
allowed: app/static/app.js, app/static/styles.css
verify: node --check app/static/app.js && grep -q 'rec-edit' app/static/app.js && grep -q 'rec-archive' app/static/app.js && grep -q 'rec-show-archived' app/static/app.js
max_attempts: 1
---
The file is app/static/app.js, relative to the repo root (KISnet-POS). Read it with that exact path. Do not look for other test files; there are none for the frontend. Vanilla JS, no build step. Keep code short.

RULES: Edit only app/static/app.js and app/static/styles.css. Do NOT create or edit anything under .qwen/ (no report, no logs, no notes).

Scope: ONLY the Recipes screen. Do not touch renderEmployees or the employee functions.

Relevant existing code: renderRecipes, addIngredientRow, saveRecipe, loadRecipeList. Helpers already in the file: api(path, options), escapeHtml, roleLabel.

Backend endpoints (admin only; they exist now):
- GET /api/v1/admin/recipes?include_archived=true|false → rows with id, name, category, price_cents, ingredients [{ingredient, qty, unit}], status ("active" | "inactive" | "archived").
- POST /api/v1/admin/recipes (exists) — add.
- PUT /api/v1/admin/recipes/{id} — body: name, category, price_cents, ingredients (same shape as add).
- POST /api/v1/admin/recipes/{id}/deactivate | /reactivate | /archive.

Changes:
1. A "Show archived" checkbox (id rec-show-archived) above the list. loadRecipeList passes include_archived=true when checked. Re-load when it changes.
2. The list table gets a Status column and an Actions column. Actions per row:
   - Edit: button with class rec-edit and data-id. Loads that recipe into the existing add form: name, category select, price (dollars), and one ingredient row per ingredient. The save button changes to "Save changes" and does PUT. A "Cancel" button leaves edit mode, clears the form and restores the "Save recipe" button and an empty add form.
   - Deactivate (class rec-deactivate) on active rows; Reactivate (class rec-reactivate) on inactive rows.
   - Archive (class rec-archive). Call window.confirm("Archive NAME? It will be removed from the menu for good. Past sales are kept.") first.
   - Archived rows show "Archived" and no buttons.
3. Keep the validation in saveRecipe for both add and edit (name, price, each ingredient needs qty and unit). Add and edit both report results in rec-status.
4. After any action, reload the list. Server errors go to rec-status with the error message.
5. Use one event listener on the list box (event delegation) for the action buttons.
6. Escape all user text with escapeHtml. Add CSS to styles.css only if needed (for example a muted style for archived rows).

Do not change any other function or file.
