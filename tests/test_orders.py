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