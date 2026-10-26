# KISnet-POS

Lightweight restaurant POS: FastAPI backend, SQLAlchemy/Alembic, and a no-build vanilla JS front end.
Stations: Admin (Command Center + Reports), Host, Server, Bar, Kitchen. Spec: `docs/KISnet-POS.txt`
and `docs/KISnet-POS-Requirements.md`.

## Setup

```bash
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m app.cli reset-db      # creates tables (Alembic) and loads seed data
venv/bin/python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and clock in with a seed code and PIN.

- `DATABASE_URL` (env or `.env`) defaults to `sqlite:///./app.db`. PostgreSQL works via a SQLAlchemy URL
  but is not tested here.
- `python -m app.cli reset-db` wipes all data and reloads the seed. `python -m app.cli seed` only seeds empty tables.

## Seed logins (change before real use)

| Code  | Name           | Station       |
|-------|----------------|---------------|
| HOST1 | Emma Carter    | Host          |
| SRV1  | Michael Brooks | Server        |
| KIT1  | Carlos Diaz    | Kitchen       |
| BAR1  | Jessica Moore  | Bar           |
| ADM1  | Linda Park     | Admin         |

Every seed PIN is `1234`.

## Tests

```bash
venv/bin/python -m pytest -q
```

Tests use a temporary SQLite database and never touch `app.db`. `tests/test_mvp_flow.py` runs the acceptance
scenario from the requirements (A11) through the HTTP API.

## Decisions on the open points (requirements A10)

1. **On the clock:** clocking in is the login. Each login opens a time entry; clocking out (from a station or
   by the admin in Command Center) closes it. Logging in again as the same person replaces the open entry and
   invalidates the old token, so a lost browser session can sign straight back in.
   After 5 minutes with no input the page signs out and returns to login; signing in again opens the same page.
   The employee stays on the clock until they clock out or are cleared by an admin.
2. **Completing an order:** the server (or bartender for bar seats, or admin) marks it complete on their screen.
3. **Kitchen finish:** Bump clears a whole ticket (one order, one track) at once.
4. **Clearing a table:** the host (or bartender for Z seats, or admin) closes the party once its order is complete.
5. **Bar tickets:** drink items appear as a ticket list on the Bar screen, alongside the Z1–Z10 circles.

## Section B suggestions adopted

Money in integer cents, PIN hashing (PBKDF2), item name/price/recipe snapshots at sale time, `location_id` on
records (default 1), server-side timestamps, edits after send marked `CHANGED`/`NEW` on the kitchen ticket,
removed items shown as `VOID` until bumped, and the `reset-db` command. Not adopted yet: nightly backups, payments.

## API

Base path `/api/v1`. Interactive docs at `/docs`.

- `auth`: `POST /auth/clock-in`, `POST /auth/clock-out`, `GET /auth/me`
- `seats`, `parties`: `GET /seats`, `GET|POST /parties`, `GET /parties/{id}`, `POST /parties/{id}/close`
- `orders`: `POST /parties/{id}/items`, `PATCH|DELETE /order-items/{id}`, `POST /parties/{id}/complete`
- `tickets`: `GET /tickets?track=appetizers|hot|cold|bar`, `POST /tickets/{order_id}/{track}/bump`
- `menu`: `GET /menu`, `GET /menu/export`, `POST /menu/import` (raw CSV body, admin)
- `admin`: `GET /employees?role=`, `GET /admin/on-clock`, `POST /admin/clock-out/{employee_id}`
- `reports` (admin): `GET /reports/daily-sales`, `GET /reports/food-usage` (both take `start` and `end` as YYYY-MM-DD)

## Layout

```
app/
  api/        routes and auth dependencies
  core/       settings, constants, security, time
  db/         engine and session
  models/     SQLAlchemy models
  schemas/    Pydantic request/response models
  services/   business rules (orders, parties, tickets, reports, menu import, seed)
  seed/menu.csv   seed menu with generic recipes (placeholders to review)
  static/     front end (index.html, app.js, styles.css)
alembic/      migrations (0001_initial)
tests/
.qwen/        task queue and conventions used to generate the code
```

## Known limits

- The front end was checked for JavaScript syntax only; it has not been exercised in a browser.
- The Kitchen and Command Center screens poll every 2–10 seconds rather than pushing updates.
- Seed recipes are generic placeholders; quantities should be checked against your real recipes.
- `TEST_REPORT.md`, `FINAL_PHASE2_VERIFICATION.md`, and `verify_phase2_functionality.py` describe the earlier
  placeholder code and are out of date.
