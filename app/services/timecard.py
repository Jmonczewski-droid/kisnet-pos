from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.models import Employee, TimeEntry


def week_bounds(day: Optional[date]) -> tuple[date, datetime, datetime]:
    """Monday of the week containing `day` (default today), and its start/end as naive UTC datetimes."""
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    day = day or datetime.now(tz).date()
    monday = day - timedelta(days=day.weekday())
    start_local = datetime.combine(monday, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=7)
    to_utc = lambda moment: moment.astimezone(timezone.utc).replace(tzinfo=None)
    return monday, to_utc(start_local), to_utc(end_local)


def _hours_in_window(entry: TimeEntry, window_start: datetime, window_end: datetime, now: datetime) -> float:
    start = max(entry.clocked_in_at, window_start)
    end = min(entry.clocked_out_at or now, window_end)
    return round(max(0.0, (end - start).total_seconds()) / 3600, 2)


def _week_entries(session: Session, employee_id: int, window_start: datetime, window_end: datetime) -> list[TimeEntry]:
    return (
        session.query(TimeEntry)
        .filter(TimeEntry.employee_id == employee_id)
        .filter(TimeEntry.clocked_in_at < window_end)
        .filter((TimeEntry.clocked_out_at == None) | (TimeEntry.clocked_out_at > window_start))  # noqa: E711
        .order_by(TimeEntry.clocked_in_at)
        .all()
    )


def employee_week(session: Session, employee: Employee, day: Optional[date]) -> dict:
    monday, window_start, window_end = week_bounds(day)
    now = utcnow()
    entries = _week_entries(session, employee.id, window_start, window_end)
    rows = [
        {
            "clocked_in_at": entry.clocked_in_at,
            "clocked_out_at": entry.clocked_out_at,
            "hours": _hours_in_window(entry, window_start, window_end, now),
        }
        for entry in entries
    ]
    return {
        "week_start": monday,
        "week_end": monday + timedelta(days=6),
        "employee": {"id": employee.id, "code": employee.code, "name": employee.name, "role": employee.role},
        "entries": rows,
        "total_hours": round(sum(row["hours"] for row in rows), 2),
    }


def weekly_summary(session: Session, day: Optional[date]) -> dict:
    monday, window_start, window_end = week_bounds(day)
    now = utcnow()
    rows = []
    for employee in session.query(Employee).order_by(Employee.name).all():
        entries = _week_entries(session, employee.id, window_start, window_end)
        hours = round(sum(_hours_in_window(entry, window_start, window_end, now) for entry in entries), 2)
        if entries:
            rows.append({
                "employee_id": employee.id,
                "code": employee.code,
                "name": employee.name,
                "role": employee.role,
                "total_hours": hours,
                "on_clock": any(entry.clocked_out_at is None for entry in entries),
            })
    return {"week_start": monday, "week_end": monday + timedelta(days=6), "rows": rows}
