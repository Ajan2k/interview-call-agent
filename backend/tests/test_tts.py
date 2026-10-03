"""Unit tests for the TTS provider functions in voice.py:
cartesia_tts_fetch (primary, Sonic 3.5 / Kavitha), sarvam_tts_fetch, azure_tts_fetch,
and the tts_fetch fallback chain (Cartesia -> Sarvam -> Azure).

All HTTP is faked — no network. We patch voice.httpx.AsyncClient with a fake whose
.post returns a canned response, and capture the request payload/headers/url for
assertions.
"""
import base64
import io
import wave

import pytest

from routes import voice

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", json_data=None, text=""):
        self.status_code = status_code
        self.content = content
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Drop-in for httpx.AsyncClient used as `async with ... as client: await client.post(...)`.

    Records the last post() call on the class-level `.captured` so tests can inspect it.
    """
    captured = None

    def __init__(self, response):
        self._response = response

    def __call__(self, *args, **kwargs):
        # httpx.AsyncClient(...) is called with no args in voice.py; return self.
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        type(self).captured = {"url": url, **kwargs}
        return self._response


@pytest.fixture
def patch_httpx(monkeypatch):
    """Return a helper that installs a fake AsyncClient returning `response`."""
    def _install(response):
        _FakeAsyncClient.captured = None
        fake = _FakeAsyncClient(response)
        monkeypatch.setattr(voice.httpx, "AsyncClient", fake)
        return fake
    return _install


def _wav(sample_rate=16000, n_frames=80):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x01\x00" * n_frames)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Cartesia (primary — Sonic 3.5, Kavitha voice)
# --------------------------------------------------------------------------- #
class TestCartesia:
    async def test_no_api_key_returns_empty(self, patch_httpx):
        # _isolate_env autouse fixture guarantees CARTESIA_API_KEY is unset.
        out = await voice.cartesia_tts_fetch("hello", "ta-IN")
        assert out == b""
        assert _FakeAsyncClient.captured is None  # never made a request

    async def test_no_voice_id_skips_request(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "key-123")
        # No CARTESIA_KAVITHA_VOICE_ID / per-language ids set.
        patch_httpx(_FakeResponse(200, content=b"PCMDATA"))
        out = await voice.cartesia_tts_fetch("hello", "ta-IN")
        assert out == b""
        assert _FakeAsyncClient.captured is None

    async def test_kavitha_voice_used_for_tamil(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "key-123")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "kavitha-uuid")
        patch_httpx(_FakeResponse(200, content=b"RAWPCMBYTES"))

        out = await voice.cartesia_tts_fetch("வணக்கம்", "ta-IN")

        assert out == b"RAWPCMBYTES"  # raw PCM passed straight through, no header strip
        cap = _FakeAsyncClient.captured
        assert cap["url"] == voice.CARTESIA_TTS_URL
        body = cap["json"]
        assert body["voice"] == {"mode": "id", "id": "kavitha-uuid"}
        assert body["language"] == "ta"  # ta-IN -> ISO-639-1 "ta"
        assert body["output_format"] == {
            "container": "raw", "encoding": "pcm_s16le", "sample_rate": 16000,
        }
        assert cap["headers"]["X-API-Key"] == "key-123"
        assert cap["headers"]["Cartesia-Version"] == voice.CARTESIA_VERSION

    async def test_default_model_is_sonic(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "v")
        patch_httpx(_FakeResponse(200, content=b"x"))
        await voice.cartesia_tts_fetch("hi", "ta-IN")
        assert _FakeAsyncClient.captured["json"]["model_id"] == "sonic-2"

    async def test_model_id_overridable_via_env(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "v")
        monkeypatch.setenv("CARTESIA_MODEL_ID", "sonic-3.5")
        patch_httpx(_FakeResponse(200, content=b"x"))
        await voice.cartesia_tts_fetch("hi", "ta-IN")
        assert _FakeAsyncClient.captured["json"]["model_id"] == "sonic-3.5"

    async def test_per_language_override_beats_kavitha_default(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "kavitha")
        monkeypatch.setenv("CARTESIA_VOICE_EN", "english-voice")
        patch_httpx(_FakeResponse(200, content=b"x"))
        await voice.cartesia_tts_fetch("hello", "en-IN")
        assert _FakeAsyncClient.captured["json"]["voice"]["id"] == "english-voice"
        assert _FakeAsyncClient.captured["json"]["language"] == "en"

    async def test_unknown_lang_falls_back_to_kavitha(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "kavitha")
        patch_httpx(_FakeResponse(200, content=b"x"))
        await voice.cartesia_tts_fetch("hi", "de-DE")
        assert _FakeAsyncClient.captured["json"]["voice"]["id"] == "kavitha"

    async def test_non_200_returns_empty(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "v")
        patch_httpx(_FakeResponse(401, text="unauthorized"))
        out = await voice.cartesia_tts_fetch("hi", "ta-IN")
        assert out == b""

    async def test_exception_returns_empty(self, monkeypatch):
        monkeypatch.setenv("CARTESIA_API_KEY", "k")
        monkeypatch.setenv("CARTESIA_KAVITHA_VOICE_ID", "v")

        class _Boom:
            def __call__(self, *a, **k):
                return self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *e):
                return False

            async def post(self, *a, **k):
                raise RuntimeError("network down")

        monkeypatch.setattr(voice.httpx, "AsyncClient", _Boom())
        assert await voice.cartesia_tts_fetch("hi", "ta-IN") == b""


# --------------------------------------------------------------------------- #
# Sarvam
# --------------------------------------------------------------------------- #
class TestSarvam:
    async def test_no_key_returns_empty(self):
        assert await voice.sarvam_tts_fetch("hi", "ta-IN") == b""

    async def test_success_decodes_and_strips_header(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("SARVAM_API_KEY", "sk")
        audio_b64 = base64.b64encode(_wav()).decode()
        patch_httpx(_FakeResponse(200, json_data={"audios": [audio_b64]}))

        out = await voice.sarvam_tts_fetch("hi", "ta-IN")
        assert out and not out.startswith(b"RIFF")  # header stripped to raw PCM
        assert _FakeAsyncClient.captured["json"]["model"] == "bulbul:v2"
        assert _FakeAsyncClient.captured["json"]["target_language_code"] == "ta-IN"

    async def test_unsupported_lang_defaults_to_en_in(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("SARVAM_API_KEY", "sk")
        patch_httpx(_FakeResponse(200, json_data={"audios": [base64.b64encode(_wav()).decode()]}))
        await voice.sarvam_tts_fetch("hi", "fr-FR")
        assert _FakeAsyncClient.captured["json"]["target_language_code"] == "en-IN"

    async def test_empty_audios_returns_empty(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("SARVAM_API_KEY", "sk")
        patch_httpx(_FakeResponse(200, json_data={"audios": []}))
        assert await voice.sarvam_tts_fetch("hi", "ta-IN") == b""

    async def test_non_200_returns_empty(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("SARVAM_API_KEY", "sk")
        patch_httpx(_FakeResponse(500, text="server error"))
        assert await voice.sarvam_tts_fetch("hi", "ta-IN") == b""


# --------------------------------------------------------------------------- #
# Azure
# --------------------------------------------------------------------------- #
class TestAzure:
    async def test_no_key_returns_empty(self):
        assert await voice.azure_tts_fetch("hi", "ta-IN") == b""

    async def test_success_strips_header_and_picks_tamil_voice(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("AZURE_SPEECH_KEY", "az")
        patch_httpx(_FakeResponse(200, content=_wav()))
        out = await voice.azure_tts_fetch("vanakkam", "ta-IN")
        assert out and not out.startswith(b"RIFF")
        # SSML content should reference the Tamil neural voice.
        sent = _FakeAsyncClient.captured["content"].decode("utf-8")
        assert "ta-IN-PallaviNeural" in sent

    async def test_unknown_lang_uses_english_voice(self, monkeypatch, patch_httpx):
        monkeypatch.setenv("AZURE_SPEECH_KEY", "az")
        patch_httpx(_FakeResponse(200, content=_wav()))
        await voice.azure_tts_fetch("hello", "xx-XX")
        assert "en-IN-NeerjaNeural" in _FakeAsyncClient.captured["content"].decode("utf-8")


# --------------------------------------------------------------------------- #
# tts_fetch fallback chain: Cartesia -> Sarvam -> Azure
# --------------------------------------------------------------------------- #
class TestTtsFetchChain:
    async def test_prefers_cartesia_when_it_returns_audio(self, monkeypatch):
        async def cart(text, lang):
            return b"CARTESIA"

        async def sarvam(text, lang):
            raise AssertionError("should not reach Sarvam")

        monkeypatch.setattr(voice, "cartesia_tts_fetch", cart)
        monkeypatch.setattr(voice, "sarvam_tts_fetch", sarvam)
        assert await voice.tts_fetch("hi", "ta-IN") == b"CARTESIA"

    async def test_falls_back_to_sarvam_when_cartesia_empty(self, monkeypatch):
        monkeypatch.setattr(voice, "cartesia_tts_fetch", lambda t, l: _coro(b""))
        monkeypatch.setattr(voice, "sarvam_tts_fetch", lambda t, l: _coro(b"SARVAM"))
        monkeypatch.setattr(voice, "azure_tts_fetch", lambda t, l: _coro(b"AZURE"))
        assert await voice.tts_fetch("hi", "ta-IN") == b"SARVAM"

    async def test_falls_back_to_azure_when_both_empty(self, monkeypatch):
        monkeypatch.setattr(voice, "cartesia_tts_fetch", lambda t, l: _coro(b""))
        monkeypatch.setattr(voice, "sarvam_tts_fetch", lambda t, l: _coro(b""))
        monkeypatch.setattr(voice, "azure_tts_fetch", lambda t, l: _coro(b"AZURE"))
        assert await voice.tts_fetch("hi", "ta-IN") == b"AZURE"


def _coro(value):
    async def _c():
        return value
    return _c()
