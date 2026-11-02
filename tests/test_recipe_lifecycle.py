import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.admin import router as admin_router
from app.api.routes.menu import router as menu_router


@pytest.fixture
def api(db):
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(menu_router, prefix="/api/v1")
    return TestClient(app)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_recipe_lifecycle(api, login):
    # First, get the admin token
    headers = login("ADM1")
    
    # Get a recipe id from the existing recipes
    recipe_list = api.get("/api/v1/admin/recipes", headers=headers).json()
    assert len(recipe_list) > 0
    
    # Get an existing recipe ID
    existing_recipe_id = recipe_list[0]["id"]
    existing_recipe_name = recipe_list[0]["name"]

    # Add a new recipe to test with (201)
    new_recipe_data = {
        "name": "New Test Recipe", 
        "category": "hot", 
        "price_cents": 750,
        "ingredients": [
            {"ingredient": "Flour", "qty": 2, "unit": "cup"},
            {"ingredient": "Egg", "qty": 1, "unit": "piece"}
        ]
    }
    
    response = api.post("/api/v1/admin/recipes", json=new_recipe_data, headers=headers)
    assert response.status_code == 201
    new_recipe_id = response.json()["id"]

    # PUT changes price and ingredients; GET shows new price 
    updated_recipe = {
        "name": "Updated Test Recipe",
        "category": "hot",
        "price_cents": 850,
        "ingredients": [
            {"ingredient": "Sugar", "qty": 1, "unit": "oz"},
            {"ingredient": "Flour", "qty": 1, "unit": "cup"}
        ]
    }
    
    response = api.put(f"/api/v1/admin/recipes/{new_recipe_id}", json=updated_recipe, headers=headers)
    assert response.status_code == 200
    
    # Verify updated price appears in menu 
    menu_response = api.get("/api/v1/menu?category=hot", headers=headers)
    assert menu_response.status_code == 200
    
    menu_items = menu_response.json()
    updated_item = None
    for item in menu_items:
        if item["name"] == "Updated Test Recipe":
            updated_item = item
            break
    
    assert updated_item is not None
    assert updated_item["price_cents"] == 850

    # PUT renaming to another existing recipe's name → 409
    response = api.put(f"/api/v1/admin/recipes/{new_recipe_id}", json={
        "name": "Caesar Salad",  # This exists already
        "category": "cold",
        "price_cents": 900,
        "ingredients": [
            {"ingredient": "Lettuce", "qty": 2, "unit": "cup"}
        ]
    }, headers=headers)
    assert response.status_code == 409
    
    # Deactivate: gone from GET /api/v1/menu; status "inactive"; reactivate brings it back
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/deactivate", headers=headers)
    assert response.status_code == 200
    deactivate_result = response.json()
    assert deactivate_result["status"] == "inactive"

    # Check that deactivated recipe is no longer in menu
    menu_response = api.get("/api/v1/menu?category=hot", headers=headers)
    assert menu_response.status_code == 200
    menu_items = menu_response.json()
    
    # Should not find the deactivated recipe
    found = any(item["name"] == "Updated Test Recipe" for item in menu_items)
    assert not found

    # Reactivate 
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/reactivate", headers=headers)
    assert response.status_code == 200
    reactivate_result = response.json()
    assert reactivate_result["status"] == "active"
    
    # Check that reactivated recipe is back in menu
    menu_response = api.get("/api/v1/menu?category=hot", headers=headers)
    assert menu_response.status_code == 200
    menu_items = menu_response.json()
    
    found = any(item["name"] == "Updated Test Recipe" for item in menu_items)
    assert found
    
    # Archive: gone from /menu and from default GET /admin/recipes; 
    # present with ?include_archived=true, status "archived"; PUT → 409; 
    # reactivate → 409; deactivate → 409; archive again → 409
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/archive", headers=headers)
    assert response.status_code == 200
    archive_result = response.json()
    assert archive_result["status"] == "archived"
    
    # Check that archived recipe is no longer in menu
    menu_response = api.get("/api/v1/menu?category=hot", headers=headers)
    assert menu_response.status_code == 200
    menu_items = menu_response.json()
    
    found = any(item["name"] == "Updated Test Recipe" for item in menu_items)
    assert not found
    
    # Check that it's still in admin recipes when including archived
    recipe_list_with_archived = api.get("/api/v1/admin/recipes?include_archived=true", headers=headers).json()
    found = any(item["id"] == new_recipe_id and item["status"] == "archived" for item in recipe_list_with_archived)
    assert found
    
    # PUT on archived recipe should fail
    response = api.put(f"/api/v1/admin/recipes/{new_recipe_id}", json=updated_recipe, headers=headers)
    assert response.status_code == 409
    
    # Reactivate on archived recipe should fail
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/reactivate", headers=headers)
    assert response.status_code == 409
    
    # Deactivate on archived recipe should fail
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/deactivate", headers=headers)
    assert response.status_code == 409
    
    # Archive again should fail 
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/archive", headers=headers)
    assert response.status_code == 409
    
    # Adding a new recipe with an archived item's name → 409
    response = api.post("/api/v1/admin/recipes", json={
        "name": "Updated Test Recipe",  # This name is taken by the archived recipe
        "category": "hot",
        "price_cents": 750,
        "ingredients": [
            {"ingredient": "Flour", "qty": 2, "unit": "cup"}
        ]
    }, headers=headers)
    assert response.status_code == 409
    
    # Non-admin (login("SRV1")) gets 403 on PUT, deactivate, reactivate, archive
    srv_headers = login("SRV1") 
    response = api.put(f"/api/v1/admin/recipes/{new_recipe_id}", json=updated_recipe, headers=srv_headers)
    assert response.status_code == 403
    
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/deactivate", headers=srv_headers)
    assert response.status_code == 403
    
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/reactivate", headers=srv_headers)
    assert response.status_code == 403
    
    response = api.post(f"/api/v1/admin/recipes/{new_recipe_id}/archive", headers=srv_headers)
    assert response.status_code == 403

    # PUT on unknown id → 404
    response = api.put("/api/v1/admin/recipes/999999", json=updated_recipe, headers=headers)
    assert response.status_code == 404
    