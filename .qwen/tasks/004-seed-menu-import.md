---
allowed: app/services/__init__.py, app/services/seed.py, app/services/menu_import.py, tests/conftest.py, tests/__init__.py, tests/test_menu_import.py
verify: venv/bin/python -m pytest -q tests/test_menu_import.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly.
STRICT: create ONLY the files in the allowed list. Do NOT create README, summary, IMPLEMENTATION, or any markdown files.
Create app/services/__init__.py (empty), app/services/menu_import.py, app/services/seed.py.

menu_import.py:
- parse_menu_csv(text) -> list[dict]: csv.DictReader on text; headers name,type,ingredient,qty,unit,sales.
  Strip whitespace from every field. type maps case-insensitively to a CATEGORIES value (Bar->bar,
  Appetizers->appetizers, Hot->hot, Cold->cold). Raise ValueError (message includes line number) for: unknown type,
  any missing/empty field, qty <= 0, or sales that differ between rows with the same name.
  Parse qty as float and sales as Decimal(string) (never Decimal(float)). Each dict has keys
  name, category, ingredient, qty, unit, price_cents (int = int(sales * 100)).
- import_menu(session, text) -> (item_count, recipe_line_count): parse; group rows by name; for each name upsert
  a MenuItem (set category and price_cents); DELETE its existing recipe_lines then add one RecipeLine per row.
  item_count = number of distinct items processed (created or updated). recipe_line_count = number of rows.
  Call session.commit() at the end. Use session.query / select as you prefer.
- export_menu_csv(session) -> str: header row name,type,ingredient,qty,unit,sales; one row per recipe line for each
  MenuItem ordered by item name then recipe line id; type = CATEGORY_LABELS[category]; sales = f"{price_cents/100:.2f}".

seed.py:
- seed_all(session): if no Employee rows, insert the 5 seed employees from the conventions with pin_hash = hash_pin("1234"),
  location_id 1, active True. If no MenuItem rows, read app/seed/menu.csv (path relative to the seed.py file) and call
  import_menu. Idempotent. Commit.

tests/conftest.py: exactly per the "Tests contract" section (DATABASE_URL env set before importing app code; fixtures
db, client, login; client imports app.main lazily; app.main does not exist yet, so only the db fixture is used here).
tests/__init__.py: empty.

tests/test_menu_import.py must contain ONLY these tests:
1. parse_menu_csv raises ValueError for a row with type "Dessert".
2. parse_menu_csv on a 3-row CSV for "Caesar Salad" (type Cold, sales 10.00) returns 3 dicts, all category "cold", price_cents 1000.
3. Using the db fixture: import_menu on the seed file contents (read app/seed/menu.csv) returns recipe_line_count equal to the number of data rows in that file (count them in the test with csv), and the MenuItem named "Caesar Salad" has category "cold", price_cents 1000 and exactly 3 recipe_lines.
4. export_menu_csv(db) round-trips: parse_menu_csv(export) returns the same number of rows as the data rows in app/seed/menu.csv (after the import in test 3; import the seed first in this test).
5. seed_all on an empty db creates exactly 5 employees with codes HOST1,SRV1,KIT1,BAR1,ADM1 (sorted comparison); calling seed_all again keeps 5.
Do not hardcode the total item count.
