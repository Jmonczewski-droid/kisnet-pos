---
allowed: app/models/employee.py, app/models/menu.py, alembic/versions/0003_archive_status.py
verify: venv/bin/python -m pytest -q && rm -f /tmp/kisnet_verify_mig.db && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic upgrade head && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic check && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic downgrade 0002 && DATABASE_URL=sqlite:////tmp/kisnet_verify_mig.db venv/bin/alembic upgrade head && rm -f /tmp/kisnet_verify_mig.db
max_attempts: 4
---
Read .qwen/CONVENTIONS.md (Stack/rules section) first. Follow the existing style of alembic/versions/0002_employee_profile_and_shift_position.py exactly for the migration.

Add an archive timestamp to two tables. Nothing else changes.

1. app/models/employee.py: add to class Employee
   `archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # set when the employee is archived (terminated); never cleared`
   Import datetime from datetime and DateTime from sqlalchemy. Keep every existing field.

2. app/models/menu.py: add to class MenuItem the same column:
   `archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # set when the recipe is retired; never cleared`
   Import datetime and DateTime. Keep every existing field and relationship.

3. alembic/versions/0003_archive_status.py: revision '0003', down_revision '0002'. upgrade(): batch_alter_table on 'employees' adds sa.Column('archived_at', sa.DateTime(), nullable=True); batch_alter_table on 'menu_items' adds the same column. downgrade() drops both columns (batch_alter_table).

Do not change any other file. Do not add tests (later tasks add them).
