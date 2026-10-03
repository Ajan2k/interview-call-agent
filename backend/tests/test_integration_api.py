"""Integration tests: spin up the real FastAPI app (main.app) via TestClient and
exercise the HTTP routes end-to-end. The database layer is mocked so these run with
no Postgres, and external HTTP (Sarvam translate) is faked so there's no network.

These verify request -> router -> (mocked) db wiring, status codes, and response
shapes — the seams a pure unit test can't cover.
"""
import pytest
from fastapi.testclient import TestClient

import main
from services import (
    db_manager,
    contact_repo,
    call_repo,
    meeting_repo,
    callback_repo,
    voice_config_repo,
    campaign_repo,
)
import services.translation_service

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """Make the DB layer behave as 'unavailable' by default so routes take their
    JSONL/in-memory fallback paths. Individual tests override specific functions."""
    monkeypatch.setattr(db_manager, "init_db", lambda: None)
    monkeypatch.setattr(db_manager, "get_connection", lambda: None)
    monkeypatch.setattr(call_repo, "get_all", lambda *a, **k: None)
    monkeypatch.setattr(meeting_repo, "get_all", lambda *a, **k: None)
    monkeypatch.setattr(callback_repo, "get_all", lambda *a, **k: None)
    monkeypatch.setattr(contact_repo, "get_all", lambda: [])
    monkeypatch.setattr(voice_config_repo, "get", lambda: None)
    monkeypatch.setattr(campaign_repo, "get_all", lambda: [])


class TestHealth:
    def test_health_ok_shape(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["databaseConnected"] is False  # get_connection mocked to None
        assert body["databaseType"] == "In-Memory (Fallback)"

    def test_health_reports_current_stack(self, client):
        # Guardrail: health should advertise the real providers we wired up.
        services = client.get("/api/health").json()["services"]
        assert "Cartesia" in services["tts"]
        assert "8B" in services["llm"] or "8b" in services["llm"]
        assert "Sarvam" in services["stt"]


class TestVoiceConfig:
    def test_get_returns_default_config(self, client):
        r = client.get("/api/voice-config")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_post_updates_config(self, client, monkeypatch):
        saved = {}
        monkeypatch.setattr(voice_config_repo, "save", lambda cfg: saved.update(cfg))
        r = client.post("/api/voice-config", json={"speed": 1.2})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["config"]["speed"] == 1.2


class TestContacts:
    def test_add_then_appears_in_list(self, client, monkeypatch):
        monkeypatch.setattr(contact_repo, "save", lambda c: None)
        # In-memory fallback list is used when contact_repo.get_all returns [].
        r = client.post("/api/contacts", json={"name": "Asha", "phone": "+9199"})
        assert r.status_code == 200
        created = r.json()
        assert created["name"] == "Asha"
        assert created["status"] == "Pending"       # default filled in
        assert created["lastCalled"] == "Never"
        assert "id" in created

    def test_update_missing_contact_404(self, client):
        r = client.put("/api/contacts/does-not-exist", json={"name": "x"})
        assert r.status_code == 404


class TestHistoryAndMeetings:
    def test_call_history_falls_back_to_jsonl(self, client, monkeypatch):
        # call_repo.get_all returns None -> route reads the JSONL file (may be empty).
        r = client.get("/api/call-history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_meetings_from_db(self, client, monkeypatch):
        monkeypatch.setattr(meeting_repo, "get_all", lambda *a, **k: [{"details": "Mon 3pm"}])
        r = client.get("/api/meetings")
        assert r.status_code == 200
        assert r.json() == [{"details": "Mon 3pm"}]

    def test_transcript_db_unavailable_503(self, client, monkeypatch):
        monkeypatch.setattr(call_repo, "get_transcript", lambda cid: None)
        r = client.get("/api/call-history/abc/transcript")
        assert r.status_code == 503


class TestTranslate:
    def test_empty_text_short_circuits(self, client):
        r = client.post("/api/translate", json={"text": "   "})
        assert r.status_code == 200
        assert r.json()["translated"] == ""

    def test_same_language_not_translated(self, client):
        r = client.post("/api/translate", json={
            "text": "hello", "source_language_code": "en-IN", "target_language_code": "en-IN",
        })
        assert r.json()["same_language"] is True
        assert r.json()["translated"] == "hello"

    def test_no_sarvam_key_returns_original(self, client, monkeypatch):
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        r = client.post("/api/translate", json={
            "text": "வணக்கம்", "source_language_code": "ta-IN", "target_language_code": "en-IN",
        })
        body = r.json()
        assert body["translated"] == "வணக்கம்"
        assert "error" in body

    def test_translates_via_sarvam_when_key_present(self, client, monkeypatch):
        monkeypatch.setenv("SARVAM_API_KEY", "sk-test")

        class _Resp:
            status_code = 200

            def json(self):
                return {"translated_text": "Hello", "source_language_code": "ta-IN"}

        monkeypatch.setattr(services.translation_service.httpx, "post", lambda *a, **k: _Resp())
        r = client.post("/api/translate", json={
            "text": "வணக்கம்", "source_language_code": "ta-IN", "target_language_code": "en-IN",
        })
        assert r.json()["translated"] == "Hello"


class TestCallbacks:
    def test_add_callback(self, client, monkeypatch):
        monkeypatch.setattr(callback_repo, "save", lambda rec: True)
        r = client.post("/api/callbacks", json={"phone": "+9199", "callback_time": "tomorrow"})
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert r.json()["callback"]["callback_time"] == "tomorrow"

    def test_mark_done(self, client, monkeypatch):
        monkeypatch.setattr(callback_repo, "mark_done", lambda cid, done: True)
        r = client.post("/api/callbacks/5/done", json={"done": True})
        assert r.json()["success"] is True
