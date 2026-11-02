import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.menu import router as menu_router


@pytest.fixture
def api(db):
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


def test_add_employee_gets_code_and_masked_ssn(api, login):
    headers = login("ADM1")
    response = api.post("/api/v1/admin/employees", json=_new_employee(["server", "bartender"]), headers=headers)

    assert response.status_code == 201, response.text
    assert response.json()["code"] == "SRV5"  # SRV1-SRV4 are seeded
    rows = api.get("/api/v1/admin/roster", headers=headers).json()
    ruth = next(row for row in rows if row["code"] == "SRV5")
    assert ruth["positions"] == ["server", "bartender"]
    assert ruth["ssn"] == "XXX-XX-XXX5"
    assert ruth["address"] == "12 Oak Street"
    # the System screen shows these; a missing key breaks the whole roster
    assert ruth["week_hours"] == 0
    assert ruth["on_clock"] is False and ruth["clocked_in_at"] is None


def test_multi_position_employee_must_choose_position_at_clock_in(api, login, db):
    admin = login("ADM1")
    api.post("/api/v1/admin/employees", json=_new_employee(["server", "bartender"], name="Multi Job", pin="5555"), headers=admin)

    assert api.post("/api/v1/auth/clock-in", json={"code": "SRV5", "pin": "5555"}).status_code == 422
    response = api.post("/api/v1/auth/clock-in", json={"code": "SRV5", "pin": "5555", "position": "bartender"})
    assert response.status_code == 200
    assert response.json()["position"] == "bartender"

    token = api.post("/api/v1/auth/login", json={"code": "SRV5", "pin": "5555"}).json()["token"]
    me = api.get("/api/v1/auth/me", headers=_bearer(token)).json()
    assert me["role"] == "bartender"  # the session works in the position of the shift


def test_position_must_be_on_the_employees_list(api, login):
    admin = login("ADM1")
    api.post("/api/v1/admin/employees", json=_new_employee(["server"], name="One Job", pin="6666"), headers=admin)
    response = api.post("/api/v1/auth/clock-in", json={"code": "SRV5", "pin": "6666", "position": "kitchen"})
    assert response.status_code == 422


def test_unknown_position_is_rejected(api, login):
    response = api.post("/api/v1/admin/employees", json=_new_employee(["janitor"]), headers=login("ADM1"))
    assert response.status_code == 422


def test_add_recipe_with_price_appears_on_the_menu(api, login):
    headers = login("ADM1")
    recipe = {"name": "Test Chowder", "category": "hot", "price_cents": 850,
              "ingredients": [{"ingredient": "Clam", "qty": 4, "unit": "oz"}]}
    assert api.post("/api/v1/admin/recipes", json=recipe, headers=headers).status_code == 201

    menu = api.get("/api/v1/menu?category=hot", headers=headers).json()
    assert any(item["name"] == "Test Chowder" and item["price_cents"] == 850 for item in menu)
    assert api.post("/api/v1/admin/recipes", json=recipe, headers=headers).status_code == 409


def test_recipe_needs_a_known_category(api, login):
    recipe = {"name": "Odd", "category": "dessert", "price_cents": 500,
              "ingredients": [{"ingredient": "Sugar", "qty": 1, "unit": "oz"}]}
    assert api.post("/api/v1/admin/recipes", json=recipe, headers=login("ADM1")).status_code == 422


def test_maintenance_is_admin_only(api, login):
    srv = login("SRV1")
    assert api.get("/api/v1/admin/roster", headers=srv).status_code == 403
    assert api.post("/api/v1/admin/employees", json=_new_employee(["server"]), headers=srv).status_code == 403
    assert api.post("/api/v1/admin/recipes", json={"name": "X", "category": "hot", "price_cents": 1,
                                                    "ingredients": [{"ingredient": "a", "qty": 1, "unit": "oz"}]},
                    headers=srv).status_code == 403
