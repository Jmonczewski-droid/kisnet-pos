from datetime import date

from app.core.time import utcnow
from app.models import Employee, MenuItem, Order, Party, TimeEntry
from app.schemas.order import OrderItemIn
from app.services.daily_reports import day_summary, end_of_day
from app.services.orders import send_ticket
from app.core.config import settings


def test_end_of_day_clocks_out_closes_and_keeps_history(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EXPORT_DIR", str(tmp_path))
    server = db.query(Employee).filter_by(code="SRV1").one()
    db.add(TimeEntry(employee_id=server.id, clocked_in_at=utcnow(), token_hash="x"))
    party = Party(seat="A1", party_name="Open Table", party_size=2, server_id=server.id,
                  created_by_id=server.id, opened_at=utcnow())
    db.add(party)
    db.commit()
    beer = db.query(MenuItem).filter_by(name="Beer").one()
    send_ticket(db, server, party, [OrderItemIn(menu_item_id=beer.id, qty=2)], [], [])
    today = date.today()
    before = day_summary(db, today)
    employees, menu_items = db.query(Employee).count(), db.query(MenuItem).count()

    result = end_of_day(db, today)

    assert result["reset"]["clocked_out"] == 1
    assert result["reset"]["tables_closed"] == 1
    assert result["reset"]["orders_completed"] == 1
    db.expire_all()
    assert db.query(TimeEntry).filter(TimeEntry.clocked_out_at.is_(None)).count() == 0
    assert db.query(TimeEntry).filter(TimeEntry.token_hash.isnot(None)).count() == 0
    assert db.query(Party).filter(Party.closed_at.is_(None)).count() == 0
    assert db.query(Order).filter(Order.status == "open").count() == 0
    assert db.query(Employee).count() == employees
    assert db.query(MenuItem).count() == menu_items
    after = day_summary(db, today)
    assert after["total_sales_cents"] == before["total_sales_cents"]
    assert after["ticket_count"] == before["ticket_count"]
