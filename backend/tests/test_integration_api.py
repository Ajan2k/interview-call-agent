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
    call_repo,
    voice_config_repo,
    candidate_repo,
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
    monkeypatch.setattr(voice_config_repo, "get", lambda: None)


class TestHealth:
    def test_health_ok_shape(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["databaseConnected"] is False  # get_connection mocked to None
        assert body["databaseType"] == "In-Memory (Fallback)"

    def test_health_reports_current_stack(self, client):
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


class TestCandidatesAPI:
    def test_get_candidates_list(self, client):
        r = client.get("/api/candidates")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert "X-Total-Count" in r.headers
        assert r.headers["X-Limit"] == "50"
        assert r.headers["X-Offset"] == "0"

    def test_get_candidates_pagination_params(self, client):
        r = client.get("/api/candidates?limit=10&offset=5")
        assert r.status_code == 200
        assert r.headers["X-Limit"] == "10"
        assert r.headers["X-Offset"] == "5"

    def test_get_behavioral_defaults(self, client):
        r = client.get("/api/candidates/behavioral-defaults")
        assert r.status_code == 200
        data = r.json()
        assert "questions" in data
        assert len(data["questions"]) == 5

    def test_get_nonexistent_candidate_404(self, client):
        r = client.get("/api/candidates/nonexistent-id-999")
        assert r.status_code == 404


class TestCallHistory:
    def test_call_history_falls_back_to_jsonl(self, client, monkeypatch):
        r = client.get("/api/call-history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_call_transcript_jsonl_fallback(self, client, monkeypatch):
        from routes.calls import _CALLS_JSONL
        import json
        monkeypatch.setattr(call_repo, "get_transcript", lambda cid: None)
        # Create a mock call in jsonl
        monkeypatch.setattr("routes.calls._read_jsonl", lambda path: [{
            "id": "mock_call_123",
            "phone": "+919876543210",
            "direction": "incoming",
            "start": "2026-10-07 10:00:00",
            "candidate_id": "cand_123",
            "candidate_name": "Test Candidate",
            "transcript": [{"role": "caller", "text": "Hello"}],
        }])
        r = client.get("/api/call-history/mock_call_123/transcript")
        assert r.status_code == 200
        data = r.json()
        assert data["found"] is True
        assert data["candidate_id"] == "cand_123"
        assert data["candidate_name"] == "Test Candidate"
        assert len(data["transcript"]) == 1

    def test_recordings_missing_file_404(self, client):
        r = client.get("/api/recordings/nonexistent.wav")
        assert r.status_code == 404


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
