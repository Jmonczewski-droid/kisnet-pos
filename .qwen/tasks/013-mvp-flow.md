---
allowed: tests/test_mvp_flow.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_mvp_flow.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. Everything is implemented: app.main exists.
Write tests/test_mvp_flow.py implementing the MVP acceptance test from docs/KISnet-POS-Requirements.md section A11 through the HTTP API with the client and login fixtures (login("HOST1"), login("SRV1"), login("BAR1"), login("KIT1"), login("ADM1")):
1. HOST1 creates party "Smith", size 4, seat B2, server_id = SRV1's id (from GET /api/v1/auth/me with SRV1 headers). Expect 201.
2. SRV1 GET /api/v1/parties?open=true finds B2; POST /api/v1/parties/{id}/items with 2 Caesar Salad, 1 Burger, 2 Beer (menu_item_ids from GET /api/v1/menu). Expect 201.
3. KIT1 GET /api/v1/tickets?track=cold shows Caesar lines with seat B2; track=hot shows Burger; BAR1 GET /api/v1/tickets?track=bar shows Beer.
4. BAR1 creates party "Jones" size 2 at seat Z3 (no server). Orders 1 Mozzarella Sticks and 1 Beer. KIT1 GET track=appetizers shows seat Z3.
5. Complete both orders: SRV1 POST /api/v1/parties/{smith}/complete and BAR1 POST /api/v1/parties/{jones}/complete. Expect 200 each.
6. ADM1: GET /api/v1/admin/on-clock lists HOST1, SRV1, KIT1, BAR1, ADM1. Daily sales for explicit start/end equal to today's date in settings.BUSINESS_TIMEZONE has order_count 2, Caesar qty 2, Beer qty 3, Burger qty 1; food-usage has Romaine Lettuce 16 oz, Caesar Dressing 8 oz, Parmesan 4 oz.
Do not create other files.
