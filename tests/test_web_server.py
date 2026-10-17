from fastapi.testclient import TestClient
from adapters.web_server import app


client = TestClient(app)


def test_dashboard_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "OSINT-D2" in response.text
    assert "vis-network" in response.text


def test_dashboard_i18n_en():
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert "Intelligence Dashboard" in response.text
    assert "Start Investigation" in response.text


def test_dashboard_i18n_es():
    response = client.get("/?lang=es")
    assert response.status_code == 200
    assert "Panel de Inteligencia" in response.text
    assert "Iniciar investigación" in response.text


def test_dashboard_i18n_fallback():
    response = client.get("/?lang=xx")
    assert response.status_code == 200
    assert "Intelligence Dashboard" in response.text


def test_investigate_api_endpoint():
    payload = {
        "target": "test-subject",
        "mode": "agent",
        "language": "es",
    }
    response = client.post("/api/investigate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "investigation_id" in data
    assert data["status"] == "started"
    assert data["target"] == "test-subject"
