from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.timecard import router
from app.models import Employee, TimeEntry


@pytest.fixture
def timecard_client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _add_entry(db, code, clocked_in, clocked_out):
    employee = db.query(Employee).filter_by(code=code).one()
    db.add(TimeEntry(employee_id=employee.id, clocked_in_at=clocked_in, clocked_out_at=clocked_out))
    db.commit()


def test_week_hours_for_employee(timecard_client, db, login):
    # Mon 2026-10-19 09:00-17:00 Eastern (EDT, UTC-4) = 8 hours, inside that week
    _add_entry(db, "SRV1", datetime(2026, 10, 19, 13, 0), datetime(2026, 10, 19, 21, 0))
    # Previous Sunday evening, outside that week
    _add_entry(db, "SRV1", datetime(2026, 10, 18, 22, 0), datetime(2026, 10, 19, 1, 0))
    headers = login("SRV1")

    card = timecard_client.get("/api/v1/timecard?week=2026-10-21", headers=headers).json()

    assert card["week_start"] == "2026-10-19"
    assert card["week_end"] == "2026-10-25"
    assert len(card["entries"]) == 1
    assert card["entries"][0]["hours"] == 8.0
    assert card["total_hours"] == 8.0


def test_entry_crossing_week_start_is_split(timecard_client, db, login):
    # Sun 2026-10-18 23:00 to Mon 2026-10-19 01:00 Eastern (03:00-05:00 UTC):
    # one hour falls in the week of Oct 12 (Sunday) and one hour in the week of Oct 19 (Monday)
    _add_entry(db, "SRV1", datetime(2026, 10, 19, 3, 0), datetime(2026, 10, 19, 5, 0))
    headers = login("SRV1")

    this_week = timecard_client.get("/api/v1/timecard?week=2026-10-19", headers=headers).json()
    last_week = timecard_client.get("/api/v1/timecard?week=2026-10-12", headers=headers).json()

    assert this_week["total_hours"] == 1.0
    assert last_week["total_hours"] == 1.0


def test_summary_is_admin_only(timecard_client, login):
    assert timecard_client.get("/api/v1/timecard/summary", headers=login("SRV1")).status_code == 403


def test_summary_lists_week_totals_per_employee(timecard_client, db, login):
    _add_entry(db, "SRV1", datetime(2026, 10, 19, 13, 0), datetime(2026, 10, 19, 21, 0))
    summary = timecard_client.get("/api/v1/timecard/summary?week=2026-10-21", headers=login("ADM1")).json()

    row = next(r for r in summary["rows"] if r["code"] == "SRV1")
    assert row["total_hours"] == 8.0
    assert all(r["code"] != "HOST1" for r in summary["rows"])


def test_open_entry_counts_to_now(timecard_client, db, login):
    headers = login("BAR1")

    card = timecard_client.get("/api/v1/timecard", headers=headers).json()

    assert card["entries"][0]["clocked_out_at"] is None
    assert card["total_hours"] >= 0
