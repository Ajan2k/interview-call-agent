"""Shared pytest fixtures for the backend test suite.

The backend imports (voice, routes, services) do NOT open a DB connection or
call any external API at import time, so importing them here is safe. Anything that
would touch Postgres, Groq, Sarvam, Cartesia, or Azure is mocked per-test.
"""
import os
import sys

import pytest

# Make the backend package importable when pytest is run from any cwd.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def session_state():
    """A minimal session_state dict shaped like the one voice.py builds per call.

    Only the keys the functions under test actually read/write are included; add
    more in a test if you exercise a code path that needs them.
    """
    return {
        "call_id": "test-call-123",
        "language_code": "ta-IN",
        "call_mode": "outbound",
        "phone": "+911234567890",
        "history": [],
        "transcript": [],
    }


@pytest.fixture
def wav_bytes():
    """Factory returning a valid in-memory WAV (RIFF) for a given sample rate/channels."""
    import io
    import wave

    def _make(sample_rate=16000, nchannels=1, sampwidth=2, n_frames=160):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(nchannels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x01\x00" * n_frames * nchannels)
        return buf.getvalue()

    return _make


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip provider API keys by default so no test accidentally hits a live API.

    A test that wants a key present sets it explicitly with monkeypatch.setenv.
    """
    for key in (
        "CARTESIA_API_KEY", "CARTESIA_KAVITHA_VOICE_ID", "CARTESIA_MODEL_ID",
        "SARVAM_API_KEY", "AZURE_SPEECH_KEY", "GROQ_API_KEY",
        "CARTESIA_VOICE_TA", "CARTESIA_VOICE_EN", "CARTESIA_VOICE_HI",
    ):
        monkeypatch.delenv(key, raising=False)
