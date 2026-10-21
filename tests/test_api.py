"""Tests for the FastAPI endpoints, on the sample data and without any API key."""

import json

import pytest
from fastapi.testclient import TestClient
from sample_data import RAW

from o2c import api
from o2c.assistant import AssistantReply, ToolCall


@pytest.fixture
def client(tmp_path, monkeypatch):
    folder = tmp_path / "fixtures"
    folder.mkdir()
    for name, rows in RAW.items():
        (folder / f"{name}.json").write_text(json.dumps(rows))
    # Point the app to a temp DB and the sample fixtures, and remove all keys
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setattr("o2c.sync.FIXTURE_DIR", folder)
    monkeypatch.setattr("o2c.api.run_sync", _sync_from(folder))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")  # closed port: no Ollama
    api.app.state.assistant = None
    monkeypatch.delenv("SAP_API_KEY", raising=False)
    with TestClient(api.app) as c:
        yield c


def _sync_from(folder):
    from o2c.sync import run_sync

    return lambda key, engine, **kw: run_sync(key, engine, fixture_dir=folder)


def test_health_shows_chat_disabled(client):
    assert client.get("/health").json() == {
        "status": "ok",
        "chat_provider": "ollama",
        "chat_enabled": False,
    }


def test_kpis_on_first_start_without_keys(client):
    data = client.get("/kpis").json()
    assert data["open_orders"] == {"count": 1, "value": "353.50"}
    assert data["delivered_not_billed"]["count"] == 1
    assert data["funnel"] == {"ordered": 3, "delivered": 2, "billed": 1}
    assert data["last_sync"]["source"] == "fixtures"


def test_chat_without_ollama_explains_in_german_and_english(client):
    res = client.post("/chat", json={"question": "Hallo"})
    assert res.status_code == 503
    assert "Starte die Ollama-App" in res.json()["detail"]
    assert "Start the Ollama app" in res.json()["detail"]


def test_chat_with_anthropic_but_no_key(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    res = client.post("/chat", json={"question": "Hallo"})
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_chat_returns_answer_and_tool_calls(client):
    class StubAssistant:
        def chat(self, question, history):
            return AssistantReply("Antwort", [ToolCall("top_customers", {"n": 1}, [])])

    api.app.state.assistant = StubAssistant()
    res = client.post("/chat", json={"question": "Top Kunde?"})
    assert res.json() == {
        "answer": "Antwort",
        "tool_calls": [
            {"name": "top_customers", "input": {"n": 1}, "output": [], "is_error": False}
        ],
    }


def test_chat_rejects_empty_question(client):
    assert client.post("/chat", json={"question": ""}).status_code == 422


def test_refresh_uses_fixtures_without_sap_key(client):
    res = client.post("/refresh").json()
    assert res["source"] == "fixtures"
    assert res["rows"]["sales_order"] == 3
