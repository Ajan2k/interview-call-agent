import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import Field, SecretStr, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_logs_dir() -> Path:
    return _get_backend_dir() / "logs"


def _get_recordings_dir() -> Path:
    return _get_backend_dir() / "recordings"


def _get_prompts_dir() -> Path:
    return _get_backend_dir() / "prompts"


class Settings(BaseSettings):
    """Application settings with SecretStr for credentials and PostgresDsn."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(_get_backend_dir(), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "TeleForce AI Call Agent"
    APP_VERSION: str = "1.0.0"

    # Paths initialized using default_factory
    BACKEND_DIR: Path = Field(default_factory=_get_backend_dir)
    LOGS_DIR: Path = Field(default_factory=_get_logs_dir)
    RECORDINGS_DIR: Path = Field(default_factory=_get_recordings_dir)
    PROMPTS_DIR: Path = Field(default_factory=_get_prompts_dir)

    # PostgreSQL Database Configuration
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = SecretStr("1234")
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "skyagent"
    DATABASE_URL: Optional[PostgresDsn] = None

    # LLM Settings & Provider Base URLs
    LLM_PROVIDER: str = "groq"
    SARVAM_LLM_BASE_URL: str = "https://api.sarvam.ai/v1"
    CEREBRAS_LLM_BASE_URL: str = "https://api.cerebras.ai/v1"
    GEMINI_LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    TOGETHER_LLM_BASE_URL: str = "https://api.together.xyz/v1"
    FALLBACK_MODEL: str = "llama-3.1-8b-instant"

    GROQ_API_KEY: Optional[SecretStr] = None
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"

    TOGETHER_API_KEY: Optional[SecretStr] = None
    TOGETHER_LLM_MODEL: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    GEMINI_API_KEY: Optional[SecretStr] = None
    GEMINI_LLM_MODEL: str = "gemini-flash-lite-latest"

    CEREBRAS_API_KEY: Optional[SecretStr] = None
    CEREBRAS_LLM_MODEL: str = "zai-glm-4.7"

    SARVAM_API_KEY: Optional[SecretStr] = None
    SARVAM_LLM_MODEL: str = "sarvam-30b"

    # Speech Synthesis (TTS) & Recognition (STT) URLs & Configuration
    SARVAM_TTS_URL: str = "https://api.sarvam.ai/text-to-speech"
    SARVAM_TTS_SPEAKER: str = "anushka"
    CARTESIA_TTS_URL: str = "https://api.cartesia.ai/tts/bytes"
    CARTESIA_VERSION: str = "2024-11-13"

    CARTESIA_API_KEY: Optional[SecretStr] = None
    CARTESIA_MODEL_ID: str = "sonic-2"
    CARTESIA_KAVITHA_VOICE_ID: Optional[str] = None
    CARTESIA_VOICE_TA: Optional[str] = None
    CARTESIA_VOICE_EN: Optional[str] = None
    CARTESIA_VOICE_HI: Optional[str] = None

    AZURE_SPEECH_KEY: Optional[SecretStr] = None
    AZURE_SPEECH_REGION: str = "centralindia"
    AZURE_TTS_URL_TEMPLATE: str = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    SARVAM_STT_URL: str = "https://api.sarvam.ai/speech-to-text"
    SARVAM_STT_MODEL: str = "saarika:v2.5"

    SARVAM_TRANSLATE_URL: str = "https://api.sarvam.ai/translate"

    # Audio Recording Retention
    AUDIO_RETENTION_MAX_DAYS: int = 30
    AUDIO_RETENTION_MAX_STORAGE_MB: float = 5000.0

    # Branding & Agent Persona
    COMPANY_NAME: str = "TalentAI Recruiting"
    AGENT_NAME: str = "Alex"

    # Call Lifecycle
    MAX_CALL_DURATION_SECS: int = 300
    LOG_API_POLLING: bool = False

    @property
    def postgres_dsn(self) -> str:
        """Returns the PostgreSQL connection string."""
        if self.DATABASE_URL:
            return str(self.DATABASE_URL)
        pwd = self.POSTGRES_PASSWORD.get_secret_value() if self.POSTGRES_PASSWORD else ""
        return f"postgresql://{self.POSTGRES_USER}:{pwd}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Safe Key & Model Accessors (supporting dynamic runtime/test overrides)
    def _get_key(self, env_name: str, secret_field: Optional[SecretStr]) -> str:
        # In pytest runs, always respect monkeypatch delenv/setenv strictly
        if "PYTEST_CURRENT_TEST" in os.environ:
            return os.getenv(env_name, "")
        val = os.getenv(env_name)
        if val is not None:
            return val
        return secret_field.get_secret_value() if secret_field else ""

    def get_sarvam_api_key(self) -> str:
        return self._get_key("SARVAM_API_KEY", self.SARVAM_API_KEY)

    def get_groq_api_key(self) -> str:
        return self._get_key("GROQ_API_KEY", self.GROQ_API_KEY)

    def get_together_api_key(self) -> str:
        return self._get_key("TOGETHER_API_KEY", self.TOGETHER_API_KEY)

    def get_gemini_api_key(self) -> str:
        return self._get_key("GEMINI_API_KEY", self.GEMINI_API_KEY)

    def get_cerebras_api_key(self) -> str:
        return self._get_key("CEREBRAS_API_KEY", self.CEREBRAS_API_KEY)

    def get_cartesia_api_key(self) -> str:
        return self._get_key("CARTESIA_API_KEY", self.CARTESIA_API_KEY)

    def get_azure_speech_key(self) -> str:
        return self._get_key("AZURE_SPEECH_KEY", self.AZURE_SPEECH_KEY)

    def get_azure_speech_region(self) -> str:
        return os.getenv("AZURE_SPEECH_REGION", self.AZURE_SPEECH_REGION)

    def get_llm_provider(self) -> str:
        return os.getenv("LLM_PROVIDER", self.LLM_PROVIDER).lower()

    def get_groq_model(self) -> str:
        return os.getenv("GROQ_LLM_MODEL", self.GROQ_LLM_MODEL)

    def get_together_model(self) -> str:
        return os.getenv("TOGETHER_LLM_MODEL", self.TOGETHER_LLM_MODEL)

    def get_gemini_model(self) -> str:
        return os.getenv("GEMINI_LLM_MODEL", self.GEMINI_LLM_MODEL)

    def get_cerebras_model(self) -> str:
        return os.getenv("CEREBRAS_LLM_MODEL", self.CEREBRAS_LLM_MODEL)

    def get_sarvam_model(self) -> str:
        return os.getenv("SARVAM_LLM_MODEL", self.SARVAM_LLM_MODEL)

    def get_sarvam_stt_model(self) -> str:
        return os.getenv("SARVAM_STT_MODEL", self.SARVAM_STT_MODEL)

    def get_sarvam_tts_speaker(self) -> str:
        return os.getenv("SARVAM_TTS_SPEAKER", self.SARVAM_TTS_SPEAKER)

    def get_cartesia_model(self) -> str:
        return os.getenv("CARTESIA_MODEL_ID", self.CARTESIA_MODEL_ID)

    def get_cartesia_voice(self, lang: str) -> str:
        voices = {
            "ta-IN": os.getenv("CARTESIA_VOICE_TA", os.getenv("CARTESIA_KAVITHA_VOICE_ID", self.CARTESIA_VOICE_TA or self.CARTESIA_KAVITHA_VOICE_ID or "")),
            "en-IN": os.getenv("CARTESIA_VOICE_EN", self.CARTESIA_VOICE_EN or ""),
            "hi-IN": os.getenv("CARTESIA_VOICE_HI", self.CARTESIA_VOICE_HI or ""),
        }
        return voices.get(lang) or os.getenv("CARTESIA_KAVITHA_VOICE_ID", self.CARTESIA_KAVITHA_VOICE_ID or "")


# Singleton instance
settings = Settings()
