"""Unit tests for the lead/meeting/callback logging helpers and the CallRecorder.

DB writes are mocked (db_save_* patched to return False -> forces the JSONL/file
fallback path, which we point at a tmp dir so nothing touches the real logs).
"""
import io
import json
import os
import wave

import pytest

import voice

pytestmark = pytest.mark.unit


class TestLogMeeting:
    def test_writes_jsonl_when_db_unavailable(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.db, "db_save_meeting", lambda rec: False)
        path = tmp_path / "logs" / "meetings.jsonl"
        monkeypatch.setattr(voice, "MEETINGS_LOG_PATH", str(path))

        voice.log_meeting("Mon 3pm", session_state)

        assert session_state["meeting_logged"] is True
        assert session_state["meeting_details"] == "Mon 3pm"
        rec = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec["details"] == "Mon 3pm"
        assert rec["call_id"] == "test-call-123"
        assert rec["direction"] == "outgoing"  # outbound -> outgoing

    def test_db_success_skips_file_write(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.db, "db_save_meeting", lambda rec: True)
        path = tmp_path / "logs" / "meetings.jsonl"
        monkeypatch.setattr(voice, "MEETINGS_LOG_PATH", str(path))
        voice.log_meeting("Tue 10am", session_state)
        assert not path.exists()

    def test_idempotent_only_logs_once(self, tmp_path, monkeypatch, session_state):
        recorded = []
        monkeypatch.setattr(voice.db, "db_save_meeting", lambda rec: recorded.append(rec) or True)
        voice.log_meeting("first", session_state)
        voice.log_meeting("second", session_state)  # ignored: meeting_logged already set
        assert len(recorded) == 1
        assert session_state["meeting_details"] == "first"

    def test_inbound_direction_is_incoming(self, monkeypatch, session_state):
        session_state["call_mode"] = "inbound"
        captured = {}
        monkeypatch.setattr(voice.db, "db_save_meeting", lambda rec: captured.update(rec) or True)
        voice.log_meeting("now", session_state)
        assert captured["direction"] == "incoming"


class TestLogCallback:
    def test_writes_jsonl_fallback(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.db, "db_save_callback", lambda rec: False)
        # log_callback builds path = dirname(__file__)/logs/callbacks.jsonl, so patch
        # __file__ rather than os.path.dirname (which it also calls on the full path).
        monkeypatch.setattr(voice, "__file__", str(tmp_path / "voice.py"))

        voice.log_callback("tomorrow 5pm", session_state)

        path = tmp_path / "logs" / "callbacks.jsonl"
        rec = json.loads(path.read_text(encoding="utf-8").strip())
        assert rec["callback_time"] == "tomorrow 5pm"
        assert session_state["callback_logged"] is True

    def test_empty_details_ignored(self, monkeypatch, session_state):
        called = []
        monkeypatch.setattr(voice.db, "db_save_callback", lambda rec: called.append(rec) or True)
        voice.log_callback("", session_state)
        assert called == []
        assert "callback_logged" not in session_state

    def test_idempotent(self, monkeypatch, session_state):
        called = []
        monkeypatch.setattr(voice.db, "db_save_callback", lambda rec: called.append(rec) or True)
        voice.log_callback("a", session_state)
        voice.log_callback("b", session_state)
        assert len(called) == 1


class TestLogLead:
    def test_appends_line_to_leads_log(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))
        voice.log_lead("status=interested", session_state)

        leads = (tmp_path / "leads.log").read_text(encoding="utf-8")
        assert "status=interested" in leads
        assert "mode=outbound" in leads
        assert "lang=ta-IN" in leads
        assert session_state["lead_logged"] is True

    def test_empty_details_ignored(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))
        voice.log_lead("", session_state)
        assert not (tmp_path / "leads.log").exists()
        assert "lead_logged" not in session_state

    def test_idempotent(self, tmp_path, monkeypatch, session_state):
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))
        voice.log_lead("first", session_state)
        voice.log_lead("second", session_state)
        leads = (tmp_path / "leads.log").read_text(encoding="utf-8")
        assert "first" in leads
        assert "second" not in leads


class TestCallRecorder:
    def test_save_returns_none_when_no_audio(self, monkeypatch, tmp_path):
        monkeypatch.setattr(voice, "RECORDINGS_DIR", str(tmp_path))
        rec = voice.CallRecorder("call-x")
        assert rec.save() is None

    def test_mixes_and_writes_wav(self, monkeypatch, tmp_path):
        monkeypatch.setattr(voice, "RECORDINGS_DIR", str(tmp_path))
        rec = voice.CallRecorder("call-y")
        rec.add_caller(b"\x10\x00" * 100)
        rec.add_agent(b"\x20\x00" * 100, at_time=rec.start_time)  # no padding

        fname = rec.save()
        assert fname == "call-y.wav"
        path = tmp_path / fname
        with wave.open(str(path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 100

    def test_agent_track_padded_to_playback_time(self, monkeypatch, tmp_path):
        monkeypatch.setattr(voice, "RECORDINGS_DIR", str(tmp_path))
        rec = voice.CallRecorder("call-z")
        # Agent speaks 0.5s after call start -> track padded with silence to that offset.
        rec.add_agent(b"\x30\x00" * 10, at_time=rec.start_time + 0.5)
        expected_pad = int(0.5 * voice.CallRecorder.BYTES_PER_SEC)
        expected_pad -= expected_pad % 2
        assert len(rec.agent_track) == expected_pad + 20
