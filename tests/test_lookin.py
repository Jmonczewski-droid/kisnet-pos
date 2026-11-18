"""The look-in portal: read-only, its own sign-in, and its own server with nothing else on it."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import totp
from app.core.config import settings
from app.core.time import utcnow
from app.lookin_app import app as lookin_app
from app.models.lookin import LookinSession

API = "/api/v1"


@pytest.fixture
def portal(db):
    """The look-in-only server."""
    return TestClient(lookin_app)


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1_800_000_000.0}
    monkeypatch.setattr(totp.time, "time", lambda: now["t"])

    class Clock:
        def tick(self):
            now["t"] += 30

        def code(self, secret):
            return totp.code_for_step(secret, totp.current_step())

    return Clock()


def _two_step(client, headers, clock):
    """Turn on two-step sign-in for whoever `headers` belongs to; returns the key."""
    secret = client.post(f"{API}/auth/totp/setup", headers=headers).json()["secret"]
    assert client.post(f"{API}/auth/totp/enable", headers=headers, json={"otp": clock.code(secret)}).status_code == 200
    clock.tick()
    return secret


def _look_in(portal, clock, secret, code="ADM1", pin="1234"):
    response = portal.post(f"{API}/lookin/login", json={"code": code, "pin": pin, "otp": clock.code(secret)})
    assert response.status_code == 200, response.text
    clock.tick()
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_look_in_needs_two_step_sign_in(client, portal, login, clock):
    refused = portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234"})
    assert refused.status_code == 403 and refused.headers["X-Error-Code"] == "two_step_setup_required"

    secret = _two_step(client, login("ADM1"), clock)
    missing = portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234"})
    assert missing.status_code == 401 and missing.headers["X-Error-Code"] == "otp_required"
    assert portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234", "otp": "000000"}).status_code == 401
    assert portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "nope", "otp": clock.code(secret)}).status_code == 401
    signed_in = portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234", "otp": clock.code(secret)})
    assert signed_in.status_code == 200
    assert signed_in.json()["access"] == "owner"


def test_look_in_works_without_clocking_in(client, portal, login, clock, db):
    owner = login("ADM1")
    secret = _two_step(client, owner, clock)
    client.post(f"{API}/auth/clock-out", headers=owner)
    assert client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234", "otp": clock.code(secret)}).status_code == 409
    clock.tick()
    viewer = _look_in(portal, clock, secret)
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 200


def test_look_in_is_not_for_team_members(client, portal, login, clock):
    login("SRV1")
    refused = portal.post(f"{API}/lookin/login", json={"code": "SRV1", "pin": "1234"})
    assert refused.status_code == 403
    assert "owner and managers" in refused.json()["detail"]


def test_look_in_shows_live_numbers_and_no_personal_details(client, portal, login, clock):
    owner = login("ADM1")
    secret = _two_step(client, owner, clock)
    viewer = _look_in(portal, clock, secret)

    before = portal.get(f"{API}/lookin", headers=viewer).json()
    assert before["sales_cents"] == 0 and before["open_tables"] == 0

    host, server = login("HOST1"), login("SRV1")
    server_id = next(e["id"] for e in client.get(f"{API}/employees?role=server", headers=host).json() if e["code"] == "SRV1")
    party = client.post(f"{API}/parties", headers=host,
                        json={"seat": "A1", "party_name": "Lee", "party_size": 2, "server_id": server_id}).json()
    item = next(i for i in client.get(f"{API}/menu", headers=server).json() if i["category"] == "hot")
    client.post(f"{API}/parties/{party['id']}/items", headers=server, json={"items": [{"menu_item_id": item["id"], "qty": 3}]})

    after = portal.get(f"{API}/lookin", headers=viewer).json()
    assert after["sales_cents"] == 3 * item["price_cents"]
    assert (after["open_tables"], after["active_tickets"]) == (1, 1)
    assert {p["name"] for p in after["on_clock"]} == {"Linda Park", "Emma Carter", "Michael Brooks"}
    # who is working and since when; no codes, addresses, birth dates or SSN
    assert set(after["on_clock"][0]) == {"employee_id", "name", "position", "clocked_in_at", "open_tables"}
    assert next(p for p in after["on_clock"] if p["name"] == "Michael Brooks")["open_tables"] == 1
    assert [row["sales_cents"] for row in after["hours"] if row["sales_cents"]] == [3 * item["price_cents"]]
    assert sum(row["labor_cents"] for row in after["hours"]) == after["labor_cents"]
    text = portal.get(f"{API}/lookin", headers=viewer).text
    assert "ssn" not in text.lower() and "address" not in text.lower() and "pin" not in text.lower()


def test_labor_can_be_managed_remotely_by_clocking_someone_out(client, portal, login, clock):
    owner, server = login("ADM1"), login("SRV1")
    secret = _two_step(client, owner, clock)
    viewer = _look_in(portal, clock, secret)
    on_clock = portal.get(f"{API}/lookin", headers=viewer).json()["on_clock"]
    target = next(p for p in on_clock if p["name"] == "Michael Brooks")

    assert portal.post(f"{API}/lookin/clock-out/{target['employee_id']}").status_code == 401          # needs the sign-in
    assert portal.post(f"{API}/lookin/clock-out/{target['employee_id']}", headers=server).status_code == 401
    done = portal.post(f"{API}/lookin/clock-out/{target['employee_id']}", headers=viewer)
    assert done.json() == {"clocked_out": True, "name": "Michael Brooks"}

    names = {p["name"] for p in portal.get(f"{API}/lookin", headers=viewer).json()["on_clock"]}
    assert "Michael Brooks" not in names
    assert client.get(f"{API}/auth/me", headers=server).status_code == 401      # their station session ended
    assert portal.post(f"{API}/lookin/clock-out/{target['employee_id']}", headers=viewer).status_code == 404
    assert portal.post(f"{API}/lookin/clock-out/99999", headers=viewer).status_code == 404


def test_look_in_token_is_read_only_and_good_for_nothing_else(client, portal, login, clock):
    owner = login("ADM1")
    secret = _two_step(client, owner, clock)
    viewer = _look_in(portal, clock, secret)
    # On the full POS, a look-in token is not a station session
    for path in ("/auth/me", "/admin/roster", "/admin/on-clock", "/parties", "/menu", "/admin/devices"):
        assert client.get(f"{API}{path}", headers=viewer).status_code == 401, path
    assert client.post(f"{API}/admin/end-of-day", headers=viewer).status_code == 401
    # ...and a station token does not open the look-in feed
    assert portal.get(f"{API}/lookin", headers=owner).status_code == 401
    assert portal.get(f"{API}/lookin").status_code == 401


def test_portal_server_has_nothing_but_the_look_in(portal, login):
    owner = login("ADM1")
    assert portal.get(f"{API}/portal").json() == {"mode": "lookin"}
    assert portal.get("/").status_code == 200
    for method, path in (("get", "/auth/me"), ("post", "/auth/login"), ("post", "/auth/clock-in"), ("get", "/admin/roster"),
                         ("get", "/admin/devices"), ("get", "/parties"), ("get", "/menu"), ("post", "/menu/import"),
                         ("post", "/admin/end-of-day"), ("get", "/reports/daily-sales"), ("post", "/devices/pair"),
                         ("post", "/auth/change-pin"), ("post", "/auth/totp/setup")):
        assert getattr(portal, method)(f"{API}{path}", headers=owner).status_code == 404, path
    assert portal.get("/docs").status_code == 404
    assert portal.get(f"{API}/openapi.json").status_code == 404


def test_look_in_sign_out_and_expiry(client, portal, login, clock, db):
    secret = _two_step(client, login("ADM1"), clock)
    viewer = _look_in(portal, clock, secret)
    assert portal.post(f"{API}/lookin/logout", headers=viewer).json() == {"signed_out": True}
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 401

    viewer = _look_in(portal, clock, secret)
    row = db.query(LookinSession).one()
    assert timedelta(hours=settings.LOOKIN_HOURS - 1) < row.expires_at - utcnow() <= timedelta(hours=settings.LOOKIN_HOURS)
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 401


def test_losing_access_ends_the_look_in(client, portal, login, clock):
    owner = login("ADM1")
    card = client.post(f"{API}/admin/employees", headers=owner,
                       json={"name": "Maya Manager", "access": "manager", "positions": ["server"], "pin": "0000"}).json()
    client.post(f"{API}/auth/change-pin", json={"code": card["code"], "pin": "0000", "new_pin": "7777"})
    client.post(f"{API}/auth/clock-in", json={"code": card["code"], "pin": "7777", "position": "admin"})
    manager = {"Authorization": "Bearer " + client.post(f"{API}/auth/login", json={"code": card["code"], "pin": "7777"}).json()["token"]}
    secret = _two_step(client, manager, clock)
    viewer = _look_in(portal, clock, secret, code=card["code"], pin="7777")
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 200

    client.patch(f"{API}/admin/employees/{card['id']}", headers=owner, json={"access": "team"})
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 401
    assert portal.post(f"{API}/lookin/login", json={"code": card["code"], "pin": "7777"}).status_code == 403


def test_deactivating_someone_ends_their_look_in(client, portal, login, clock):
    owner = login("ADM1")
    card = client.post(f"{API}/admin/employees", headers=owner,
                       json={"name": "Second Owner", "access": "owner", "pin": "0000"}).json()
    client.post(f"{API}/auth/change-pin", json={"code": card["code"], "pin": "0000", "new_pin": "7777"})
    client.post(f"{API}/auth/clock-in", json={"code": card["code"], "pin": "7777"})
    second = {"Authorization": "Bearer " + client.post(f"{API}/auth/login", json={"code": card["code"], "pin": "7777"}).json()["token"]}
    secret = _two_step(client, second, clock)
    viewer = _look_in(portal, clock, secret, code=card["code"], pin="7777")
    client.post(f"{API}/admin/employees/{card['id']}/deactivate", headers=owner)
    assert portal.get(f"{API}/lookin", headers=viewer).status_code == 401


def test_wrong_codes_lock_the_look_in(client, portal, login, clock):
    secret = _two_step(client, login("ADM1"), clock)
    for _ in range(5):
        assert portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234", "otp": "000000"}).status_code == 401
    assert portal.post(f"{API}/lookin/login", json={"code": "ADM1", "pin": "1234", "otp": clock.code(secret)}).status_code == 429


@pytest.mark.parametrize("which", ["pos", "portal"])
def test_security_headers(client, portal, which):
    server = client if which == "pos" else portal
    for path in ("/", f"{API}/portal", "/static/app.js"):
        headers = server.get(path).headers
        assert "script-src 'self'" in headers["Content-Security-Policy"], path
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"
    assert server.get(f"{API}/portal").headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in server.get("/").headers
    assert "Strict-Transport-Security" in server.get("/", headers={"X-Forwarded-Proto": "https"}).headers


def test_full_pos_reports_its_mode(client):
    assert client.get(f"{API}/portal").json() == {"mode": "full"}
