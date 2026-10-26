# KISnet-POS — shared conventions (read before every task)

Source docs: docs/KISnet-POS.txt and docs/KISnet-POS-Requirements.md. Follow the names below EXACTLY;
other tasks import them.

## Stack / rules
- Python 3.12. Tests: `venv/bin/python -m pytest -q <files>`. Run from repo root.
- Pinned deps only (requirements.txt). Do NOT add dependencies. Use stdlib (hashlib, secrets, csv, zoneinfo).
- FastAPI 0.109, SQLAlchemy 2.0 (`DeclarativeBase` from `sqlalchemy.orm`, `Mapped`, `mapped_column`, `Session.get`, `select()`),
  Pydantic 2.5 (`model_config = ConfigDict(from_attributes=True)`, NOT `class Config`).
- Settings: `class Settings(BaseSettings)` from pydantic_settings (NOT BaseModel).
- Money is INTEGER CENTS, field suffix `_cents`. Quantities are float.
- Datetimes stored as naive UTC via `app.core.time.utcnow()`. API returns ISO strings.
- Never write `.env`, `data/`, `venv/`, `.qwen/`. Never print secrets.
- No `datetime.utcnow()` (deprecated); use `utcnow()`.
- Keep code short, idiomatic, no dead code, no placeholder comments.
- Only create/modify the files listed in your task's allowed list. Anything else is reverted.

## Package layout (all paths under repo root)
- `app/__init__.py`
- `app/core/config.py` — `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`,
  fields: `PROJECT_NAME="KISnet-POS"`, `API_V1_STR="/api/v1"`, `DATABASE_URL="sqlite:///./app.db"`,
  `BUSINESS_TIMEZONE="America/New_York"`. Module-level `settings = Settings()`.
- `app/core/constants.py` — `ROLES = ("admin","host","server","bartender","kitchen")`,
  `CATEGORIES = ("bar","appetizers","hot","cold")` (= kitchen/bar tracks), `TRACKS = CATEGORIES`,
  `CATEGORY_LABELS = {"bar":"Bar","appetizers":"Appetizers","hot":"Hot","cold":"Cold"}`,
  `TABLE_SEATS = [f"{r}{c}" for r in "ABCD" for c in "1234"]`, `BAR_SEATS = [f"Z{i}" for i in range(1,11)]`,
  `ALL_SEATS = TABLE_SEATS + BAR_SEATS`. Bar seats are exactly the ones starting with "Z".
- `app/core/time.py` — `utcnow() -> datetime` (naive UTC).
- `app/core/security.py` — `hash_pin(pin: str) -> str` (pbkdf2_hmac sha256, 200_000 iters, random salt,
  stored as `"pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>"`), `verify_pin(pin: str, stored: str) -> bool`
  (constant time via hmac.compare_digest; malformed stored -> False), `new_token() -> str` (secrets.token_urlsafe(32)),
  `hash_token(token: str) -> str` (sha256 hexdigest).
- `app/db/base.py` — `class Base(DeclarativeBase)` (import DeclarativeBase from sqlalchemy.orm), `engine = create_engine(settings.DATABASE_URL,
  connect_args={"check_same_thread": False} if sqlite else {}, pool_pre_ping=True)`,
  `SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)`,
  `def get_db()` generator yielding a session and closing it.
- `app/models/` — one module per group; `app/models/__init__.py` imports ALL model classes so
  `Base.metadata` is complete.
  - `employee.py`: `Employee` table `employees`: id (pk), location_id (int, default 1),
    number (int, backend numbering, unique per location), code (str, unique, e.g. "HOST1"),
    name (str), role (str), pin_hash (str), active (bool, default True).
  - `time_entry.py`: `TimeEntry` table `time_entries`: id, employee_id (FK employees.id, indexed),
    clocked_in_at (datetime), clocked_out_at (datetime, nullable), token_hash (str, unique, nullable).
    Open entry = clocked_out_at IS NULL.
  - `menu.py`: `MenuItem` table `menu_items`: id, name (str, unique), category (str),
    price_cents (int), active (bool, default True). `RecipeLine` table `recipe_lines`: id,
    menu_item_id (FK cascade delete), ingredient (str), qty (float), unit (str). Relationship
    `MenuItem.recipe_lines` ordered by id, cascade all, delete-orphan.
  - `party.py`: `Party` table `parties`: id, location_id (default 1), seat (str, e.g. "B2" or "Z3"),
    party_name (str), party_size (int), server_id (FK employees.id, nullable), created_by_id
    (FK employees.id), opened_at (datetime), closed_at (datetime, nullable). Open party = closed_at IS NULL.
    Relationships: `server` (Employee), `orders` (Order, ordered by id).
  - `order.py`: `Order` table `orders`: id, location_id (default 1), party_id (FK parties.id, indexed),
    status (str: "open" | "completed"), opened_at (datetime), completed_at (datetime, nullable),
    relationship `items` (OrderItem, ordered by id, cascade all).
    `OrderItem` table `order_items`: id, order_id (FK orders.id cascade delete), menu_item_id
    (FK menu_items.id, SET NULL, nullable), name (str, snapshot), category (str, snapshot),
    unit_price_cents (int, snapshot), qty (int), notes (str, nullable), changed (bool, default False;
    True when edited after it was sent), voided (bool, default False; removed from the order but kept
    so kitchen can see VOID until bumped), created_by_id (FK employees.id), sent_at (datetime),
    bumped_at (datetime, nullable). Relationship `ingredients` (OrderItemIngredient, cascade all).
    `OrderItemIngredient` table `order_item_ingredients`: id, order_item_id (FK cascade delete),
    ingredient (str), qty (float), unit (str) — a SNAPSHOT of the recipe at sale time.
- `app/schemas/` — Pydantic v2 request/response models (see API section for shapes).
- `app/services/` — business logic, functions take a `Session` as first arg.
  - `seed.py`: `seed_all(session)` idempotent: seeds employees and menu if the tables are empty.
  - `menu_import.py`: `parse_menu_csv(text) -> list[dict]`, `import_menu(session, text) -> (items, recipe_lines)`,
    `export_menu_csv(session) -> str`.
  - `auth.py`, `parties.py`, `orders.py`, `tickets.py`, `reports.py`, `admin.py` (see below).
- `app/seed/menu.csv` — seed menu (columns `name,type,ingredient,qty,unit,sales`; `type` in
  Bar/Appetizers/Hot/Cold).
- `app/api/deps.py` — `get_current_employee` (Bearer token → Employee, else 401), `require_roles(*roles)`
  dependency factory (403 if role not allowed; admin always allowed).
- `app/api/routes/` — `health.py`, `auth.py`, `seats.py`, `parties.py`, `orders.py`, `tickets.py`,
  `menu.py`, `admin.py`, `reports.py`. Each defines `router = APIRouter()`.
- `app/main.py` — `app = FastAPI(title=settings.PROJECT_NAME, openapi_url=...)`, includes routers under
  `settings.API_V1_STR`, mounts `app/static` at `/static`, `GET /` returns `app/static/index.html`.
  Health: `GET /health` and `GET /api/v1/health` return `{"status": "OK"}`.
- `app/cli.py` — `python -m app.cli reset-db` and `python -m app.cli seed`.
- `app/static/` — index.html, styles.css, app.js (vanilla JS, no build step).
- `alembic/` — env.py, script.py.mako, versions/0001_initial.py. `alembic.ini` at root.
- `tests/` — `conftest.py`, `test_*.py`.

## Tests contract (tests/conftest.py)
- Top of conftest, BEFORE importing app: `os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"`
  using `tempfile.mkdtemp()`. Tests must never touch app.db.
- Fixture `db` (function scope): `Base.metadata.drop_all(engine)`, `create_all(engine)`, `seed_all(session)`,
  yield a `SessionLocal()` session, close it.
- Fixture `client` (depends on `db`): `from app.main import app` lazily inside the fixture; yields
  `fastapi.testclient.TestClient(app)`.
- Fixture `login`: callable `login(code: str, pin: str = "1234") -> dict` that POSTs clock-in and returns
  `{"Authorization": f"Bearer {token}"}`. Cache per code within a test.
- Seed PIN for every seeded employee is `"1234"`.

## Auth
- `POST /api/v1/auth/clock-in` body `{"code": str, "pin": str}` → 200 `{"token": str, "employee": EmployeeOut}`.
  Code matched case-insensitively. Wrong code/pin/inactive → 401. Already has an open TimeEntry → 409
  ("already on the clock"). Creates TimeEntry with token_hash = hash_token(token).
- `POST /api/v1/auth/clock-out` (auth) → 200 `{"clocked_out": true}`; closes the caller's open entry.
- `GET /api/v1/auth/me` (auth) → EmployeeOut.
- `get_current_employee`: `Authorization: Bearer <token>`; looks up TimeEntry by hash_token where
  clocked_out_at IS NULL; missing/invalid → 401.
- `EmployeeOut`: `{id, code, name, role}` (number and pin_hash never returned).
- `GET /api/v1/employees?role=server` (auth) → `[EmployeeOut]` for active employees, optional `role` filter,
  sorted by name. Implemented in app/api/routes/admin.py via services/admin.py `list_employees(session, role)`.

## Seats / parties — access rules
- Roles: admin = everything. host = table seats only (create/close). server = orders only on parties where
  `server_id == me.id`. bartender = bar seats (Z) only (create/close/order). kitchen = tickets for food tracks only.
- `can_view_party(user, party)`: admin/host → True; server → party.server_id == user.id;
  bartender → party.seat in BAR_SEATS; kitchen → False.
- `can_order(user, party)`: admin → True; server → party.server_id == user.id; bartender → seat in BAR_SEATS;
  otherwise False.
- `GET /api/v1/seats` (auth) → `[{ "seat": str, "party": PartySummary | null }]` for ALL_SEATS in order,
  filtered by can_view_party (seats with no visible party still listed with party null).
- `GET /api/v1/parties?open=true` (auth) → `[PartySummary]` of open parties the caller can view.
- `POST /api/v1/parties` body `{seat, party_name, party_size (>=1), server_id?}` →
  201 PartyDetail. host: seat must be a table seat; server_id required and must be an active server.
  bartender: seat must be a bar seat; server_id ignored (null). admin: any seat, server_id optional.
  Seat code not in ALL_SEATS → 422. Seat has an open party → 409. Role not allowed → 403.
  Sets opened_at = utcnow(), created_by_id = caller.
- `GET /api/v1/parties/{id}` (auth, can_view_party) → PartyDetail. 404 if not found; 403 if not viewable.
- `POST /api/v1/parties/{id}/close` (host for table seats, bartender for bar seats, admin) → 200 PartyDetail.
  409 if an open order exists or already closed. Sets closed_at.
- `PartySummary`: `{id, seat, party_name, party_size, server_id, server_name, opened_at}`.
- `PartyDetail`: PartySummary fields + `closed_at`, `open_order: OrderOut | null`.

## Orders
- `OrderItemOut`: `{id, menu_item_id, name, category, unit_price_cents, qty, notes, changed, voided,
  bumped, sent_at, line_total_cents}` where `bumped = bumped_at is not None`,
  `line_total_cents = 0 if voided else unit_price_cents * qty`.
- `OrderOut`: `{id, party_id, status, opened_at, completed_at, total_cents, items: [OrderItemOut]}`
  where total_cents sums non-voided lines.
- `POST /api/v1/parties/{id}/items` body `{"items": [{"menu_item_id": int, "qty": int>=1, "notes": str|null}]}`
  (can_order, party must be open) → 201 OrderOut. Creates the open order if none (status "open",
  opened_at = utcnow()). Each new line: snapshots name, category, unit_price_cents from the MenuItem;
  copies the MenuItem's recipe_lines into order_item_ingredients; sent_at = utcnow(); changed = True iff the
  order ALREADY had items before this request (edit after send). Unknown or inactive menu item → 422.
- `PATCH /api/v1/order-items/{id}` body `{"qty"?: int>=1, "notes"?: str|null}` (can_order on its party)
  → OrderItemOut. 409 if bumped or voided. Changing qty sets changed = True.
- `DELETE /api/v1/order-items/{id}` (can_order) → 204. Sets voided = True. 409 if bumped or already voided.
- `POST /api/v1/parties/{id}/complete` (can_order) → OrderOut. Completes the open order: status
  "completed", completed_at = utcnow(). 409 if no open order.

## Menu
- `GET /api/v1/menu?category=` (auth) → `[{id, name, category, price_cents}]` active items sorted by name.
- `GET /api/v1/menu/export` (admin) → text/csv of all recipe lines in seed CSV format.
- `POST /api/v1/menu/import` (admin) raw body `text/csv` → 200 `{"items": int, "recipe_lines": int}`.
  Replaces recipes for each imported item name; upserts items. CSV error → 422 with the message.

## Kitchen / bar tickets
- A ticket = (order, track) with the order's items where `category == track` and `bumped_at IS NULL`
  (voided items included so kitchen sees VOID).
- `GET /api/v1/tickets?track=appetizers|hot|cold|bar` → `[{order_id, track, seat, party_name, opened_at, items: [OrderItemOut]}]`
  where opened_at = min(sent_at) of the ticket items. Only open orders. Sorted by opened_at.
  Access: kitchen → food tracks; bartender → bar; admin → all. Others 403. Invalid track → 422.
- `POST /api/v1/tickets/{order_id}/{track}/bump` → 200 `{"bumped": int}`. Sets bumped_at = utcnow() on
  the ticket's items. Same access as GET. 404 if order missing.

## Admin / command center
- `GET /api/v1/admin/on-clock` (admin) → `[{employee_id, code, name, role, clocked_in_at}]` for open entries.
- `POST /api/v1/admin/clock-out/{employee_id}` (admin) → 200 `{"clocked_out": true}`; 404 if not on clock.

## Reports (admin only)
- Date range `start` and `end` query params (YYYY-MM-DD, inclusive). Defaults: today in BUSINESS_TIMEZONE.
  Convert local day bounds to naive UTC for filtering on orders.completed_at (status "completed").
  Exclude voided items.
- `GET /api/v1/reports/daily-sales?start&end` → `{start, end, order_count, total_qty, total_sales_cents,
  rows: [{name, category, qty, sales_cents}]}` grouped by item name+category, sorted by name.
  sales_cents = sum(unit_price_cents * qty).
- `GET /api/v1/reports/food-usage?start&end` → `{start, end, rows: [{ingredient, unit, qty}]}` where
  qty = sum over non-voided items of item.qty * ingredient.qty, grouped by ingredient+unit, sorted by ingredient.

## Seed data
- Employees (number, code, name, role): 1 HOST1 Emma Carter host; 2 SRV1 Michael Brooks server;
  3 KIT1 Carlos Diaz kitchen; 4 BAR1 Jessica Moore bartender; 5 ADM1 Linda Park admin. PIN "1234" all.
  location_id 1, active True.
- Menu: `app/seed/menu.csv`.
