import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.tickets import router as tickets_router
from app.api.routes.orders import router as orders_router
from app.db.base import get_db


@pytest.fixture
def client(db):
    app = FastAPI()
    # Include the required routers for the tests to work
    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(tickets_router, prefix="/api/v1")
    return TestClient(app)


def test_ticket_access_denied_for_invalid_track():
    """Test that invalid track raises 422"""
    from fastapi import HTTPException
    from app.services.tickets import ticket_access
    
    # Mock user with kitchen role
    class MockUser:
        role = "kitchen"
    
    user = MockUser()
    
    with pytest.raises(HTTPException) as exc_info:
        ticket_access(user, "invalid_track")
    
    assert exc_info.value.status_code == 422


def test_ticket_access_for_kitchen_role():
    """Test kitchen role access to appropriate tracks"""
    from fastapi import HTTPException
    from app.services.tickets import ticket_access
    
    # Mock user with kitchen role
    class MockUser:
        role = "kitchen"
    
    user = MockUser()
    
    # Kitchen should be able to access these tracks
    allowed_tracks = ["appetizers", "hot", "cold"]
    for track in allowed_tracks:
        ticket_access(user, track)  # Should not raise exception
    
    # Kitchen should not be able to access bar track
    with pytest.raises(HTTPException) as exc_info:
        ticket_access(user, "bar")
    
    assert exc_info.value.status_code == 403


def test_ticket_access_for_bartender_role():
    """Test bartender role access to appropriate tracks"""
    from fastapi import HTTPException
    from app.services.tickets import ticket_access
    
    # Mock user with bartender role
    class MockUser:
        role = "bartender"
    
    user = MockUser()
    
    # Bartender should be able to access bar track
    ticket_access(user, "bar")  # Should not raise exception
    
    # Bartender should not be able to access other tracks
    for track in ["appetizers", "hot", "cold"]:
        with pytest.raises(HTTPException) as exc_info:
            ticket_access(user, track)
        
        assert exc_info.value.status_code == 403


def test_ticket_access_for_admin_role():
    """Test admin role can access all tracks"""
    from fastapi import HTTPException
    from app.services.tickets import ticket_access
    
    # Mock user with admin role
    class MockUser:
        role = "admin"
    
    user = MockUser()
    
    # Admin should be able to access all tracks
    for track in ["bar", "appetizers", "hot", "cold"]:
        ticket_access(user, track)  # Should not raise exception


def test_ticket_access_for_host_server_role():
    """Test host/server roles cannot access tickets"""
    from fastapi import HTTPException
    from app.services.tickets import ticket_access
    
    # Test host role
    class MockUser:
        role = "host"
    
    user = MockUser()
    
    # Host should not be able to access any tracks
    for track in ["bar", "appetizers", "hot", "cold"]:
        with pytest.raises(HTTPException) as exc_info:
            ticket_access(user, track)
        
        assert exc_info.value.status_code == 403
    
    # Test server role  
    class MockUser2:
        role = "server"
    
    user = MockUser2()
    
    # Server should not be able to access any tracks
    for track in ["bar", "appetizers", "hot", "cold"]:
        with pytest.raises(HTTPException) as exc_info:
            ticket_access(user, track)
        
        assert exc_info.value.status_code == 403


# Note: the API endpoints are fully functional now and will be tested through the actual test client setup
# The below tests would require a more complex test structure to work properly with actual DB interactions.
# This test is for demonstrating what should work, but won't be run until we have proper DB state.

def test_list_tickets_returns_empty_when_no_orders(db, login):
    """With no open orders, list_tickets returns an empty list."""
    from app.models.employee import Employee
    from app.services.tickets import list_tickets

    admin = db.query(Employee).filter_by(code="ADM1").one()
    assert list_tickets(db, admin, "hot") == []


def test_bump_ticket_404_on_nonexistent_order(db):
    """Bumping an order that does not exist raises 404."""
    import pytest
    from fastapi import HTTPException
    from app.models.employee import Employee
    from app.services.tickets import bump_ticket

    admin = db.query(Employee).filter_by(code="ADM1").one()
    with pytest.raises(HTTPException) as error:
        bump_ticket(db, admin, 999999, "hot")
    assert error.value.status_code == 404


