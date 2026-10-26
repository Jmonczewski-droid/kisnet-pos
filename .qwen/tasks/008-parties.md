---
allowed: app/schemas/party.py, app/services/parties.py, app/api/routes/seats.py, app/api/routes/parties.py, tests/test_parties.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_parties.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists. services/orders.py (task 007) exists: reuse can_order/can_view_party and order_out from it.
Create:
- app/schemas/party.py: PartyIn(seat: str, party_name: str min 1, party_size: int ge=1, server_id: int|None=None), PartySummary, PartyDetail (adds closed_at and open_order: OrderOut|None) per conventions. Seat validation happens in the service (422 if not in ALL_SEATS).
- app/services/parties.py: list_seats(session, user), list_open_parties(session, user), create_party(session, user, data) (role rules per conventions; 422 bad seat, 409 occupied, 403 role, 422 bad server), get_party_detail(session, user, party_id), close_party(session, user, party_id) (409 if open order or closed; host for table seats, bartender for bar seats, admin any; server cannot close). Reuse OrderError or a similar error type.
- app/api/routes/seats.py: router with GET /seats.
- app/api/routes/parties.py: router with GET /parties (query open: bool), POST /parties (201), GET /parties/{party_id}, POST /parties/{party_id}/close.
tests/test_parties.py: build FastAPI() including seats, parties and orders routers under /api/v1, override get_db to the test SessionLocal. Cover: host creates table party with server SRV1 -> 201; host creating at Z3 -> 403; bartender creating at Z3 -> 201 with server null; duplicate seat -> 409; bad seat "Q9" -> 422; GET /seats returns 26 entries in ALL_SEATS order for admin and occupied one has party; server sees only own parties in list (open=true); close with open order -> 409, after completing the order close -> 200 and seat becomes free again; server cannot close -> 403.
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

EXACT PATHS (router paths are bare; the test app mounts them under /api/v1):
- app/api/routes/seats.py: "/seats" (GET)
- app/api/routes/parties.py: "/parties" (GET with open query, POST), "/parties/{party_id}" (GET), "/parties/{party_id}/close" (POST)
- The test app includes seats, parties AND orders routers (orders is needed to create open orders).
- Do NOT edit tests/conftest.py (out of scope); the guard there is already correct.

TEST RULES (the last attempt failed because a test had SRV1 create a party, which is a 403):
- Only HOST1 (table seats), BAR1 (bar seats) or ADM1 may CREATE parties in tests.
- To set up a party owned by SRV1, have HOST1 create it with server_id=2 (SRV1's seed id). Then log in SRV1 only to test
  forbidden or permitted actions on that party.
- Seed ids: HOST1=1, SRV1=2, KIT1=3, BAR1=4, ADM1=5.

CHECK ORDER for POST /parties (apply in this order, first failure wins):
1. seat not in ALL_SEATS -> 422
2. caller role not in (host, bartender, admin) -> 403
3. host and seat is a bar seat -> 403; bartender and seat is a table seat -> 403
4. host: server_id missing or not an active server -> 422
5. seat already has an open party -> 409
Then create. Use the exact seat strings: table seats like "B2", bar seats like "Z3".
