import pytest

# Test to confirm the services are importable and working
def test_services_importable():
    """Verify all components can be imported successfully."""
    from app.services.orders import (
        add_items,
        update_item,
        void_item,
        complete_order,
        order_out,
        OrderError,
        can_order,
        can_view_party
    )
    
    assert add_items is not None
    assert update_item is not None
    assert void_item is not None
    assert complete_order is not None 
    assert order_out is not None
    assert OrderError is not None
    assert can_order is not None
    assert can_view_party is not None


def test_schema_importable():
    """Verify schemas are importable."""
    from app.schemas.order import (
        OrderItemIn,
        OrderItemsIn,
        OrderItemPatch,
        OrderItemOut,
        OrderOut
    )
    
    assert OrderItemIn is not None
    assert OrderItemsIn is not None
    assert OrderItemPatch is not None 
    assert OrderItemOut is not None
    assert OrderOut is not None


def test_routes_importable():
    """Verify routes can be imported."""
    from app.api.routes.orders import router
    
    assert router is not None

def test_change_quantity_and_void_line_through_api(client, db, login):
    from app.core.time import utcnow
    from app.models import Party, MenuItem, Employee
    from app.services.orders import add_items, update_item, void_item
    from app.schemas.order import OrderItemIn, OrderItemsIn, OrderItemPatch

    server = db.query(Employee).filter_by(code="SRV1").one()
    party = Party(seat="B9", party_name="Edit Test", party_size=2, server_id=server.id, created_by_id=server.id, opened_at=utcnow())
    db.add(party)
    db.commit()
    menu_item = db.query(MenuItem).filter_by(name="Garden Salad").one()
    order = add_items(db, server, party, OrderItemsIn(items=[OrderItemIn(menu_item_id=menu_item.id, qty=1, notes=None)]))
    line = order.items[0]

    update_item(db, server, line, OrderItemPatch(qty=3, notes="no croutons"))
    db.refresh(line)
    assert line.qty == 3 and line.changed is True and line.notes == "no croutons"

    void_item(db, server, line)
    db.refresh(line)
    assert line.voided is True


def _send_setup(db):
    from app.core.time import utcnow
    from app.models import Party, Employee
    server = db.query(Employee).filter_by(code="SRV1").one()
    party = Party(seat="B8", party_name="Send Test", party_size=2, server_id=server.id,
                  created_by_id=server.id, opened_at=utcnow())
    db.add(party)
    db.commit()
    return server, party


def _menu_id(db, name):
    from app.models import MenuItem
    return db.query(MenuItem).filter_by(name=name).one().id


def test_send_ticket_saves_new_lines_changes_and_voids_together(db):
    from app.schemas.order import OrderItemIn, TicketUpdateIn
    from app.services.orders import send_ticket
    from app.models import OrderItem

    server, party = _send_setup(db)
    salad, beer = _menu_id(db, "Garden Salad"), _menu_id(db, "Beer")
    order = send_ticket(db, server, party, [OrderItemIn(menu_item_id=salad, qty=1), OrderItemIn(menu_item_id=beer, qty=2)], [], [])
    salad_line, beer_line = order.items

    order = send_ticket(db, server, party,
                        [OrderItemIn(menu_item_id=salad, qty=1)],
                        [TicketUpdateIn(item_id=salad_line.id, qty=3, notes="no onion")],
                        [beer_line.id])
    db.expire_all()
    lines = {item.id: item for item in db.query(OrderItem).filter_by(order_id=order.id).all()}
    assert lines[salad_line.id].qty == 3 and lines[salad_line.id].notes == "no onion" and lines[salad_line.id].changed
    assert lines[beer_line.id].voided is True
    new_line = max(lines.values(), key=lambda item: item.id)
    assert new_line.changed is True  # added after the first send


def test_send_ticket_refuses_changes_to_lines_already_at_kitchen(db):
    from app.core.time import utcnow
    from app.schemas.order import OrderItemIn, TicketUpdateIn
    from app.services.orders import OrderError, send_ticket

    server, party = _send_setup(db)
    order = send_ticket(db, server, party, [OrderItemIn(menu_item_id=_menu_id(db, "Burger"), qty=1)], [], [])
    line = order.items[0]
    line.bumped_at = utcnow()
    db.commit()

    try:
        send_ticket(db, server, party, [], [TicketUpdateIn(item_id=line.id, qty=2)], [])
        assert False, "expected a 409"
    except OrderError as error:
        assert error.status == 409


def test_send_with_nothing_to_send_is_422(db):
    from app.services.orders import OrderError, send_ticket

    server, party = _send_setup(db)
    try:
        send_ticket(db, server, party, [], [], [])
        assert False, "expected a 422"
    except OrderError as error:
        assert error.status == 422
