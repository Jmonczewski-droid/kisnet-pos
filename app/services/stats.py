from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import LABOR_RATE_CENTS_PER_HOUR
from app.core.time import utcnow
from app.models import Order, OrderItem, TimeEntry


def _business_day(day: Optional[date]):
    """Local calendar day (default today) as (date, start, end) in naive UTC."""
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    day = day or datetime.now(tz).date()
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    to_utc = lambda moment: moment.astimezone(timezone.utc).replace(tzinfo=None)
    return day, to_utc(start_local), to_utc(start_local + timedelta(days=1)), start_local


def day_stats(session: Session, day: Optional[date]) -> dict:
    """Sales, labor and labor % for one business day, by hour."""
    day, start, end, start_local = _business_day(day)
    now = utcnow()
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    hour_starts = [start + timedelta(hours=k) for k in range(24)]  # naive UTC hour boundaries

    # Sales: non-voided lines sent during the day, bucketed by local hour
    sales_by_hour = [0] * 24
    lines = (
        session.query(OrderItem)
        .filter(OrderItem.sent_at >= start, OrderItem.sent_at < end, OrderItem.voided == False)  # noqa: E712
        .all()
    )
    for line in lines:
        hour_index = int((line.sent_at - start).total_seconds() // 3600)
        sales_by_hour[hour_index] += line.unit_price_cents * line.qty

    # Labor: each employee on the clock is costed at the hourly rate for the time inside each hour
    labor_by_hour = [0.0] * 24
    entries = (
        session.query(TimeEntry)
        .filter(TimeEntry.clocked_in_at < end)
        .filter((TimeEntry.clocked_out_at == None) | (TimeEntry.clocked_out_at > start))  # noqa: E711
        .all()
    )
    for entry in entries:
        shift_start = max(entry.clocked_in_at, start)
        shift_end = min(entry.clocked_out_at or now, end)
        for k, hour_start in enumerate(hour_starts):
            hour_end = hour_start + timedelta(hours=1)
            overlap = (min(shift_end, hour_end) - max(shift_start, hour_start)).total_seconds()
            if overlap > 0:
                labor_by_hour[k] += overlap / 3600 * LABOR_RATE_CENTS_PER_HOUR

    labor_by_hour = [round(value) for value in labor_by_hour]
    now_local = datetime.now(tz)
    current_k = int((now - start).total_seconds() // 3600) if day == now_local.date() else None
    active = [k for k in range(24) if sales_by_hour[k] or labor_by_hour[k]]
    if current_k is not None:
        active.append(current_k)
    first, last = (min(active), max(active)) if active else (0, -1)

    rows = []
    for k in range(first, last + 1):
        sales, labor = sales_by_hour[k], labor_by_hour[k]
        rows.append({
            "hour": (start_local + timedelta(hours=k)).strftime("%H:00"),
            "sales_cents": sales,
            "labor_cents": labor,
            "labor_pct": round(labor * 100 / sales, 1) if sales else None,
        })

    total_sales = sum(sales_by_hour)
    total_labor = sum(labor_by_hour)
    return {
        "date": day,
        "sales_cents": total_sales,
        "labor_cents": total_labor,
        "labor_pct": round(total_labor * 100 / total_sales, 1) if total_sales else None,
        "active_tickets": session.query(func.count(Order.id)).filter(Order.status == "open").scalar(),
        "hours": rows,
    }
