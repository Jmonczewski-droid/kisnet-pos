---
allowed: app/services/admin.py
verify: venv/bin/python -m pytest -q tests/test_maintenance.py tests/test_menu_admin.py tests/test_orders.py && venv/bin/python -c "from app.services.admin import update_recipe, deactivate_recipe, reactivate_recipe, archive_recipe, list_recipes, recipe_status"
max_attempts: 4
---
Read .qwen/CONVENTIONS.md (Menu section) first. Then read app/services/admin.py (add_recipe, list_recipes) and app/schemas/admin.py (RecipeIn). Extend app/services/admin.py only; keep code short; no dead code. Do NOT edit anything under .qwen/ and do not write report or log files.

Recipe states, shown as `status`:
- "active": active=True, archived_at None.
- "inactive": active=False, archived_at None. Off the menu; can be reactivated.
- "archived": archived_at set (active=False). Permanent: cannot be edited, reactivated or deleted. Kept for history.
Never delete a menu item. Order items keep their own snapshots, so edits never change past sales.

Services. Errors: raise AdminError(status_code, detail).
- `recipe_status(item) -> str`: "archived" if archived_at, else "active" if active, else "inactive".
- `update_recipe(session, recipe_id, data) -> MenuItem`: 404 "Recipe not found" if missing. 409 "Archived recipes cannot be changed" if archived. 409 "A recipe with this name already exists" if another item has the same stripped name (filter id != recipe_id). Set name (stripped), category, price_cents. Replace ingredients: `item.recipe_lines.clear()` then append new RecipeLine objects, as add_recipe does. Commit, refresh, return.
- `deactivate_recipe(session, recipe_id)`: 404 if missing; 409 "Archived recipes cannot be changed" if archived; 409 "Already inactive" if not active. Set active=False, commit.
- `reactivate_recipe(session, recipe_id)`: 404 if missing; 409 "Archived recipes cannot be reactivated" if archived; 409 "Already active" if active. Set active=True, commit.
- `archive_recipe(session, recipe_id)`: 404 if missing; 409 "Already archived" if archived. Set active=False and archived_at = utcnow(), commit.
- `list_recipes(session, include_archived: bool = False)`: leave out archived rows unless include_archived. Each dict gains "status": recipe_status(item). Keep every existing key and the ordering.
- Keep add_recipe's duplicate-name check unchanged. An archived name still blocks a new recipe with that name.
