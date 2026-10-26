import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Order, OrderItem
from app.services.stats import _business_day, day_stats


def _day_items(session: Session, day):
    """Non-voided lines sent during the business day."""
    _, start, end, _ = _business_day(day)
    return (
        session.query(OrderItem)
        .filter(OrderItem.sent_at >= start, OrderItem.sent_at < end, OrderItem.voided == False)  # noqa: E712
    )


def day_summary(session: Session, day) -> dict:
    """Total sales, number of tickets and average ticket for one business day."""
    day, _, _, _ = _business_day(day)
    lines = _day_items(session, day).all()
    total = sum(line.unit_price_cents * line.qty for line in lines)
    tickets = len({line.order_id for line in lines})
    return {
        "date": day,
        "total_sales_cents": total,
        "ticket_count": tickets,
        "average_ticket_cents": round(total / tickets) if tickets else 0,
    }


def item_sales(session: Session, day) -> dict:
    """How many of each item sold, most popular first. Food and drink are split into separate lists."""
    day, _, _, _ = _business_day(day)
    rows = (
        _day_items(session, day)
        .with_entities(OrderItem.name, OrderItem.category,
                       func.sum(OrderItem.qty), func.sum(OrderItem.qty * OrderItem.unit_price_cents))
        .group_by(OrderItem.name, OrderItem.category)
        .all()
    )
    items = [
        {"name": name, "category": category, "qty": int(qty), "sales_cents": int(sales)}
        for name, category, qty, sales in rows
    ]
    items.sort(key=lambda item: (-item["qty"], item["name"]))
    return {
        "date": day,
        "drinks": [item for item in items if item["category"] == "bar"],
        "food": [item for item in items if item["category"] != "bar"],
    }


def end_of_day(session: Session, day) -> dict:
    """Write the day's summary, item sales and hourly figures as CSV files; returns the folder and files."""
    summary = day_summary(session, day)
    items = item_sales(session, day)
    hours = day_stats(session, day)["hours"]
    folder = Path(settings.EXPORT_DIR) / summary["date"].isoformat()
    folder.mkdir(parents=True, exist_ok=True)

    files = {}
    with open(folder / "summary.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "total_sales", "tickets", "average_ticket"])
        writer.writerow([summary["date"].isoformat(), f"{summary['total_sales_cents'] / 100:.2f}",
                         summary["ticket_count"], f"{summary['average_ticket_cents'] / 100:.2f}"])
    files["summary"] = str(folder / "summary.csv")

    with open(folder / "item_sales.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["type", "item", "qty", "sales"])
        for kind, rows in (("food", items["food"]), ("drink", items["drinks"])):
            for row in rows:
                writer.writerow([kind, row["name"], row["qty"], f"{row['sales_cents'] / 100:.2f}"])
    files["item_sales"] = str(folder / "item_sales.csv")

    with open(folder / "hourly.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hour", "sales", "labor", "labor_pct"])
        for row in hours:
            writer.writerow([row["hour"], f"{row['sales_cents'] / 100:.2f}", f"{row['labor_cents'] / 100:.2f}",
                             "" if row["labor_pct"] is None else row["labor_pct"]])
    files["hourly"] = str(folder / "hourly.csv")

    weekly = _maybe_weekly_report(session, summary["date"])
    return {"date": summary["date"].isoformat(), "folder": str(folder), "files": files, "weekly": weekly}


def _export_root() -> Path:
    return Path(settings.EXPORT_DIR)


def _saved_days(root: Path) -> list:
    """Business days already saved (folders named YYYY-MM-DD), oldest first."""
    if not root.exists():
        return []
    days = []
    for child in root.iterdir():
        if child.is_dir():
            try:
                days.append(date.fromisoformat(child.name))
            except ValueError:
                pass
    return sorted(days)


def last_weekly_end(root: Path) -> Optional[date]:
    """End day of the most recent weekly report, or None if there is none yet."""
    weekly = root / "weekly"
    if not weekly.exists():
        return None
    ends = [date.fromisoformat(child.name.split("_to_")[1]) for child in weekly.iterdir()
            if child.is_dir() and "_to_" in child.name]
    return max(ends) if ends else None


def _maybe_weekly_report(session: Session, day) -> Optional[dict]:
    """Create a weekly report when 7 days have passed since the last one (or since the first saved day)."""
    root = _export_root()
    saved = _saved_days(root)
    if not saved:
        return None
    base = last_weekly_end(root) or (saved[0] - timedelta(days=1))
    if (day - base).days >= 7:
        return weekly_report(session, day)
    return None


def weekly_report(session: Session, end_day) -> dict:
    """The 7 business days ending on end_day: summary per day, items and hourly totals, same categories as daily."""
    start_day = end_day - timedelta(days=6)
    days = [start_day + timedelta(days=offset) for offset in range(7)]

    per_day = [day_summary(session, day) for day in days]
    item_totals = {}
    hour_totals = {}
    for day in days:
        day_items = item_sales(session, day)
        for kind, rows in (("food", day_items["food"]), ("drink", day_items["drinks"])):
            for row in rows:
                key = (kind, row["name"])
                qty, sales = item_totals.get(key, (0, 0))
                item_totals[key] = (qty + row["qty"], sales + row["sales_cents"])
        for row in day_stats(session, day)["hours"]:
            sales, labor = hour_totals.get(row["hour"], (0, 0))
            hour_totals[row["hour"]] = (sales + row["sales_cents"], labor + row["labor_cents"])

    folder = _export_root() / "weekly" / f"{start_day.isoformat()}_to_{end_day.isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)

    total = sum(entry["total_sales_cents"] for entry in per_day)
    tickets = sum(entry["ticket_count"] for entry in per_day)
    with open(folder / "summary.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "total_sales", "tickets", "average_ticket"])
        for entry in per_day:
            writer.writerow([entry["date"].isoformat(), f"{entry['total_sales_cents'] / 100:.2f}",
                             entry["ticket_count"], f"{entry['average_ticket_cents'] / 100:.2f}"])
        writer.writerow(["TOTAL", f"{total / 100:.2f}", tickets,
                         f"{(total / tickets / 100) if tickets else 0:.2f}"])

    with open(folder / "item_sales.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["type", "item", "qty", "sales"])
        rows = sorted(item_totals.items(), key=lambda entry: (entry[0][0] != "food", -entry[1][0], entry[0][1]))
        for (kind, name), (qty, sales) in rows:
            writer.writerow([kind, name, qty, f"{sales / 100:.2f}"])

    with open(folder / "hourly.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hour", "sales", "labor", "labor_pct"])
        for hour in sorted(hour_totals):
            sales, labor = hour_totals[hour]
            writer.writerow([hour, f"{sales / 100:.2f}", f"{labor / 100:.2f}",
                             round(labor * 100 / sales, 1) if sales else ""])

    return {"start": start_day.isoformat(), "end": end_day.isoformat(), "folder": str(folder)}
