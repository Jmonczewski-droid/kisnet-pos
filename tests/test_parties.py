import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db.base import Base, SessionLocal, engine
from app.services.seed import seed_all
from app.api.routes.seats import router as seats_router
from app.api.routes.parties import router as parties_router
from app.api.routes.orders import router as orders_router
from app.core.time import utcnow


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(seats_router, prefix="/api/v1")
    app.include_router(parties_router, prefix="/api/v1") 
    app.include_router(orders_router, prefix="/api/v1")
    return TestClient(app)


def test_create_table_party_with_server(client, db, login):
    # HOST1 creates a party at B2 with server SRV1
    headers = login("HOST1")
    
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "B2",
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": 2  # SRV1's seed id
        },
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["seat"] == "B2"
    assert data["party_name"] == "Test Party"
    assert data["party_size"] == 4
    assert data["server_id"] == 2


def test_host_creating_at_bar_seat_fails(client, db, login):
    # HOST1 trying to create a party at Z3 (bar seat) should fail
    headers = login("HOST1")
    
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "Z3",
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": 2
        },
        headers=headers
    )
    
    assert response.status_code == 403


def test_bartender_creating_at_bar_seat(client, db, login):
    # BAR1 (bartender) creates a party at Z3 with server null
    headers = login("BAR1")
    
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "Z3",
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": None
        },
        headers=headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["seat"] == "Z3"
    assert data["server_id"] is None


def test_duplicate_seat_fails(client, db, login):
    # HOST1 creates a party at B2
    headers = login("HOST1")
    
    client.post(
        "/api/v1/parties",
        json={
            "seat": "B2",
            "party_name": "Test Party 1",
            "party_size": 4,
            "server_id": 2
        },
        headers=headers
    )
    
    # Try to create another party at same seat - should fail with 409
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "B2",
            "party_name": "Test Party 2",
            "party_size": 3,
            "server_id": 2
        },
        headers=headers
    )
    
    assert response.status_code == 409


def test_bad_seat_fails(client, db, login):
    # HOST1 tries to create party at invalid seat Q9 - should fail with 422
    headers = login("HOST1")
    
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "Q9",
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": 2
        },
        headers=headers
    )
    
    assert response.status_code == 422


def test_get_seats(client, db, login):
    # ADM1 (admin) gets seats list
    headers = login("ADM1")
    
    response = client.get("/api/v1/seats", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 26  # 16 table seats + 10 bar seats
    
    # Check that Z3 (bar seat) is in the list
    z3_seat = next((s for s in data if s["seat"] == "Z3"), None)
    assert z3_seat is not None
    assert z3_seat["party"] is None  # No party at Z3 yet


def test_server_sees_own_parties(client, db, login):
    # HOST1 creates a party at B2 with server SRV1
    headers = login("HOST1")
    
    client.post(
        "/api/v1/parties",
        json={
            "seat": "B2", 
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": 2  # SRV1's id
        },
        headers=headers
    )
    
    # SRV1 (server) should see this party in the list
    headers = login("SRV1")
    
    response = client.get("/api/v1/parties?open=true", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["seat"] == "B2"


def _open_party_with_caesar(client, db, login):
    from app.models import MenuItem

    response = client.post(
        "/api/v1/parties",
        json={"seat": "B2", "party_name": "Test Party", "party_size": 4, "server_id": 2},
        headers=login("HOST1"),
    )
    assert response.status_code == 201, response.text
    party_id = response.json()["id"]
    menu_item = db.query(MenuItem).filter_by(name="Caesar Salad").one()
    response = client.post(
        f"/api/v1/parties/{party_id}/items",
        json={"items": [{"menu_item_id": menu_item.id, "qty": 2}]},
        headers=login("ADM1"),
    )
    assert response.status_code == 201, response.text
    return party_id


def test_close_party_with_open_order_fails(client, db, login):
    party_id = _open_party_with_caesar(client, db, login)

    response = client.post(f"/api/v1/parties/{party_id}/close", headers=login("HOST1"))

    assert response.status_code == 409


def test_close_party_after_completing_order(client, db, login):
    party_id = _open_party_with_caesar(client, db, login)

    response = client.post(f"/api/v1/parties/{party_id}/complete", headers=login("ADM1"))
    assert response.status_code == 200, response.text

    response = client.post(f"/api/v1/parties/{party_id}/close", headers=login("HOST1"))
    assert response.status_code == 200, response.text
    seats = client.get("/api/v1/seats", headers=login("ADM1")).json()
    b2 = next(seat for seat in seats if seat["seat"] == "B2")
    assert b2["party"] is None


def test_server_cannot_close_party(client, db, login):
    # HOST1 creates a party at B2 with server SRV1  
    headers = login("HOST1")
    
    response = client.post(
        "/api/v1/parties",
        json={
            "seat": "B2",
            "party_name": "Test Party",
            "party_size": 4,
            "server_id": 2
        },
        headers=headers
    )
    
    party_data = response.json()
    party_id = party_data["id"]
    
    # SRV1 (server) tries to close the party - should fail with 403
    headers = login("SRV1")
    response = client.post(f"/api/v1/parties/{party_id}/close", headers=headers)
    
    assert response.status_code == 403