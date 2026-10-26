import os
import tempfile

# Must run before any app module is imported: the engine is built from DATABASE_URL at import time.
_TMPDIR = tempfile.mkdtemp(prefix="kisnet-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient

from app.db.base import Base, SessionLocal, engine  # noqa: E402
from app.services.seed import seed_all  # noqa: E402
from app.main import app  # noqa: E402

assert "kisnet-test-" in str(engine.url.database), "tests must never use a non-temporary database"


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    seed_all(session)
    session.close()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    return TestClient(app)


@pytest.fixture
def login(db):
    """Clock an employee in via the auth service (no HTTP, so it works before app.main exists)."""
    from app.services.auth import clock_in

    cache = {}

    def _login(code: str, pin: str = "1234") -> dict:
        if code not in cache:
            _, token = clock_in(db, code, pin)
            cache[code] = {"Authorization": f"Bearer {token}"}
        return cache[code]

    return _login
