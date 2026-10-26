---
allowed: app/models/__init__.py, app/models/employee.py, app/models/time_entry.py, app/models/menu.py, tests/test_models_core.py
verify: venv/bin/python -m pytest -q tests/test_models_core.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. app/db/base.py already exists: do NOT edit it (it is out of scope); import Base from it.
Create the models in app/models/employee.py, app/models/time_entry.py, app/models/menu.py exactly as the
"app/models/" section describes. Do NOT create party.py or order.py yet.
app/models/__init__.py imports Employee, TimeEntry, MenuItem, RecipeLine (only these for now).
tests/test_models_core.py: use a fresh in-memory sqlite engine (create_engine("sqlite://")) bound to a
sessionmaker, Base.metadata.create_all on that engine, insert an Employee, a TimeEntry, a MenuItem with two
RecipeLines, then query them back and assert values and that deleting the MenuItem deletes its recipe lines.
Do not use conftest.py (it does not exist yet). Do not create any other files.
