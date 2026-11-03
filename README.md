# KISnet-POS

A restaurant point-of-sale (POS) system built around how a dining room actually runs: guests are seated, orders are placed and changed, the kitchen and bar work their tickets, tables are cleared, and the manager sees sales, labor, and food usage at the end of the day.

## Why I built it

I spent 16 years running restaurants: as a General Manager, as a training-store manager, and as an Area Supervisor over as many as six locations. In that time I opened new stores, led technology installations, and trained managers and crews on the systems they used every shift. I saw firsthand where a POS helps a crew and where it gets in the way.

KISnet-POS is my answer to that. I wrote the workflow document first, as an operator, describing each station the way the people working it would describe it. Then I built the software to match that document, not the other way around. The original workflow is in [`docs/KISnet-POS.txt`](docs/KISnet-POS.txt), and the formal requirements derived from it are in [`docs/KISnet-POS-Requirements.md`](docs/KISnet-POS-Requirements.md).

## What it does

| Station | What the employee sees and does |
|---|---|
| **Host** | A 4x4 floor map (tables A1-D4). Creates a party with table, assigned server, name, and party size, which starts the table's timer. |
| **Server** | A drop-down of only their assigned tables. Places and edits orders; drinks route to the bar and food routes to the kitchen automatically. |
| **Bar** | Ten bar seats (Z1-Z10) plus a live drink-ticket list. Bartenders seat their own guests and ring their own orders. |
| **Kitchen** | Three ticket tracks (Appetizers, Hot, Cold) with running ticket times and table numbers. Changes after send are flagged `CHANGED`/`NEW`; removed items show as `VOID`. |
| **Admin** | A Command Center showing who is on the clock, plus menu and recipe management, employee lifecycle (edit, deactivate, archive), time cards, and daily sales and food-usage reports. |

Every employee clocks in with their own code and PIN and lands on the screen for their job.

## Built for real operations

- **Accurate money:** all prices and totals are stored in whole cents, so there are no rounding errors in sales reports.
- **Price snapshots:** each item's name, price, and recipe are saved at the moment of sale, so changing the menu never rewrites past sales.
- **Secure logins:** employee PINs are hashed (PBKDF2), never stored as plain text.
- **Food-usage reporting:** recipes are stored with ingredient quantities, so sales turn directly into a food-usage report, the same way a manager tracks food cost.
- **Labor tracking:** clock-in/out, weekly hours per employee, and an admin view of everyone's hours.
- **Multi-location ready:** records carry a location ID so the system can grow beyond one store.
- **Business-day simulation:** [`tools/simulate_business_day.py`](tools/simulate_business_day.py) runs a full day of tickets through the same API the screens use, so reports can be checked against a realistic day.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic migrations, Pydantic
- **Database:** SQLite by default; PostgreSQL can be configured through a SQLAlchemy URL (not yet tested)
- **Front end:** plain HTML, CSS, and JavaScript, with no build step
- **Testing:** 98 automated tests with pytest, including an end-to-end acceptance test of the full workflow through the HTTP API

## How it was built

I acted as product owner and project manager, and used AI coding agents and local language models as the development team. I broke the requirements into a queue of small, numbered tasks with shared conventions (see [`.qwen/`](.qwen/)). Each task had a defined scope and had to pass its tests before it was accepted; tasks that failed were sent back with written feedback. This is the same approach I used for store rollouts: clear standards, small steps, and checking the result before moving on.

## Screenshots

<!-- Add screenshots here, e.g. ![Host screen](docs/screenshots/host.png) -->
Coming soon.

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

1. **Party system shared with Bar and Server**
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
- `timecard`: `GET /timecard?week=` (own entries and hours for the week; defaults to this week in business time), `GET /timecard/summary?week=` (admin: every employee's hours that week)
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

## Roadmap

- Payments and checkout
- Nightly database backups
- Long-term load testing of the system and database
