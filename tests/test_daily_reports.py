import csv
from datetime import date, datetime

import pytest

from app.core.config import settings
from app.core.time import utcnow
from app.models import Employee, MenuItem, Party
from app.schemas.order import OrderItemIn
from app.services.daily_reports import day_summary, end_of_day, item_sales
from app.services.orders import send_ticket


def _party(db, seat, name):
    server = db.query(Employee).filter_by(code="SRV1").one()
    party = Party(seat=seat, party_name=name, party_size=2, server_id=server.id,
                  created_by_id=server.id, opened_at=utcnow())
    db.add(party)
    db.commit()
    return server, party


def _menu(db, name):
    return db.query(MenuItem).filter_by(name=name).one().id


@pytest.fixture
def busy_day(db):
    """Two tickets sent today: 3 Caesar + 1 Beer, and 2 Beer + 1 Burger."""
    server, first = _party(db, "A1", "One")
    send_ticket(db, server, first, [OrderItemIn(menu_item_id=_menu(db, "Caesar Salad"), qty=3),
                                    OrderItemIn(menu_item_id=_menu(db, "Beer"), qty=1)], [], [])
    server, second = _party(db, "A2", "Two")
    send_ticket(db, server, second, [OrderItemIn(menu_item_id=_menu(db, "Beer"), qty=2),
                                     OrderItemIn(menu_item_id=_menu(db, "Burger"), qty=1)], [], [])
    return date.today()


def test_summary_counts_sales_tickets_and_average(db, busy_day):
    summary = day_summary(db, busy_day)
    # Caesar 10.00 x3 = 30.00, Beer 6.00 x3 = 18.00, Burger 14.00 = 14.00
    assert summary["total_sales_cents"] == 6200
    assert summary["ticket_count"] == 2
    assert summary["average_ticket_cents"] == 3100


def test_item_sales_most_popular_first_with_food_and_drink_split(db, busy_day):
    items = item_sales(db, busy_day)
    assert [row["name"] for row in items["drinks"]] == ["Beer"]
    assert items["drinks"][0]["qty"] == 3
    assert [row["name"] for row in items["food"]] == ["Caesar Salad", "Burger"]
    assert items["food"][0]["qty"] == 3 and items["food"][1]["qty"] == 1


def test_end_of_day_writes_csv_files(db, busy_day, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EXPORT_DIR", str(tmp_path))
    result = end_of_day(db, busy_day)

    summary_rows = list(csv.reader(open(result["files"]["summary"])))
    assert summary_rows[1] == [busy_day.isoformat(), "62.00", "2", "31.00"]
    item_rows = list(csv.reader(open(result["files"]["item_sales"])))
    assert item_rows[0] == ["type", "item", "qty", "sales"]
    assert ["drink", "Beer", "3", "18.00"] in item_rows
    assert ["food", "Caesar Salad", "3", "30.00"] in item_rows
    assert result["folder"].endswith(busy_day.isoformat())


def test_weekly_report_after_seven_saved_days(db, busy_day, tmp_path, monkeypatch):
    from datetime import timedelta
    from app.services.daily_reports import weekly_report
    monkeypatch.setattr(settings, "EXPORT_DIR", str(tmp_path))

    # Six earlier business days already saved
    for offset in range(6, 0, -1):
        (tmp_path / (busy_day - timedelta(days=offset)).isoformat()).mkdir()

    result = end_of_day(db, busy_day)  # the seventh saved day triggers the weekly report

    assert result["weekly"] is not None
    expected = tmp_path / "weekly" / f"{(busy_day - timedelta(days=6)).isoformat()}_to_{busy_day.isoformat()}"
    assert expected.is_dir()
    assert (expected / "summary.csv").exists() and (expected / "item_sales.csv").exists() and (expected / "hourly.csv").exists()

    weekly_rows = list(csv.reader(open(expected / "summary.csv")))
    assert weekly_rows[-1][0] == "TOTAL" and weekly_rows[-1][1] == "62.00" and weekly_rows[-1][2] == "2"
    assert end_of_day(db, busy_day)["weekly"] is None  # no second report the same day
