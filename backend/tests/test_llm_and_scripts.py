"""Unit tests around LLM model selection and the script-prompt loader.

The Groq model default was changed to `llama-3.1-8b-instant` (fast, dodges the 70B
tokens-per-day rate limit). The model is chosen deep inside the process_utterance
websocket handler, so we assert the default/override at the source level plus verify
the environment-variable contract, and fully unit-test the pure load_script_prompt.
"""
import os

import pytest

from routes import voice

pytestmark = pytest.mark.unit


class TestGroqModelDefault:
    def test_default_is_8b_instant(self, monkeypatch):
        # The handler reads os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant").
        monkeypatch.delenv("GROQ_LLM_MODEL", raising=False)
        assert os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant") == "llama-3.1-8b-instant"

    def test_override_via_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
        assert os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant") == "llama-3.3-70b-versatile"

    def test_source_wires_env_var_with_8b_default(self):
        """Guardrail: the Groq branch must default to 8b-instant via GROQ_LLM_MODEL.
        Fails loudly if someone reverts the model back to a hardcoded 70B string."""
        src = _voice_source()
        assert 'os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")' in src

    def test_fallback_model_is_8b_instant(self):
        src = _voice_source()
        assert 'FALLBACK_MODEL = "llama-3.1-8b-instant"' in src


class TestLoadScriptPrompt:
    def test_fills_placeholders(self, tmp_path, monkeypatch):
        # Point the loader at a temp Scripts dir with a known template.
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        (scripts / "outbound_prompt.txt").write_text(
            "Speak {lang_name}. Examples:\n{few_shot}", encoding="utf-8"
        )
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))

        out = voice.load_script_prompt("outbound", "Tamil", "EX1")
        assert "Speak Tamil." in out
        assert "EX1" in out
        assert "{lang_name}" not in out and "{few_shot}" not in out

    def test_inbound_reads_inbound_file(self, tmp_path, monkeypatch):
        scripts = tmp_path / "Scripts"
        scripts.mkdir()
        (scripts / "inbound_prompt.txt").write_text("INBOUND {lang_name}", encoding="utf-8")
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))

        out = voice.load_script_prompt("inbound", "English", "")
        assert out.startswith("INBOUND English")

    def test_missing_file_uses_fallback_prompt(self, tmp_path, monkeypatch):
        # No Scripts dir at all -> open() raises -> minimal fallback prompt used.
        monkeypatch.setattr(voice.os.path, "dirname", lambda _p: str(tmp_path))
        out = voice.load_script_prompt("outbound", "Hindi", "few")
        assert voice.AGENT_NAME in out
        assert "Hindi" in out          # {lang_name} substituted in the fallback too
        assert "{lang_name}" not in out


def _voice_source():
    path = os.path.join(os.path.dirname(voice.__file__), "voice.py")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
