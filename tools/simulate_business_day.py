#!/usr/bin/env python3
"""
Run one business day of orders through the app, then spread its timestamps across the day.

Tickets are created through the same API the screens use (table parties by the host and servers,
bar parties by the bartender, kitchen and bar bumps, closing tables). The clock times are then moved so the
day runs from opening to close, which makes the sales and labor reports read like a real day.

Usage:
    DATABASE_URL=sqlite:////tmp/sim.db venv/bin/python tools/simulate_business_day.py --tickets 100 --check
"""
import argparse
import random
import sys
from time import sleep
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.constants import BAR_SEATS, TABLE_SEATS  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Employee, MenuItem, Order, OrderItem, Party, TimeEntry  # noqa: E402
from app.services.auth import AuthError, clock_in  # noqa: E402

PIN = "1234"
SERVER_CODES = ("SRV1", "SRV2", "SRV3", "SRV4")
FOOD_TRACKS = ("cold", "appetizers", "hot")
OPENING = (11, 0)       # first ticket opens at or after 11:00 local
LAST_OPENING = (21, 30)  # last ticket opens at or before 21:30 local
SHIFT = ((10, 45), (22, 15))  # every employee's shift, local time


def local_to_utc(day: date, hour: int, minute: int = 0) -> datetime:
    """A local wall-clock time on the business day as naive UTC (what the app stores)."""
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    local = datetime.combine(day, time(hour, minute), tzinfo=tz)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def day_window(day: date):
    return local_to_utc(day, 0), local_to_utc(day + timedelta(days=1), 0)


def call(client: TestClient, method: str, path: str, token: str, **kwargs):
    """Make one API call as the given employee; any error stops the run with the server's message."""
    response = client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} returned {response.status_code}: {response.text}")
    return response.json()


def login_everyone(client: TestClient, db) -> dict:
    """Clock the simulated staff in (if not already), then log each one in. Returns code -> token.

    ADM1 is left alone: logging in again replaces an employee's session, so the admin login stays free
    for someone watching the screens.
    """
    tokens = {}
    for employee in db.query(Employee).filter(Employee.code != "ADM1").all():
        try:
            clock_in(db, employee.code, PIN)
        except AuthError:
            pass  # already on the clock
        response = client.post("/api/v1/auth/login", json={"code": employee.code, "pin": PIN})
        if response.status_code != 200:
            raise RuntimeError(f"login {employee.code} failed: {response.text}")
        tokens[employee.code] = response.json()["token"]
    return tokens


def _menu_query(db):
    return db.query(MenuItem).filter(MenuItem.active == True)  # noqa: E712


def run_tickets(client: TestClient, db, tokens: dict, count: int, leave_open: int, rng: random.Random,
                pause: float = 0.0, delay: float = 0.0) -> list:
    """Create and serve `count` tickets. The last `leave_open` stay open at the end of the day.

    pause: seconds between sending a ticket and bumping it (so it shows on the kitchen and bar screens).
    delay: seconds between tickets.
    """
    menu = [{"id": m.id, "category": m.category} for m in _menu_query(db)]
    food = [m for m in menu if m["category"] != "bar"]
    drinks = [m for m in menu if m["category"] == "bar"]
    server_ids = {code: db.query(Employee).filter_by(code=code).one().id for code in SERVER_CODES}
    free_table, free_bar = list(TABLE_SEATS), list(BAR_SEATS)
    tickets = []

    for index in range(count):
        keep_open = index >= count - leave_open
        is_bar = rng.random() < 0.4
        if is_bar:
            seat = free_bar.pop(rng.randrange(len(free_bar)))
            party = call(client, "POST", "/api/v1/parties", tokens["BAR1"],
                         json={"seat": seat, "party_name": f"Bar guest {index + 1}"})
            serving_token = closing_token = tokens["BAR1"]
            lines = [rng.choice(drinks) for _ in range(rng.randint(1, 3))]
        else:
            seat = free_table.pop(rng.randrange(len(free_table)))
            server_code = rng.choice(SERVER_CODES)
            party = call(client, "POST", "/api/v1/parties", tokens["HOST1"],
                         json={"seat": seat, "party_name": f"Guest {index + 1}",
                               "party_size": rng.randint(1, 6), "server_id": server_ids[server_code]})
            serving_token = tokens[server_code]
            closing_token = tokens["HOST1"]
            lines = [rng.choice(food + drinks) for _ in range(rng.randint(1, 4))]

        order = call(client, "POST", f"/api/v1/parties/{party['id']}/send", serving_token,
                     json={"items": [{"menu_item_id": m["id"], "qty": rng.randint(1, 2), "notes": None} for m in lines],
                           "updates": [], "voids": []})
        if rng.random() < 0.2:  # a second round for some tickets
            extra = rng.choice(food + drinks)
            order = call(client, "POST", f"/api/v1/parties/{party['id']}/send", serving_token,
                         json={"items": [{"menu_item_id": extra["id"], "qty": 1, "notes": None}],
                               "updates": [], "voids": []})

        sleep(pause)
        # Kitchen and bar bump every track this ticket has items on
        tracks = {item["category"] for item in order["items"]}
        for track in sorted(tracks & set(FOOD_TRACKS)):
            call(client, "POST", f"/api/v1/tickets/{order['id']}/{track}/bump", tokens["KIT1"])
        if "bar" in tracks:
            call(client, "POST", f"/api/v1/tickets/{order['id']}/bar/bump", tokens["BAR1"])

        if not keep_open:
            sleep(pause)
            call(client, "POST", f"/api/v1/parties/{party['id']}/close", closing_token)
            (free_bar if is_bar else free_table).append(seat)
        tickets.append({"party_id": party["id"], "order_id": order["id"], "closed": not keep_open})
        sleep(delay)
    return tickets


def backdate(db, tickets: list, day: date, rng: random.Random, first_entry_id: int) -> None:
    """Spread the day's tickets, item times and shifts across the business day."""
    start_minute = OPENING[0] * 60 + OPENING[1]
    end_minute = LAST_OPENING[0] * 60 + LAST_OPENING[1]
    opening_minutes = sorted(rng.randint(start_minute, end_minute) for _ in tickets)

    for ticket, minute in zip(tickets, opening_minutes):
        opened = local_to_utc(day, minute // 60, minute % 60)
        party = db.get(Party, ticket["party_id"])
        order = db.get(Order, ticket["order_id"])
        party.opened_at = opened
        order.opened_at = opened
        for item in order.items:
            item.sent_at = opened + timedelta(minutes=rng.randint(0, 20))
            if item.bumped_at is not None:
                item.bumped_at = item.sent_at + timedelta(minutes=rng.randint(5, 15))
        if ticket["closed"]:
            completed = opened + timedelta(minutes=rng.randint(30, 60))
            order.status = "completed"
            order.completed_at = completed
            party.closed_at = completed

    for entry in db.query(TimeEntry).filter(TimeEntry.id >= first_entry_id).all():
        entry.clocked_in_at = local_to_utc(day, *SHIFT[0])
        entry.clocked_out_at = local_to_utc(day, *SHIFT[1])
    db.commit()


def check(db, tickets: list, day: date, leave_open: int) -> bool:
    """Verify the backdated day. Prints each result and returns True only if all pass."""
    start, end = day_window(day)
    orders = db.query(Order).filter(Order.opened_at >= start, Order.opened_at < end).all()
    open_orders = sum(1 for order in orders if order.status == "open")
    completed = sum(1 for order in orders if order.status == "completed")
    sales = sum(item.unit_price_cents * item.qty for order in orders for item in order.items if not item.voided)
    outside = db.query(OrderItem).filter((OrderItem.sent_at < start) | (OrderItem.sent_at >= end)).count()
    checks = [
        ("tickets for the day", len(orders) == len(tickets), f"{len(orders)} of {len(tickets)}"),
        ("still open", open_orders == leave_open, f"{open_orders} of {leave_open}"),
        ("completed", completed == len(tickets) - leave_open, f"{completed}"),
        ("sales above zero", sales > 0, f"${sales / 100:.2f}"),
        ("times inside the day", outside == 0, f"{outside} outside"),
    ]
    for name, passed, detail in checks:
        print(f"{'ok  ' if passed else 'FAIL'} {name}: {detail}")
    passed_all = all(passed for _, passed, _ in checks)
    print("CHECK PASSED" if passed_all else "CHECK FAILED")
    return passed_all


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickets", type=int, default=100)
    parser.add_argument("--leave-open", type=int, default=5)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--live", action="store_true",
                        help="keep real times (no backdating) so the orders show on the screens as they happen")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between send, bump and close")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between tickets")
    args = parser.parse_args(argv)

    day = args.date or datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date()
    rng = random.Random(args.seed)
    client = TestClient(app)
    db = SessionLocal()
    try:
        first_entry_id = (db.query(func.max(TimeEntry.id)).scalar() or 0) + 1
        tokens = login_everyone(client, db)
        tickets = run_tickets(client, db, tokens, args.tickets, args.leave_open, rng,
                              pause=args.pause, delay=args.delay)
        if not args.live:
            backdate(db, tickets, day, rng, first_entry_id)

        completed = sum(1 for t in tickets if t["closed"])
        print(f"Business day {day.isoformat()}: {len(tickets)} tickets, {completed} closed, "
              f"{len(tickets) - completed} still open.")
        if args.check and not args.live:
            return 0 if check(db, tickets, day, args.leave_open) else 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
