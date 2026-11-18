"""Device management: printers, monitors, pairing, ticket and receipt printing."""
import socket
import socketserver
import threading
from datetime import timedelta

import pytest

from app.core.time import utcnow
from app.models import Device
from app.services import printing

API = "/api/v1"


class FakePrinter:
    """A network printer that just remembers what it was sent."""

    def __init__(self):
        self.jobs = []
        outer = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                chunks = []
                while True:
                    data = self.request.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
                outer.jobs.append(b"".join(chunks))

        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def text(self):
        return b"\n".join(self.jobs).decode("cp437")

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def printer():
    fake = FakePrinter()
    yield fake
    fake.close()


def _closed_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _add(client, admin, **body):
    response = client.post(f"{API}/admin/devices", headers=admin, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _seat_party(client, login, seat="B2"):
    host = login("HOST1")
    server = login("SRV1")
    server_id = next(e["id"] for e in client.get(f"{API}/employees?role=server", headers=host).json()
                     if e["code"] == "SRV1")
    party = client.post(f"{API}/parties", headers=host,
                        json={"seat": seat, "party_name": "Smith", "party_size": 4, "server_id": server_id}).json()
    menu = client.get(f"{API}/menu", headers=server).json()
    by_category = {}
    for item in menu:
        by_category.setdefault(item["category"], item)
    return party["id"], server, by_category


# --- Admin screen ---------------------------------------------------------------------------

def test_devices_are_admin_only(client, login):
    assert client.get(f"{API}/admin/devices", headers=login("SRV1")).status_code == 403
    assert client.get(f"{API}/admin/devices").status_code == 401


def test_add_printer_and_monitor(client, login):
    admin = login("ADM1")
    printer = _add(client, admin, name="Kitchen printer", kind="printer", jobs=["hot", "cold"], host="192.168.1.50")
    assert printer["port"] == 9100
    assert printer["connection"] == "untested"
    assert printer["pairing_code"] is None

    monitor = _add(client, admin, name="Line monitor", kind="monitor", jobs=["hot"])
    assert monitor["connection"] == "waiting"
    assert len(monitor["pairing_code"]) == 6
    assert monitor["host"] is None

    names = [d["name"] for d in client.get(f"{API}/admin/devices", headers=admin).json()]
    assert names == ["Line monitor", "Kitchen printer"]  # monitors first, then printers


def test_device_validation(client, login):
    admin = login("ADM1")
    post = lambda **body: client.post(f"{API}/admin/devices", headers=admin, json=body).status_code
    assert post(name="P", kind="printer", jobs=["hot"]) == 422                      # printer needs an address
    assert post(name="P", kind="printer", jobs=["hot"], host="bad host!") == 422
    assert post(name="P", kind="fax", jobs=["hot"], host="10.0.0.1") == 422
    assert post(name="P", kind="printer", jobs=["dessert"], host="10.0.0.1") == 422
    assert post(name="P", kind="printer", jobs=[], host="10.0.0.1") == 422
    assert post(name="M", kind="monitor", jobs=["receipt"]) == 422                  # monitors do not print receipts
    _add(client, admin, name="Same", kind="monitor", jobs=["bar"])
    assert post(name="Same", kind="monitor", jobs=["bar"]) == 409


def test_device_lifecycle(client, login):
    admin = login("ADM1")
    device = _add(client, admin, name="Bar printer", kind="printer", jobs=["bar"], host="10.0.0.9", port=9101)
    url = f"{API}/admin/devices/{device['id']}"

    edited = client.patch(url, headers=admin, json={"name": "Bar printer 2", "jobs": ["bar", "receipt"]}).json()
    assert (edited["name"], edited["jobs"], edited["port"]) == ("Bar printer 2", ["bar", "receipt"], 9101)

    assert client.post(f"{url}/deactivate", headers=admin).json()["status"] == "inactive"
    assert client.post(f"{url}/deactivate", headers=admin).status_code == 409
    assert client.post(f"{url}/reactivate", headers=admin).json()["status"] == "active"
    assert client.post(f"{url}/archive", headers=admin).json()["status"] == "archived"
    assert client.patch(url, headers=admin, json={"name": "x"}).status_code == 409
    assert client.post(f"{url}/reactivate", headers=admin).status_code == 409

    assert client.get(f"{API}/admin/devices", headers=admin).json() == []
    assert len(client.get(f"{API}/admin/devices?include_archived=true", headers=admin).json()) == 1
    assert client.post(f"{API}/admin/devices/9999/archive", headers=admin).status_code == 404


# --- Monitors -------------------------------------------------------------------------------

def test_monitor_pairs_and_shows_its_tracks(client, login):
    admin = login("ADM1")
    monitor = _add(client, admin, name="Hot line", kind="monitor", jobs=["hot"])
    party_id, server, menu = _seat_party(client, login)
    client.post(f"{API}/parties/{party_id}/items", headers=server,
                json={"items": [{"menu_item_id": menu["hot"]["id"], "qty": 2},
                                {"menu_item_id": menu["bar"]["id"], "qty": 1}]})

    assert client.get(f"{API}/devices/tickets").status_code == 401
    assert client.post(f"{API}/devices/pair", json={"code": "WRONG1"}).status_code == 404

    paired = client.post(f"{API}/devices/pair", json={"code": monitor["pairing_code"].lower()},
                         headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Tablet)"})
    assert paired.status_code == 200
    token = {"Authorization": f"Bearer {paired.json()['token']}"}
    assert paired.json()["device"]["platform"] == "Android"

    # The code works once
    assert client.post(f"{API}/devices/pair", json={"code": monitor["pairing_code"]}).status_code == 404

    board = client.get(f"{API}/devices/tickets", headers=token).json()
    assert list(board["tracks"]) == ["hot"]
    assert [item["name"] for item in board["tracks"]["hot"][0]["items"]] == [menu["hot"]["name"]]
    order_id = board["tracks"]["hot"][0]["order_id"]

    row = client.get(f"{API}/admin/devices", headers=admin).json()[0]
    assert (row["connection"], row["platform"], row["pairing_code"]) == ("online", "Android", None)

    assert client.post(f"{API}/devices/tickets/{order_id}/bar/bump", headers=token).status_code == 403
    assert client.post(f"{API}/devices/tickets/{order_id}/hot/bump", headers=token).json() == 1
    assert client.get(f"{API}/devices/tickets", headers=token).json()["tracks"]["hot"] == []


def test_an_employee_token_is_not_a_device_token(client, login):
    assert client.get(f"{API}/devices/tickets", headers=login("KIT1")).status_code == 401


def test_pairing_code_expires(client, login, db):
    admin = login("ADM1")
    monitor = _add(client, admin, name="Old code", kind="monitor", jobs=["cold"])
    device = db.get(Device, monitor["id"])
    device.pairing_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(f"{API}/devices/pair", json={"code": monitor["pairing_code"]}).status_code == 404
    row = client.get(f"{API}/admin/devices", headers=admin).json()[0]
    assert (row["connection"], row["pairing_code"]) == ("not paired", None)


@pytest.mark.parametrize("action", ["deactivate", "archive", "unpair", "pairing-code"])
def test_admin_can_cut_off_a_monitor(client, login, action):
    admin = login("ADM1")
    monitor = _add(client, admin, name="Cut off", kind="monitor", jobs=["bar"])
    token = client.post(f"{API}/devices/pair", json={"code": monitor["pairing_code"]}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{API}/devices/me", headers=headers).status_code == 200
    assert client.post(f"{API}/admin/devices/{monitor['id']}/{action}", headers=admin).status_code == 200
    assert client.get(f"{API}/devices/me", headers=headers).status_code == 401


def test_monitor_can_disconnect_itself(client, login):
    admin = login("ADM1")
    monitor = _add(client, admin, name="Leaving", kind="monitor", jobs=["bar"])
    token = client.post(f"{API}/devices/pair", json={"code": monitor["pairing_code"]}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post(f"{API}/devices/disconnect", headers=headers).json() == {"disconnected": True}
    assert client.get(f"{API}/devices/me", headers=headers).status_code == 401


@pytest.mark.parametrize("agent,platform", [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "PC"),
    ("Mozilla/5.0 (X11; Linux x86_64)", "PC"),
    ("Mozilla/5.0 (Linux; Android 14)", "Android"),
    ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", "Apple"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Apple"),
    ("", "Other"),
])
def test_platform_from_user_agent(agent, platform):
    from app.services.devices import platform_from_user_agent
    assert platform_from_user_agent(agent) == platform


# --- Printers -------------------------------------------------------------------------------

def test_test_print_reaches_the_printer(client, login, printer):
    admin = login("ADM1")
    device = _add(client, admin, name="Kitchen", kind="printer", jobs=["hot"], host="127.0.0.1", port=printer.port)
    result = client.post(f"{API}/admin/devices/{device['id']}/test", headers=admin)
    assert result.status_code == 200
    assert result.json()["connection"] == "ok"
    assert "Printer test" in printer.text()
    assert printer.jobs[0].endswith(b"\x1dV\x00")  # paper cut


def test_test_print_reports_an_unreachable_printer(client, login):
    admin = login("ADM1")
    device = _add(client, admin, name="Gone", kind="printer", jobs=["hot"], host="127.0.0.1", port=_closed_port())
    result = client.post(f"{API}/admin/devices/{device['id']}/test", headers=admin)
    assert result.status_code == 502
    row = client.get(f"{API}/admin/devices", headers=admin).json()[0]
    assert row["connection"] == "error" and row["last_error"]


def test_tickets_print_on_the_printer_for_their_track(client, login, printer):
    admin = login("ADM1")
    _add(client, admin, name="Hot printer", kind="printer", jobs=["hot"], host="127.0.0.1", port=printer.port)
    party_id, server, menu = _seat_party(client, login)

    sent = client.post(f"{API}/parties/{party_id}/send", headers=server, json={
        "items": [{"menu_item_id": menu["hot"]["id"], "qty": 2, "notes": "no onions"},
                  {"menu_item_id": menu["bar"]["id"], "qty": 1}], "updates": [], "voids": []})
    assert sent.status_code == 200
    assert len(printer.jobs) == 1  # one hot ticket; nothing prints the bar item
    text = printer.text()
    assert "HOT" in text and "B2" in text and "Smith" in text
    assert f"2 x {menu['hot']['name']}" in text and "no onions" in text
    assert menu["bar"]["name"] not in text

    # A later send prints only what changed
    hot_line = next(item for item in sent.json()["items"] if item["category"] == "hot")
    client.post(f"{API}/parties/{party_id}/send", headers=server,
                json={"items": [], "updates": [], "voids": [hot_line["id"]]})
    assert len(printer.jobs) == 2
    assert "VOID" in printer.jobs[1].decode("cp437")


def test_an_unreachable_printer_never_fails_an_order(client, login):
    admin = login("ADM1")
    _add(client, admin, name="Unplugged", kind="printer", jobs=["hot", "receipt"], host="127.0.0.1",
         port=_closed_port())
    party_id, server, menu = _seat_party(client, login)
    sent = client.post(f"{API}/parties/{party_id}/items", headers=server,
                       json={"items": [{"menu_item_id": menu["hot"]["id"], "qty": 1}]})
    assert sent.status_code == 201
    assert client.post(f"{API}/parties/{party_id}/close", headers=server).status_code == 200
    assert client.get(f"{API}/admin/devices", headers=admin).json()[0]["connection"] == "error"


def test_inactive_printers_do_not_print(client, login, printer):
    admin = login("ADM1")
    device = _add(client, admin, name="Off", kind="printer", jobs=["hot"], host="127.0.0.1", port=printer.port)
    client.post(f"{API}/admin/devices/{device['id']}/deactivate", headers=admin)
    party_id, server, menu = _seat_party(client, login)
    client.post(f"{API}/parties/{party_id}/items", headers=server,
                json={"items": [{"menu_item_id": menu["hot"]["id"], "qty": 1}]})
    assert printer.jobs == []


# --- Receipts -------------------------------------------------------------------------------

def test_receipt_prints_when_the_table_is_sent_to_payment(client, login, printer):
    admin = login("ADM1")
    _add(client, admin, name="Front printer", kind="printer", jobs=["receipt"], host="127.0.0.1", port=printer.port)
    party_id, server, menu = _seat_party(client, login)
    client.post(f"{API}/parties/{party_id}/items", headers=server,
                json={"items": [{"menu_item_id": menu["hot"]["id"], "qty": 2},
                                {"menu_item_id": menu["bar"]["id"], "qty": 1}]})
    assert printer.jobs == []  # a receipt printer does not print kitchen tickets
    assert client.post(f"{API}/parties/{party_id}/close", headers=server).status_code == 200

    assert len(printer.jobs) == 1
    text = printer.text()
    total = 2 * menu["hot"]["price_cents"] + menu["bar"]["price_cents"]
    assert "Table B2" in text and "Party: Smith" in text and "Server: Michael Brooks" in text
    assert f"2 {menu['hot']['name']}" in text
    assert f"TOTAL {printing.money(total)}" in text
    assert "Items: 3" in text


def test_receipt_template_rules():
    template = "\n".join([
        "# a note that never prints",
        "!BIG NAME",
        "^centered",
        "----",
        "Table {seat} | #{order_number}",
        "{items}",
        "TOTAL {total} {typo}",
    ])
    lines = printing.receipt_lines(template, {"seat": "A1", "order_number": 7, "total": "$5.00"}, [(1, "Soup", 500)])
    assert lines[0] == ("title", "BIG NAME")
    assert lines[1] == ("center", "centered")
    assert lines[2] == ("left", "-" * printing.WIDTH)
    assert lines[3][1].startswith("Table A1") and lines[3][1].endswith("#7") and len(lines[3][1]) == printing.WIDTH
    assert lines[4][1].startswith("1 Soup") and lines[4][1].endswith("$5.00")
    assert lines[5] == ("left", "TOTAL $5.00 {typo}")  # an unknown field is left visible
    assert len(lines) == 6


def test_shipped_receipt_template_fills_every_field(client, login):
    preview = client.get(f"{API}/admin/receipt-preview", headers=login("ADM1"))
    assert preview.status_code == 200
    assert "{" not in preview.text
    assert "TOTAL $47.50" in preview.text
    assert all(len(line) <= printing.WIDTH for line in preview.text.splitlines())
