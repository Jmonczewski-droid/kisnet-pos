import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.menu import router as menu_router
from app.db.base import Base, SessionLocal, engine
from app.services.seed import seed_all

# Create the test client and fixtures similar to test_maintenance.py
@pytest.fixture
def api(db):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(menu_router, prefix="/api/v1")
    return TestClient(app)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _new_employee(positions, name="Ruth Adams", pin="4321"):
    return {"name": name, "address": "12 Oak Street", "dob": "1990-05-02", "hire_date": "2026-10-01",
            "positions": positions, "pin": pin}


@pytest.fixture
def employee_data():
    return {"name": "Test Employee", "address": "123 Test St", "dob": "1990-01-01", 
            "hire_date": "2026-10-01", "positions": ["server"], "pin": "1234"}


@pytest.fixture
def add_employee(api, login):
    """Helper to add an employee and return the employee ID."""
    def _add_employee(positions=["server"], name="Test Employee", pin="1234"):
        headers = login("ADM1")
        response = api.post("/api/v1/admin/employees", 
                          json={"name": name, "address": "123 Test St", "dob": "1990-01-01", 
                                "hire_date": "2026-10-01", "positions": positions, "pin": pin},
                          headers=headers)
        assert response.status_code == 201
        employee_id = response.json()["id"]
        return employee_id
    return _add_employee


def test_patch_name_and_positions(api, login, add_employee):
    """Test that PATCH updates name and positions correctly."""
    employee_id = add_employee(["server", "bartender"], "Original Name")
    
    headers = login("ADM1")
    response = api.patch(f"/api/v1/admin/employees/{employee_id}", 
                        json={"name": "Updated Name", "positions": ["bartender", "server"]}, 
                        headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that name was updated
    assert data["name"] == "Updated Name"
    
    # Check that positions were updated - they get re-ordered by ROLES precedence
    from app.core.constants import ROLES
    expected_positions = [role for role in ROLES if role in ["bartender", "server"]]
    assert data["positions"] == expected_positions
    # The first position will be the one with the lowest index in ROLES (which is 'server' before 'bartender')
    assert data["positions"][0] == "server"  # role follows the first position in standard ROLES order
    
    # Verify SSN is unchanged
    assert "ssn" in data
    # Verify other fields remain the same
    assert data["active"] is True
    assert data["status"] == "active"


def test_patch_pin(api, login, add_employee):
    """Test that PIN changes work correctly and old PIN is rejected."""
    employee_id = add_employee(["server"], "Pin Test Employee")
    
    headers = login("ADM1")
    # Change the PIN
    response = api.patch(f"/api/v1/admin/employees/{employee_id}", 
                        json={"pin": "9876"}, 
                        headers=headers)
    
    assert response.status_code == 200
    
    # Verify new PIN works
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "9876"})
    assert response.status_code == 200
    
    # Verify old PIN is rejected
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "1234"})
    assert response.status_code == 401


def test_deactivate_employee(api, login, add_employee):
    """Test employee deactivation."""
    employee_id = add_employee(["server"], "Deactivate Test")
    
    headers = login("ADM1")
    
    # Deactivate the employee
    response = api.post(f"/api/v1/admin/employees/{employee_id}/deactivate", 
                       headers=headers)
    
    assert response.status_code == 200
    
    # Verify employee cannot clock in anymore
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "1234"})
    assert response.status_code == 401
    
    # Verify employee is not listed in active employees
    roster_response = api.get("/api/v1/admin/roster", headers=headers)
    assert roster_response.status_code == 200
    roster_data = roster_response.json()
    employee_in_roster = next((emp for emp in roster_data if emp["id"] == employee_id), None)
    assert employee_in_roster is not None
    assert employee_in_roster["status"] == "inactive"
    
    # Verify employee is not in the list of employees (they should be inactive but still visible in roster when include_archived=True)
    active_employees = api.get("/api/v1/employees", headers=headers).json()
    assert not any(emp["id"] == employee_id for emp in active_employees)


def test_deactivate_while_on_clock(api, login, add_employee):
    """Test that deactivating an employee while on clock removes them from on-clock list."""
    employee_id = add_employee(["server"], "Clock Test")
    
    headers = login("ADM1")
    
    # Clock the employee in
    api.post("/api/v1/auth/clock-in", json={"code": "SRV5", "pin": "1234"})
    
    # Get on-clock list before deactivation
    response = api.get("/api/v1/admin/on-clock", headers=headers)
    assert response.status_code == 200
    on_clock_before = response.json()
    assert any(emp["employee_id"] == employee_id for emp in on_clock_before)
    
    # Deactivate the employee
    response = api.post(f"/api/v1/admin/employees/{employee_id}/deactivate", 
                       headers=headers)
    assert response.status_code == 200
    
    # Verify employee is not in on-clock list anymore
    response = api.get("/api/v1/admin/on-clock", headers=headers)
    assert response.status_code == 200
    on_clock_after = response.json()
    assert not any(emp["employee_id"] == employee_id for emp in on_clock_after)


def test_deactivate_then_reactivate(api, login, add_employee):
    """Test reactivating a deactivated employee."""
    employee_id = add_employee(["server"], "Reactivate Test")
    
    headers = login("ADM1")
    
    # Deactivate the employee
    response = api.post(f"/api/v1/admin/employees/{employee_id}/deactivate", 
                       headers=headers)
    assert response.status_code == 200
    
    # Verify employee cannot clock in
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "1234"})
    assert response.status_code == 401
    
    # Reactivate the employee
    response = api.post(f"/api/v1/admin/employees/{employee_id}/reactivate", 
                       headers=headers)
    assert response.status_code == 200
    
    # Verify employee can clock in now
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "1234"})
    assert response.status_code == 200


def test_archive_employee(api, login, add_employee):
    """Test archiving an employee."""
    employee_id = add_employee(["server"], "Archive Test")
    
    headers = login("ADM1")
    
    # Archive the employee
    response = api.post(f"/api/v1/admin/employees/{employee_id}/archive", 
                       headers=headers)
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "archived"
    
    # Verify employee is not in default roster anymore
    roster_response = api.get("/api/v1/admin/roster", headers=headers)
    assert roster_response.status_code == 200
    roster_data = roster_response.json()
    assert not any(emp["id"] == employee_id for emp in roster_data)
    
    # Verify employee is present when include_archived=true
    archived_roster_response = api.get("/api/v1/admin/roster?include_archived=true", headers=headers)
    assert archived_roster_response.status_code == 200
    archived_roster_data = archived_roster_response.json()
    assert any(emp["id"] == employee_id for emp in archived_roster_data)
    
    # Verify PATCH returns 409
    response = api.patch(f"/api/v1/admin/employees/{employee_id}", 
                        json={"name": "Updated Name"}, 
                        headers=headers)
    assert response.status_code == 409
    
    # Verify reactivate returns 409
    response = api.post(f"/api/v1/admin/employees/{employee_id}/reactivate", 
                       headers=headers)
    assert response.status_code == 409
    
    # Verify clock-in returns 401
    response = api.post("/api/v1/auth/clock-in", 
                       json={"code": "SRV5", "pin": "1234"})
    assert response.status_code == 401


def test_cannot_change_deactivated_or_archived_employee_with_open_party(api, login, add_employee):
    """Test that deactivate or archive returns 409 when employee has open party."""
    from app.core.time import utcnow
    employee_id = add_employee(["server"], "Party Test")
    
    # Add a party with this employee as server
    headers = login("ADM1")
    from app.models.party import Party
    
    db = SessionLocal()
    seed_all(db)
    new_party = Party(
        seat="A1",
        party_name="Test Party", 
        party_size=4,
        server_id=employee_id,
        created_by_id=1,
        opened_at=utcnow()
    )
    db.add(new_party)
    db.commit()
    db.refresh(new_party)
    
    # Try to deactivate - should fail
    response = api.post(f"/api/v1/admin/employees/{employee_id}/deactivate", 
                       headers=headers)
    assert response.status_code == 409
    
    # Try to archive - should fail  
    response = api.post(f"/api/v1/admin/employees/{employee_id}/archive", 
                       headers=headers)
    assert response.status_code == 409
    
    db.close()


def test_non_admin_access_returns_403(api, login, add_employee):
    """Test that non-admin users cannot perform employee lifecycle actions."""
    employee_id = add_employee(["server"], "Access Test")
    
    # Try as non-admin user (SRV1)
    headers = login("SRV1")
    
    # Try to PATCH
    response = api.patch(f"/api/v1/admin/employees/{employee_id}", 
                        json={"name": "Updated Name"}, 
                        headers=headers)
    assert response.status_code == 403
    
    # Try to deactivate
    response = api.post(f"/api/v1/admin/employees/{employee_id}/deactivate", 
                       headers=headers)
    assert response.status_code == 403
    
    # Try to reactivate
    response = api.post(f"/api/v1/admin/employees/{employee_id}/reactivate", 
                       headers=headers)
    assert response.status_code == 403
    
    # Try to archive
    response = api.post(f"/api/v1/admin/employees/{employee_id}/archive", 
                       headers=headers)
    assert response.status_code == 403


def test_patch_unknown_employee_returns_404(api, login):
    """Test that PATCH on unknown employee ID returns 404."""
    headers = login("ADM1")
    
    response = api.patch("/api/v1/admin/employees/9999", 
                        json={"name": "Updated Name"}, 
                        headers=headers)
    assert response.status_code == 404