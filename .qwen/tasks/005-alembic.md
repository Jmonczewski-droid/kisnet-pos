---
allowed: alembic.ini, alembic/**
verify: rm -f /tmp/kisnet_verify_mig.db && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic upgrade head && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic check && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic downgrade base && rm -f /tmp/kisnet_verify_mig.db
---
Read .qwen/CONVENTIONS.md first and follow it exactly.
STRICT: create ONLY the files in the allowed list. Do not create markdown or summary files. Do not import sqlmodel or any package not in requirements.txt.
Set up Alembic (alembic.ini exists at repo root with script_location = alembic; leave its sqlalchemy.url line
alone, env.py overrides it from settings).
Create: alembic/env.py (sys.path insert of repo root; set sqlalchemy.url from app.core.config.settings.DATABASE_URL;
target_metadata = Base.metadata from app.db.base after importing app.models so all tables are registered;
render_as_batch=True; online and offline modes), alembic/script.py.mako (standard Alembic template),
alembic/versions/0001_initial.py.

Migration rules (so `alembic check` reports no differences from the models):
- Read every model file in app/models/ first and mirror its columns exactly: types, nullable, defaults only where
  server-side (the models use Python defaults, so do not add server_default), foreign keys with ondelete as declared.
- Do NOT use sa.UniqueConstraint in create_table for columns the models mark unique. Instead, for each column the
  model declares with index=True, create the index with op.create_index(op.f("ix_<table>_<column>"), table, [col],
  unique=<True if the model says unique>). Include unique=True ones too (e.g. ix_employees_code, ix_employees_number,
  ix_menu_items_name, ix_time_entries_token_hash). Match the model's index names exactly.
- Revision id "0001", down_revision None. downgrade drops indexes first, then tables in reverse dependency order.
Iterate by running the verify command; read the autogenerate diffs and fix the migration (not the models).
