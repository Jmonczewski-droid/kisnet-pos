import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client):
    """Test that /health returns status OK"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_api_v1_health_endpoint(client):
    """Test that /api/v1/health returns status OK"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}


def test_menu_requires_auth(client, db):
    """Test that /api/v1/menu requires authentication (401 without header)"""
    response = client.get("/api/v1/menu")
    assert response.status_code == 401


def test_openapi_json_endpoint(client):
    """Test that openapi JSON is served at /api/v1/openapi.json"""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert data["info"]["title"] == "KISnet-POS"
    

def test_openapi_paths(client):
    """Test that openapi paths include the expected endpoints"""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    data = response.json()
    
    paths = data.get("paths", {})
    
    # Check that required paths are present
    assert "/api/v1/auth/clock-in" in paths
    assert "/api/v1/parties" in paths  
    assert "/api/v1/tickets" in paths
    assert "/api/v1/reports/daily-sales" in paths