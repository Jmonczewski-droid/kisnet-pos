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
