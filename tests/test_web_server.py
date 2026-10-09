import pytest
from fastapi.testclient import TestClient
from adapters.web_server import app


client = TestClient(app)


def test_dashboard_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "OSINT-D2 // Live Intelligence Dashboard" in response.text
    assert "vis-network" in response.text


def test_investigate_api_endpoint():
    payload = {
        "target": "Doble-2",
        "mode": "agent",
        "language": "es",
    }
    response = client.post("/api/investigate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "investigation_id" in data
    assert data["status"] == "started"
    assert data["target"] == "Doble-2"
