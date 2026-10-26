---
allowed: app/schemas/report.py, app/services/reports.py, app/api/routes/reports.py, tests/test_reports.py
max_attempts: 6
verify: venv/bin/python -m pytest -q tests/test_reports.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly. conftest from task 004 exists.
Create:
- app/schemas/report.py: DailySalesRow, DailySalesOut, FoodUsageRow, FoodUsageOut per the Reports section.
- app/services/reports.py: resolve_range(start: date|None, end: date|None) -> (start, end) defaulting to today in settings.BUSINESS_TIMEZONE (zoneinfo), converting local day bounds [start 00:00, end+1 00:00) to naive UTC datetimes; daily_sales(session, start, end) and food_usage(session, start, end) using completed orders (orders.completed_at in range, status completed), excluding voided items.
- app/api/routes/reports.py: router with GET /reports/daily-sales and GET /reports/food-usage (admin only via require_roles("admin")); query params start and end as date (optional).
tests/test_reports.py: FastAPI() including reports router under /api/v1 with get_db override. Create completed orders via ORM with completed_at set explicitly on a fixed local date (2026-10-20 18:00 America/New_York converted to naive UTC): order 1: 2 Caesar Salad + 1 Burger; order 2: 2 Beer. Plus one open order that must not count. Assert daily-sales for that date: order_count 2, total_qty 5 (Caesar 2, Burger 1, Beer 2), rows sorted by name, Caesar qty 2 sales_cents 2000. Assert food-usage: Romaine Lettuce 16 oz, Caesar Dressing 8 oz, Parmesan 4 oz, Ground Beef 6 oz. Assert voided items are excluded. Assert SRV1 gets 403.
Create items with ingredient snapshots by writing rows directly with the ORM (copy recipe lines into OrderItemIngredient).
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

EXACT PATHS: app/api/routes/reports.py: "/reports/daily-sales" (GET), "/reports/food-usage" (GET). Do NOT edit tests/conftest.py.
