---
allowed: app/services/tickets.py, app/api/routes/tickets.py, tests/test_tickets.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_tickets.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists. services/orders.py and routes exist from task 007.
Create:
- app/services/tickets.py: ticket_access(user, track) -> raises 403 when the role may not see the track (kitchen: appetizers/hot/cold; bartender: bar; admin: all; host/server: none) and 422 for an invalid track; list_tickets(session, user, track) -> list of dicts (order_id, track, seat, party_name, opened_at = min sent_at, items) using only open orders, items with category == track and bumped_at IS NULL, sorted by opened_at; bump_ticket(session, user, order_id, track) -> int count, sets bumped_at = utcnow() on those items, 404 if order missing.
- app/api/routes/tickets.py: router with GET /tickets (query track) and POST /tickets/{order_id}/{track}/bump.
tests/test_tickets.py: FastAPI() including orders and tickets routers under /api/v1 with get_db override. Seed a party at seat Z3 (bartender BAR1 creates it via the API or ORM), an order with a Beer (bar), Chicken Wings (appetizers) and Burger (hot). Assert: kitchen GET track=appetizers returns one ticket with the wings; kitchen GET track=bar -> 403; bartender GET track=bar returns beer ticket; bump appetizers returns 1 and the ticket disappears; a voided item still appears on the ticket with voided true until bumped; invalid track -> 422.
Do not create other files.

IMPORTANT (same rules as the other router tasks):
- Do NOT edit app/main.py or app/api/routes/__init__.py. Do NOT import app.main or modules not in this task.
- Routers use BARE paths; the app is assembled later under /api/v1.
- tests/conftest.py has NO client fixture. In this test module define a fixture named `client`:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    @pytest.fixture
    def client(db):
        app = FastAPI()
        app.include_router(<router>, prefix="/api/v1")   # include every router this test needs
        return TestClient(app)
  Use the `db` and `login` fixtures from conftest.

EXACT PATHS: app/api/routes/tickets.py: "/tickets" (GET with track query), "/tickets/{order_id}/{track}/bump" (POST).
The test app includes orders and tickets routers. Do NOT edit tests/conftest.py.
