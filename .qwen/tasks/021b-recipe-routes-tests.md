---
allowed: app/api/routes/admin.py, tests/test_recipe_lifecycle.py
verify: venv/bin/python -m pytest -q tests/test_recipe_lifecycle.py tests/test_maintenance.py tests/test_menu_admin.py
max_attempts: 3
---
Read app/api/routes/admin.py, app/services/admin.py, and tests/test_maintenance.py (api fixture and recipe dict shape). conftest provides db and login fixtures; there is no client fixture.

RULES: Edit only the two allowed files. Do NOT create or edit anything under .qwen/ (no report, no logs, no notes). Do not change app/services/admin.py. If a test fails because the service is wrong, say so in your final message and leave the service alone.

STEP 1 — imports. In app/api/routes/admin.py the existing `from app.services.admin import (...)` block does NOT yet import the recipe functions. Add these names to that import: update_recipe, deactivate_recipe, reactivate_recipe, archive_recipe. Also add `list_recipes` if it is not already there. Without these imports the routes raise NameError.

STEP 2 — routes (all require_roles("admin")). Wrap each service call: `except AdminError as e: raise HTTPException(status_code=e.status_code, detail=e.detail)`.
- GET /admin/recipes: add query parameter `include_archived: bool = False`; return list_recipes(db, include_archived=include_archived).
- PUT /admin/recipes/{recipe_id}: body RecipeIn. Call update_recipe(db, recipe_id, data). Then return the dict for that id from list_recipes(db, include_archived=True) — this dict has keys id, name, category, price_cents, ingredients, status. Use `next(r for r in list_recipes(db, include_archived=True) if r["id"] == recipe_id)`.
- POST /admin/recipes/{recipe_id}/deactivate, /reactivate, /archive: call the matching service function, then return the same single dict as PUT.
- Do not rename or change the existing POST /admin/recipes route.

STEP 3 — tests/test_recipe_lifecycle.py. Copy the api fixture from tests/test_maintenance.py. Find a seeded recipe id via GET /api/v1/admin/recipes. Add new recipes with the existing POST /api/v1/admin/recipes (201). Test:
- PUT changes price and ingredients; GET /api/v1/menu?category=... shows the new price; the ingredient list is replaced, not appended (read ingredients from the PUT response, which has the key "ingredients").
- PUT renaming to another existing recipe's name → 409.
- Deactivate: gone from GET /api/v1/menu; status "inactive"; reactivate brings it back.
- Archive: gone from /menu and from default GET /admin/recipes; present with ?include_archived=true, status "archived"; PUT → 409; reactivate → 409; deactivate → 409; archive again → 409.
- Adding a new recipe with an archived item's name → 409.
- Non-admin (login("SRV1")) gets 403 on PUT, deactivate, reactivate, archive.
- PUT on an unknown id → 404.
