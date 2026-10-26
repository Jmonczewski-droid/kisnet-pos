---
allowed: app/__init__.py, app/core/*.py, app/db/*.py, tests/test_security.py
verify: venv/bin/python -m pytest -q tests/test_security.py && venv/bin/python -c "from app.db.base import Base, engine, SessionLocal; from app.core.config import settings; from app.core.constants import ALL_SEATS; assert len(ALL_SEATS) == 26"
---
Read .qwen/CONVENTIONS.md first and follow it exactly.
Create: app/__init__.py (empty), app/core/__init__.py (empty), app/core/config.py, app/core/constants.py,
app/core/time.py, app/core/security.py, app/db/__init__.py (empty), app/db/base.py.
config.py must use BaseSettings (pydantic_settings), not BaseModel.
Create tests/test_security.py testing: hash_pin/verify_pin roundtrip (right pin True, wrong pin False),
two hashes of the same pin differ, verify_pin on malformed stored string returns False, hash_token is
deterministic sha256 hex, new_token returns distinct strings of length >= 40.
Do not create any other files.
