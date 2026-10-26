---
allowed: app/schemas/order.py, app/services/orders.py, app/api/routes/orders.py, tests/test_orders.py
verify: venv/bin/python -m pytest -q tests/test_orders.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists (fixtures db, client, login).
Create:
- app/schemas/order.py: OrderItemIn(menu_item_id: int, qty: int = Field(ge=1), notes: str|None=None), OrderItemsIn(items: list[OrderItemIn] min 1), OrderItemPatch(qty: int|None ge=1, notes: str|None), OrderItemOut, OrderOut exactly per the "Orders" section of the conventions (from_attributes=True).
- app/services/orders.py: functions taking session first: can_order(user, party) and can_view_party(user, party) per the conventions (put both here); add_items(session, user, party, items) -> Order; update_item(session, user, item, patch); void_item(session, user, item); complete_order(session, user, party) -> Order; order_out(order) helper computing total_cents and bumped/line_total. Raise a small OrderError(status, detail) for 403/404/409/422 which routes convert to HTTPException. Party must be open for add_items (409 otherwise).
- app/api/routes/orders.py: router with POST /parties/{party_id}/items (201), PATCH /order-items/{item_id}, DELETE /order-items/{item_id} (204), POST /parties/{party_id}/complete. Use get_current_employee from app.api.deps and get_db from app.db.base. 404 if the party/item is missing.
Tests insert Party rows directly with the ORM (Employee SRV1 as server, seat "B2"), login via the login fixture to get headers, then exercise the endpoints through a FastAPI() app that includes only this router under prefix /api/v1 (override get_db with the test SessionLocal).
tests/test_orders.py covers: create order with 2 lines snapshots name/price and recipe ingredients; second POST to same party marks new lines changed=True while first-batch lines stay changed=False; PATCH qty sets changed; DELETE voids and total excludes it; bumped item PATCH returns 409 (set bumped_at directly in db); complete sets status completed; complete with no open order 409; server not owning party gets 403 on POST items; unknown menu_item_id 422.
Do not create other files.

IMPORTANT:
- Do NOT edit app/main.py or app/api/routes/__init__.py (out of scope; app.main and parties routes do not exist yet).
- Do NOT import app.api.routes.parties or any module not in this task.
- app/api/routes/orders.py: `router = APIRouter()` with BARE paths: "/parties/{party_id}/items" (POST),
  "/order-items/{item_id}" (PATCH, DELETE), "/parties/{party_id}/complete" (POST). No prefix on the router.
- tests/test_orders.py: do NOT use the shared `client` fixture (app.main does not exist yet). Define a module fixture:
    app = FastAPI(); app.include_router(router, prefix="/api/v1"); return TestClient(app)
  using the `db` fixture from conftest for data. Use `login` fixture from conftest for headers.
- Name the module fixture `client` (defined in tests/test_orders.py itself). The shared conftest no longer has a client fixture.
