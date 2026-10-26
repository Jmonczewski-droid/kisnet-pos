import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db.base import Base, engine, SessionLocal
from app.api.routes.auth import router
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.services.seed import seed_all


@pytest.fixture
def auth_client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/auth")
    return TestClient(app)


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


def test_clock_in_good_login(auth_client, db):
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "employee" in data
    assert data["employee"]["code"] == "SRV1"
    assert "pin_hash" not in data["employee"]


def test_clock_in_wrong_pin(auth_client, db):
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid code or PIN"


def test_clock_in_unknown_code(auth_client, db):
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "UNKNOWN", "pin": "1234"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid code or PIN"


def test_clock_in_again_replaces_open_entry(auth_client, db):
    first = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert first.status_code == 200
    old_token = first.json()["token"]

    second = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert second.status_code == 200
    new_token = second.json()["token"]
    assert new_token != old_token

    assert auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


def test_me_with_token(auth_client, db):
    # Clock in first
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert response.status_code == 200
    token = response.json()["token"]
    
    # Test /me endpoint
    response = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SRV1"


def test_me_without_token(auth_client, db):
    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_clock_out_then_me_401(auth_client, db):
    # Clock in first
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert response.status_code == 200
    token = response.json()["token"]
    
    # Clock out with the token we got from login
    response = auth_client.post("/api/v1/auth/clock-out", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    
    # Try to access /me with the same token - should fail
    response = auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_clock_out_again_after_new_login(auth_client, db):
    # Clock in first
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert response.status_code == 200
    token = response.json()["token"]
    
    # Clock out with the token we got from login
    response = auth_client.post("/api/v1/auth/clock-out", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    
    # Clock in again with same employee
    response = auth_client.post("/api/v1/auth/clock-in", json={"code": "SRV1", "pin": "1234"})
    assert response.status_code == 200
    assert "token" in response.json()

def test_preview_reports_clock_state_without_changing_it(auth_client, db):
    from app.models import TimeEntry

    response = auth_client.post("/api/v1/auth/preview", json={"code": "BAR1", "pin": "1234"})
    assert response.status_code == 200
    assert response.json()["on_clock"] is False
    assert response.json()["employee"]["name"] == "Jessica Moore"
    assert db.query(TimeEntry).count() == 0

    auth_client.post("/api/v1/auth/clock-in", json={"code": "BAR1", "pin": "1234"})
    response = auth_client.post("/api/v1/auth/preview", json={"code": "BAR1", "pin": "1234"})
    assert response.json()["on_clock"] is True


def test_logout_keeps_employee_on_the_clock(auth_client, db):
    from app.models import TimeEntry

    token = auth_client.post("/api/v1/auth/clock-in", json={"code": "KIT1", "pin": "1234"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert auth_client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert auth_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    open_entries = db.query(TimeEntry).filter(TimeEntry.clocked_out_at == None).all()  # noqa: E711
    assert len(open_entries) == 1


def test_sign_in_again_keeps_original_clock_in_time(auth_client, db):
    from app.models import TimeEntry

    auth_client.post("/api/v1/auth/clock-in", json={"code": "KIT1", "pin": "1234"})
    original = db.query(TimeEntry).one().clocked_in_at

    auth_client.post("/api/v1/auth/clock-in", json={"code": "KIT1", "pin": "1234"})
    db.expire_all()

    entries = db.query(TimeEntry).all()
    assert len(entries) == 1
    assert entries[0].clocked_in_at == original
