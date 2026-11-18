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
| **Bar** | Ten bar seats (BAR1-BAR10) plus a live drink-ticket list. Bartenders seat their own guests and ring their own orders. |
| **Kitchen** | Three ticket tracks (Appetizers, Hot, Cold) with running ticket times and table numbers. Changes after send are flagged `CHANGED`/`NEW`; removed items show as `VOID`. |
| **Admin** | A Command Center showing who is on the clock, plus menu and recipe management, employee lifecycle (edit, deactivate, archive), device management for printers and screens, time cards, and daily sales and food-usage reports. |

Every employee clocks in with their own code and PIN and lands on the screen for their job.

## Built for real operations

- **Accurate money:** all prices and totals are stored in whole cents, so there are no rounding errors in sales reports.
- **Price snapshots:** each item's name, price, and recipe are saved at the moment of sale, so changing the menu never rewrites past sales.
- **Secure logins:** employee PINs are hashed (PBKDF2), never stored as plain text. Employees set their own PIN, repeated wrong guesses lock the sign-in, and the owner can add two-step sign-in with an authenticator app.
- **Remote look-in:** a separate, locked-down portal shows today's sales and labor in real time from anywhere, behind two-step sign-in.
- **Three access levels:** Owner, Manager and Team Member, so only the owner can open the employee database.
- **Food-usage reporting:** recipes are stored with ingredient quantities, so sales turn directly into a food-usage report, the same way a manager tracks food cost.
- **Labor tracking:** clock-in/out, weekly hours per employee, and an admin view of everyone's hours.
- **Multi-location ready:** records carry a location ID so the system can grow beyond one store.
- **Runs on the devices you already have:** every screen is a web page, so PCs, Android and Apple phones and tablets all work with nothing to install.
- **Printers and ticket screens:** network kitchen, bar and receipt printers, and any spare screen as a paired ticket monitor, are set up from one Device Management screen.
- **Business-day simulation:** [`tools/simulate_business_day.py`](tools/simulate_business_day.py) runs a full day of tickets through the same API the screens use, so reports can be checked against a realistic day.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic migrations, Pydantic
- **Database:** SQLite by default; PostgreSQL can be configured through a SQLAlchemy URL (not yet tested)
- **Front end:** plain HTML, CSS, and JavaScript, with no build step
- **Testing:** 155 automated tests with pytest, including an end-to-end acceptance test of the full workflow through the HTTP API

## How it was built

I acted as product owner and project manager, and used AI coding agents and local language models as the development team. I broke the requirements into a queue of small, numbered tasks with shared conventions. Each task had a defined scope and had to pass its tests before it was accepted; tasks that failed were sent back with written feedback. This is the same approach I used for store rollouts: clear standards, small steps, and checking the result before moving on.

## Screenshots

<!-- Add screenshots here, e.g. ![Host screen](docs/screenshots/host.png) -->
Coming soon.

## Setup

```bash
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m app.cli reset-db      # creates tables (Alembic) and loads seed data
venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` lets phones, tablets and screens on the same network open the POS at this computer's
address (shown on the Device Management screen). Leave it off to keep the POS on this computer only.
For an existing database, run `venv/bin/alembic upgrade head` after updating to apply new migrations.

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
| ADM1  | Linda Park     | Admin (Owner) |

Every seed PIN is `1234`. This roster is a demo: see "Access levels and going live" before real use.

## Tests

```bash
venv/bin/python -m pytest -q
```

Tests use a temporary SQLite database and never touch `app.db`. `tests/test_mvp_flow.py` runs the acceptance
scenario from the requirements (A11) through the HTTP API.

## Decisions on the open points (requirements A10)

1. **Party system shared with Bar and Server:** Host, Server, and Bar all work from the same party record, so each seat has one party and one open order whichever station opened it.
2. **Completing an order:** the server (or bartender for bar seats, or admin) marks it complete on their screen.
3. **Kitchen finish:** Bump clears a whole ticket (one order, one track) at once.
4. **Clearing a table:** Send to Payment closes the party and completes its open order. Servers do this for their own tables, bartenders for bar seats, hosts for tables, and admins for any seat. Payment is assumed accepted; this is the hook for later payment integration.
5. **Bar tickets:** drink items appear as a ticket list on the Bar screen, alongside the BAR1–BAR10 seat circles.

## Access levels and going live

Every employee card has an access level, separate from the stations they work:

| Level | Can do |
|---|---|
| **Owner** | Everything, including database management: the employee database, recipes, menu import, devices. |
| **Manager** | Runs the restaurant: Command Center, reports, daily summary, end of day, time cards, every station. No database management. |
| **Team Member** | Works the stations on their card (Host, Server, Bar, Kitchen) and sees their own time card. |

- **Employees protect their own PIN.** The PIN on a new card, or one the owner resets, is a starter PIN: the
  first time it is used the employee must replace it with one only they know. PINs are stored hashed, so
  nobody, including the owner, can read them.
- **Lockout.** Five wrong PINs (or authenticator codes) in a row lock that sign-in for five minutes. The owner
  can unlock it sooner by issuing a new starter PIN.
- **Two-step sign-in.** Under Menu > Sign-in Security the owner and managers can require a 6-digit code from an
  authenticator app as well as the PIN. It uses the open TOTP standard, so any app works, including the
  open-source Aegis, 2FAS and Ente Auth. If the phone is lost, run
  `venv/bin/python -m app.cli reset-two-step <CODE>` on the server.
- **There is always an owner.** The last owner cannot be demoted, deactivated or archived.

To go live with a real business: run `venv/bin/python -m app.cli create-owner "Your Name"`, sign in with the
code it prints, turn on two-step sign-in, create a card for each employee, then archive the demo roster.

## Look-in portal (remote, real time)

The look-in portal lets the owner and managers see today's business from outside the restaurant, live:
sales, sales per hour, open tables and tickets, who is working and when they clocked in, labor per hour and
labor for the day. It is read-only: nothing can be changed from the portal, including clock-outs.

It runs as a **separate server with its own link**, so the rest of the POS is never exposed:

```bash
venv/bin/python -m uvicorn app.lookin_app:app --port 8001
```

- That server has the look-in page and nothing else. Ordering, employees, recipes, devices and reports do not
  exist on it, so they cannot be reached from outside.
- Sign-in is employee code + PIN + authenticator code. Two-step sign-in is required (turn it on at the
  restaurant under Menu > Sign-in Security), no clock-in is needed, and a sign-in lasts 12 hours.
- A look-in sign-in cannot be used on the POS, and a POS sign-in cannot be used on the portal.
- Point a VPN or an HTTPS tunnel (Tailscale, WireGuard, Cloudflare Tunnel) at port 8001 only. Do not expose it
  over plain HTTP, and never point the outside world at the main POS port.
- Settings (`.env`): `LOOKIN_HOURS` (default 12), `LOOKIN_REQUIRE_TWO_STEP` (default true).

The same page is also on the main POS at `#/lookin` for use inside the restaurant.

## Device management

Owner > System > **Device Management** is where printers and screens are connected.

- **Printers** are network receipt/kitchen printers (ESC/POS on port 9100). Give each one a name, its IP
  address, and what it prints: any of the Bar, Apps, Hot and Cold ticket tracks, and/or guest receipts.
  Tickets print when an order is sent (only the lines that send added, changed or voided). The guest receipt
  prints when a table is sent to payment. **Test print** checks the connection. A printer that is off or
  unreachable never blocks an order; the screen shows it as "Not responding" with the reason.
- **Monitors** turn any browser into a ticket screen with no employee login. Add a monitor, choose the tracks
  it shows, then on that device open the address shown and enter the 6-character code. Codes work once and
  expire after 10 minutes. The screen can bump its own tracks. A manager can disconnect it at any time.
- **Guest receipt layout** is the text file `app/templates/receipt.txt`. Edit it to change the header,
  footer and layout; the file explains its own rules, and the Device Management screen previews the result.
  Tax and tips are not calculated yet, so the receipt has no lines for them.

## Section B suggestions adopted

Money in integer cents, PIN hashing (PBKDF2), item name/price/recipe snapshots at sale time, `location_id` on
records (default 1), server-side timestamps, edits after send marked `CHANGED`/`NEW` on the kitchen ticket,
removed items shown as `VOID` until bumped, and the `reset-db` command. Not adopted yet: nightly backups, payments.

## API

Base path `/api/v1`. Interactive docs at `/docs`.

- `auth`: `POST /auth/clock-in`, `POST /auth/login`, `POST /auth/clock-out`, `GET /auth/me`, `POST /auth/change-pin`,
  `GET /auth/totp`, `POST /auth/totp/setup|enable|disable` (owner two-step sign-in)
- `seats`, `parties`: `GET /seats`, `GET|POST /parties`, `GET /parties/{id}`, `POST /parties/{id}/close`
- `orders`: `POST /parties/{id}/items`, `PATCH|DELETE /order-items/{id}`, `POST /parties/{id}/complete`
- `tickets`: `GET /tickets?track=appetizers|hot|cold|bar`, `POST /tickets/{order_id}/{track}/bump`
- `menu`: `GET /menu`, `GET /menu/export`, `POST /menu/import` (raw CSV body, admin)
- `timecard`: `GET /timecard?week=` (own entries and hours for the week; defaults to this week in business time), `GET /timecard/summary?week=` (admin: every employee's hours that week)
- `admin`: `GET /employees?role=`, `GET /admin/on-clock`, `POST /admin/clock-out/{employee_id}`
- `devices` (owner): `GET|POST /admin/devices`, `PATCH /admin/devices/{id}`,
  `POST /admin/devices/{id}/deactivate|reactivate|archive|pairing-code|unpair|test`, `GET /admin/receipt-preview`,
  `GET /admin/server-address`
- `devices` (a paired monitor, using its own token): `POST /devices/pair`, `GET /devices/me`, `GET /devices/tickets`,
  `POST /devices/tickets/{order_id}/{track}/bump`, `POST /devices/disconnect`
- `lookin` (owner/manager, own token, read-only): `POST /lookin/login`, `GET /lookin`, `POST /lookin/logout`
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
  templates/receipt.txt   guest receipt layout (edit this)
alembic/      migrations (0001_initial through 0006_lookin_sessions)
tests/
```

## Roadmap

- Payments and checkout
- Nightly database backups
- Long-term load testing of the system and database
