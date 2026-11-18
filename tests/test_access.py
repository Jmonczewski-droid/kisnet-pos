"""Access levels (owner / manager / team member), starter PINs, lockout and owner two-step sign-in."""
import pytest

from app.core import totp
from app.core.constants import MAX_FAILED_ATTEMPTS
from app.models import Employee

API = "/api/v1"


def _card(client, owner, name, access=None, positions=(), pin="0000"):
    body = {"name": name, "positions": list(positions), "pin": pin}
    if access:
        body["access"] = access
    return client.post(f"{API}/admin/employees", headers=owner, json=body)


def _sign_in(client, code, pin, position=None):
    """Clock in and log in; returns the auth header."""
    body = {"code": code, "pin": pin}
    if position:
        body["position"] = position
    assert client.post(f"{API}/auth/clock-in", json=body).status_code == 200
    token = client.post(f"{API}/auth/login", json={"code": code, "pin": pin}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _hire(client, owner, name, access=None, positions=(), pin="7777"):
    """Create a card and have the employee choose their own PIN. Returns (card, auth header)."""
    card = _card(client, owner, name, access, positions).json()
    assert client.post(f"{API}/auth/change-pin",
                       json={"code": card["code"], "pin": "0000", "new_pin": pin}).status_code == 200
    return card, _sign_in(client, card["code"], pin, position=card["positions"].split(",")[0])


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock for authenticator codes."""
    now = {"t": 1_800_000_000.0}
    monkeypatch.setattr(totp.time, "time", lambda: now["t"])

    class Clock:
        def tick(self, seconds=30):
            now["t"] += seconds

        def code(self, secret):
            return totp.code_for_step(secret, totp.current_step())

    return Clock()


# --- Who may do what ------------------------------------------------------------------------

def test_seed_admin_is_the_owner(client, login):
    assert client.get(f"{API}/auth/me", headers=login("ADM1")).json()["access"] == "owner"
    assert client.get(f"{API}/auth/me", headers=login("SRV1")).json()["access"] == "team"


def test_manager_runs_the_floor_but_not_the_database(client, login):
    owner = login("ADM1")
    card, manager = _hire(client, owner, "Maya Manager", access="manager")
    assert (card["code"], card["access"], card["positions"]) == ("ADM2", "manager", "admin")
    assert client.get(f"{API}/auth/me", headers=manager).json()["access"] == "manager"

    for path in ("/admin/on-clock", "/admin/stats", "/timecard/summary", "/menu/export", "/tickets?track=hot",
                 "/reports/daily-sales?start=2026-01-01&end=2026-01-02"):
        assert client.get(f"{API}{path}", headers=manager).status_code == 200, path

    for path in ("/admin/roster", "/admin/recipes", "/admin/devices", "/admin/receipt-preview"):
        assert client.get(f"{API}{path}", headers=manager).status_code == 403, path
    assert _card(client, manager, "Sneaky", positions=["server"]).status_code == 403
    assert client.patch(f"{API}/admin/employees/1", headers=manager, json={"name": "x"}).status_code == 403
    assert client.post(f"{API}/admin/employees/1/archive", headers=manager).status_code == 403
    assert client.post(f"{API}/admin/devices", headers=manager,
                       json={"name": "M", "kind": "monitor", "jobs": ["hot"]}).status_code == 403
    assert client.post(f"{API}/menu/import", headers=manager, content="x").status_code == 403


def test_team_member_has_no_management_access(client, login):
    server = login("SRV1")
    for path in ("/admin/on-clock", "/admin/stats", "/admin/roster", "/admin/devices", "/timecard/summary"):
        assert client.get(f"{API}{path}", headers=server).status_code == 403, path


def test_access_and_positions_are_settled_together(client, login):
    owner = login("ADM1")
    assert _card(client, owner, "No Station").status_code == 422                       # team member with no station
    assert _card(client, owner, "No Station", access="team", positions=["admin"]).status_code == 422
    assert _card(client, owner, "Bad", access="boss", positions=["server"]).status_code == 422

    both = _card(client, owner, "Floor Manager", access="manager", positions=["server", "bartender"]).json()
    assert both["positions"] == "admin,server,bartender"
    legacy = _card(client, owner, "Old Style", positions=["admin"]).json()                # admin position means manager
    assert legacy["access"] == "manager"
    team = _card(client, owner, "Cook", positions=["kitchen"]).json()
    assert (team["access"], team["positions"]) == ("team", "kitchen")

    row = client.patch(f"{API}/admin/employees/{team['id']}", headers=owner, json={"access": "manager"}).json()
    assert (row["access"], row["positions"]) == ("manager", ["admin", "kitchen"])
    row = client.patch(f"{API}/admin/employees/{team['id']}", headers=owner, json={"access": "team"}).json()
    assert (row["access"], row["positions"]) == ("team", ["kitchen"])


def test_there_is_always_an_owner(client, login):
    owner = login("ADM1")
    me = client.get(f"{API}/auth/me", headers=owner).json()["id"]
    assert client.patch(f"{API}/admin/employees/{me}", headers=owner, json={"access": "manager"}).status_code == 409
    assert client.post(f"{API}/admin/employees/{me}/deactivate", headers=owner).status_code == 409
    assert client.post(f"{API}/admin/employees/{me}/archive", headers=owner).status_code == 409

    second, second_owner = _hire(client, owner, "Second Owner", access="owner")
    assert client.get(f"{API}/admin/roster", headers=second_owner).status_code == 200
    assert client.patch(f"{API}/admin/employees/{me}", headers=second_owner, json={"access": "manager"}).status_code == 200
    assert client.get(f"{API}/admin/roster", headers=owner).status_code == 403  # no longer an owner


def test_demotion_ends_a_manager_session(client, login):
    owner = login("ADM1")
    card, manager = _hire(client, owner, "Short Lived", access="manager", positions=["server"])
    assert client.get(f"{API}/admin/on-clock", headers=manager).status_code == 200
    client.patch(f"{API}/admin/employees/{card['id']}", headers=owner, json={"access": "team"})
    assert client.get(f"{API}/admin/on-clock", headers=manager).status_code == 401


# --- Starter PINs: employees protect their own --------------------------------------------

def test_new_employee_must_choose_their_own_pin(client, login):
    owner = login("ADM1")
    card = _card(client, owner, "New Hire", positions=["server"], pin="4321").json()
    code = card["code"]
    roster_row = lambda: next(r for r in client.get(f"{API}/admin/roster", headers=owner).json() if r["id"] == card["id"])
    assert roster_row()["pin_is_temporary"] is True

    for path in ("clock-in", "login", "preview"):
        blocked = client.post(f"{API}/auth/{path}", json={"code": code, "pin": "4321"})
        assert blocked.status_code == 403 and blocked.headers["X-Error-Code"] == "pin_change_required", path

    change = lambda pin, new: client.post(f"{API}/auth/change-pin", json={"code": code, "pin": pin, "new_pin": new})
    assert change("wrong", "8642").status_code == 401
    assert change("4321", "4321").status_code == 422      # must differ
    assert change("4321", "12").status_code == 422        # too short
    assert change("4321", "8642").status_code == 200
    assert roster_row()["pin_is_temporary"] is False
    assert client.post(f"{API}/auth/clock-in", json={"code": code, "pin": "8642"}).status_code == 200
    assert client.post(f"{API}/auth/clock-in", json={"code": code, "pin": "4321"}).status_code == 401


def test_owner_changing_their_own_pin_is_not_a_starter_pin(client, login, db):
    owner = login("ADM1")
    me = client.get(f"{API}/auth/me", headers=owner).json()["id"]
    assert client.patch(f"{API}/admin/employees/{me}", headers=owner, json={"pin": "9090"}).status_code == 200
    assert client.post(f"{API}/auth/preview", json={"code": "ADM1", "pin": "9090"}).status_code == 200


def test_anyone_can_change_their_own_pin(client, login):
    login("SRV1")
    assert client.post(f"{API}/auth/change-pin", json={"code": "SRV1", "pin": "1234", "new_pin": "5151"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"code": "SRV1", "pin": "5151"}).status_code == 200


# --- Lockout --------------------------------------------------------------------------------

def test_wrong_pins_lock_the_sign_in(client, login):
    owner = login("ADM1")
    wrong = lambda: client.post(f"{API}/auth/clock-in", json={"code": "SRV2", "pin": "nope"})
    for _ in range(MAX_FAILED_ATTEMPTS):
        assert wrong().status_code == 401
    locked = client.post(f"{API}/auth/clock-in", json={"code": "SRV2", "pin": "1234"})
    assert locked.status_code == 429 and locked.headers["X-Error-Code"] == "locked"
    row = next(r for r in client.get(f"{API}/admin/roster", headers=owner).json() if r["code"] == "SRV2")
    assert row["locked"] is True

    # The owner unlocks by issuing a new starter PIN
    client.patch(f"{API}/admin/employees/{row['id']}", headers=owner, json={"pin": "3030"})
    assert client.post(f"{API}/auth/change-pin", json={"code": "SRV2", "pin": "3030", "new_pin": "6161"}).status_code == 200
    assert client.post(f"{API}/auth/clock-in", json={"code": "SRV2", "pin": "6161"}).status_code == 200


def test_a_correct_pin_clears_the_count(client, login):
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        client.post(f"{API}/auth/preview", json={"code": "SRV3", "pin": "nope"})
    assert client.post(f"{API}/auth/preview", json={"code": "SRV3", "pin": "1234"}).status_code == 200
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        client.post(f"{API}/auth/preview", json={"code": "SRV3", "pin": "nope"})
    assert client.post(f"{API}/auth/preview", json={"code": "SRV3", "pin": "1234"}).status_code == 200


# --- Owner two-step sign-in -----------------------------------------------------------------

def test_two_step_setup_is_for_owner_and_managers(client, login):
    owner = login("ADM1")
    card, manager = _hire(client, owner, "Maya Manager", access="manager")
    assert client.post(f"{API}/auth/totp/setup", headers=manager).status_code == 200  # needed for the look-in portal
    assert client.post(f"{API}/auth/totp/setup", headers=login("SRV1")).status_code == 403


def test_owner_two_step_sign_in(client, login, clock):
    owner = login("ADM1")
    assert client.get(f"{API}/auth/totp", headers=owner).json() == {"enabled": False, "pending": False}

    setup = client.post(f"{API}/auth/totp/setup", headers=owner).json()
    secret = setup["secret"]
    assert setup["uri"].startswith("otpauth://totp/KISnet-POS%3AADM1?secret=" + secret)
    assert setup["qr_svg"].startswith("<svg")
    assert client.get(f"{API}/auth/totp", headers=owner).json() == {"enabled": False, "pending": True}

    # Not on until a code from the app confirms it; sign-in still works with the PIN alone
    assert client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234"}).status_code == 200
    owner = {"Authorization": "Bearer " + client.post(
        f"{API}/auth/login", json={"code": "ADM1", "pin": "1234"}).json()["token"]}
    assert client.post(f"{API}/auth/totp/enable", headers=owner, json={"otp": "000000"}).status_code == 422
    assert client.post(f"{API}/auth/totp/enable", headers=owner, json={"otp": clock.code(secret)}).json()["enabled"] is True
    assert client.post(f"{API}/auth/totp/setup", headers=owner).status_code == 409

    sign_in = lambda **extra: client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234", **extra})
    missing = sign_in()
    assert missing.status_code == 401 and missing.headers["X-Error-Code"] == "otp_required"
    assert sign_in(otp="000000").headers["X-Error-Code"] == "otp_invalid"
    assert sign_in(otp=clock.code(secret)).headers["X-Error-Code"] == "otp_invalid"   # the setup code was already used

    clock.tick()
    code = clock.code(secret)
    signed_in = sign_in(otp=code)
    assert signed_in.status_code == 200
    assert sign_in(otp=code).headers["X-Error-Code"] == "otp_invalid"                  # a code works once
    assert sign_in(pin="wrong", otp=code).status_code == 401                            # the PIN is still required

    # Clocking in needs only the PIN; it opens no session
    assert client.post(f"{API}/auth/preview", json={"code": "ADM1", "pin": "1234"}).status_code == 200

    # Turning it off takes a current code
    owner = {"Authorization": f"Bearer {signed_in.json()['token']}"}
    assert client.post(f"{API}/auth/totp/disable", headers=owner, json={"otp": "000000"}).status_code == 401
    clock.tick()
    assert client.post(f"{API}/auth/totp/disable", headers=owner, json={"otp": clock.code(secret)}).json()["enabled"] is False
    assert sign_in().status_code == 200


def test_wrong_codes_lock_the_owner_sign_in(client, login, clock, db):
    owner = login("ADM1")
    secret = client.post(f"{API}/auth/totp/setup", headers=owner).json()["secret"]
    client.post(f"{API}/auth/totp/enable", headers=owner, json={"otp": clock.code(secret)})
    clock.tick()
    for _ in range(MAX_FAILED_ATTEMPTS):
        assert client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234", "otp": "000000"}).status_code == 401
    locked = client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234", "otp": clock.code(secret)})
    assert locked.status_code == 429


def test_lost_phone_recovery_from_the_server(client, login, clock, db):
    from app.cli import reset_two_step
    owner = login("ADM1")
    secret = client.post(f"{API}/auth/totp/setup", headers=owner).json()["secret"]
    client.post(f"{API}/auth/totp/enable", headers=owner, json={"otp": clock.code(secret)})
    assert client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234"}).status_code == 401
    assert reset_two_step("ADM1") == 0
    assert client.post(f"{API}/auth/login", json={"code": "ADM1", "pin": "1234"}).status_code == 200
    assert reset_two_step("NOPE9") == 1


def test_two_step_roster_flag_and_demotion_clears_it(client, login, clock, db):
    owner = login("ADM1")
    second, second_owner = _hire(client, owner, "Second Owner", access="owner")
    secret = client.post(f"{API}/auth/totp/setup", headers=second_owner).json()["secret"]
    client.post(f"{API}/auth/totp/enable", headers=second_owner, json={"otp": clock.code(secret)})
    row = lambda: next(r for r in client.get(f"{API}/admin/roster", headers=owner).json() if r["id"] == second["id"])
    assert row()["two_step"] is True
    client.patch(f"{API}/admin/employees/{second['id']}", headers=owner, json={"access": "manager"})
    assert row()["two_step"] is True   # managers keep it
    client.patch(f"{API}/admin/employees/{second['id']}", headers=owner,
                 json={"access": "team", "positions": ["server"]})
    assert row()["two_step"] is False
    db.expire_all()
    assert db.get(Employee, second["id"]).totp_secret is None


def test_totp_matches_the_published_standard():
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    # RFC 6238 Appendix B (SHA-1): the 8-digit values end in these 6 digits
    assert totp.code_for_step(secret, 59 // 30) == "287082"
    assert totp.code_for_step(secret, 1111111109 // 30) == "081804"
    assert totp.code_for_step(secret, 1234567890 // 30) == "005924"
    assert totp.matching_step(secret, "287 082", at=59) == 1
    assert totp.matching_step(secret, "287082", at=59, after_step=1) is None
    assert totp.matching_step(secret, "287082", at=59 + 120) is None  # too old
