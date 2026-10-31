import json
import re
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from adapters.i18n import TEMPLATES_DIR
from adapters.web_server import active_sessions, app

I18N_DIR = TEMPLATES_DIR / "i18n"


client = TestClient(app, base_url="http://localhost")


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


def test_i18n_files_share_the_same_keys():
    files = list(I18N_DIR.glob("*.json"))
    assert {f.stem for f in files} == {"en", "es", "pt", "ar", "ru"}
    reference = set(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8")))
    for file in files:
        assert set(json.loads(file.read_text(encoding="utf-8"))) == reference, file.name


def test_graph_strings_share_keys_and_placeholders():
    def placeholders(text):
        return set(re.findall(r"{(\w+)}", text))

    reference = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))["graph"]
    for file in I18N_DIR.glob("*.json"):
        graph = json.loads(file.read_text(encoding="utf-8"))["graph"]
        assert set(graph) == set(reference), file.name
        for key, text in reference.items():
            assert placeholders(graph[key]) == placeholders(text), f"{file.name}:{key}"


def test_log_strings_keep_their_placeholders():
    reference = json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))
    for file in I18N_DIR.glob("*.json"):
        strings = json.loads(file.read_text(encoding="utf-8"))
        for key in (k for k in reference if k.startswith("log_")):
            assert set(re.findall(r"{(\w+)}", strings[key])) == set(re.findall(r"{(\w+)}", reference[key])), f"{file.name}:{key}"


def test_every_form_field_has_a_visible_label():
    html = client.get("/").text
    for field in ("target-input", "usernames-input", "emails-input", "phones-input", "anchors-input",
                  "mode-select", "ai-provider-select", "lang-select", "max-steps-input"):
        assert f'for="{field}"' in html, field


def test_dashboard_template_only_uses_defined_i18n_keys():
    template = (I18N_DIR.parent / "dashboard.html").read_text(encoding="utf-8")
    used = set(re.findall(r"\{\{ t\.([a-z0-9_]+)", template)) | set(re.findall(r"\bT\.([a-z0-9_]+)", template))
    assert used - set(json.loads((I18N_DIR / "en.json").read_text(encoding="utf-8"))) == set()


def test_dashboard_english_has_no_hardcoded_spanish():
    html = client.get("/?lang=en").text
    for text in ("Motor de búsqueda", "NODOS", "CONEXIONES", "CONFIANZA", "Sin pasos", "HALLAZGO", "seguidores"):
        assert text not in html


def test_dashboard_arabic_is_rtl():
    assert 'dir="rtl"' in client.get("/?lang=ar").text
    assert 'dir="ltr"' in client.get("/?lang=en").text


def test_dashboard_offers_every_report_language():
    html = client.get("/").text
    for value in ("en", "es", "pt", "ar", "ru"):
        assert f'<option value="{value}"' in html.split('id="lang-select"')[1]


def test_dashboard_reflects_ai_configuration(monkeypatch):
    monkeypatch.setenv("OSINT_D2_AI_PROVIDER", "openai")
    monkeypatch.setenv("OSINT_D2_AI_API_KEY", "not-a-real-key")
    html = client.get("/").text
    assert '<option value="openai" selected>' in html
    assert "const AI_KEY_CONFIGURED = true;" in html
    assert "not-a-real-key" not in html


def test_investigate_api_endpoint():
    payload = {
        "target": "test-subject",
        "mode": "agent",
        "language": "es",
    }
    # Stubbed: the real task would call the AI provider configured in .env.
    with patch("adapters.web_server._run_investigation", new=AsyncMock()):
        response = client.post("/api/investigate", json=payload)
    active_sessions.clear()
    assert response.status_code == 200
    data = response.json()
    assert "investigation_id" in data
    assert data["status"] == "started"
    assert data["target"] == "test-subject"
