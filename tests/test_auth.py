import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.auth import router
from app.models import Employee, TimeEntry


@pytest.fixture
def auth_client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/auth")
    return TestClient(app)


def _post(client, path, code="SRV1", pin="1234", headers=None):
    return client.post(f"/api/v1/auth/{path}", json={"code": code, "pin": pin}, headers=headers or {})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_clock_in_does_not_log_in(auth_client, db):
    response = _post(auth_client, "clock-in")
    assert response.status_code == 200
    assert response.json()["employee"]["code"] == "SRV1"
    assert "token" not in response.json()
    assert db.query(TimeEntry).count() == 1


def test_wrong_pin_and_unknown_code_are_401(auth_client):
    assert _post(auth_client, "clock-in", pin="wrong").status_code == 401
    assert _post(auth_client, "clock-in", code="UNKNOWN").status_code == 401
    assert _post(auth_client, "login", pin="wrong").status_code == 401


def test_clock_in_twice_is_409(auth_client):
    assert _post(auth_client, "clock-in").status_code == 200
    response = _post(auth_client, "clock-in")
    assert response.status_code == 409
    assert response.json()["detail"] == "Already clocked in"


def test_login_requires_being_on_the_clock(auth_client):
    response = _post(auth_client, "login")
    assert response.status_code == 409
    assert response.json()["detail"] == "Not clocked in. Clock in first."


def test_login_after_clock_in_returns_working_token(auth_client):
    _post(auth_client, "clock-in")
    token = _post(auth_client, "login").json()["token"]
    response = auth_client.get("/api/v1/auth/me", headers=_bearer(token))
    assert response.status_code == 200
    assert response.json()["code"] == "SRV1"
    assert "pin_hash" not in response.json()


def test_me_without_token_is_401(auth_client):
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_logging_in_again_replaces_token_and_keeps_clock_time(auth_client, db):
    _post(auth_client, "clock-in")
    original = db.query(TimeEntry).one().clocked_in_at
    first = _post(auth_client, "login").json()["token"]
    second = _post(auth_client, "login").json()["token"]

    assert first != second
    assert auth_client.get("/api/v1/auth/me", headers=_bearer(first)).status_code == 401
    assert auth_client.get("/api/v1/auth/me", headers=_bearer(second)).status_code == 200
    db.expire_all()
    entries = db.query(TimeEntry).all()
    assert len(entries) == 1 and entries[0].clocked_in_at == original


def test_logout_keeps_employee_on_the_clock(auth_client, db):
    _post(auth_client, "clock-in")
    token = _post(auth_client, "login").json()["token"]

    assert auth_client.post("/api/v1/auth/logout", headers=_bearer(token)).status_code == 200
    assert auth_client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401
    assert _post(auth_client, "preview").json()["on_clock"] is True
    assert _post(auth_client, "login").status_code == 200


def test_clock_out_ends_shift_and_login(auth_client, db):
    _post(auth_client, "clock-in")
    token = _post(auth_client, "login").json()["token"]

    assert auth_client.post("/api/v1/auth/clock-out", headers=_bearer(token)).status_code == 200
    assert auth_client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401
    assert _post(auth_client, "login").status_code == 409


def test_clock_out_again_after_new_shift(auth_client, db):
    _post(auth_client, "clock-in")
    token = _post(auth_client, "login").json()["token"]
    auth_client.post("/api/v1/auth/clock-out", headers=_bearer(token))

    assert _post(auth_client, "clock-in").status_code == 200
    assert _post(auth_client, "login").status_code == 200


def test_preview_reports_clock_state_without_changing_it(auth_client, db):
    response = _post(auth_client, "preview", code="BAR1")
    assert response.status_code == 200
    assert response.json()["on_clock"] is False
    assert response.json()["employee"]["name"] == "Jessica Moore"
    assert db.query(TimeEntry).count() == 0
