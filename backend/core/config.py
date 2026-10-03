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

    # LLM Settings
    LLM_PROVIDER: str = "groq"
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

    # Speech Synthesis (TTS) & Recognition (STT)
    CARTESIA_API_KEY: Optional[SecretStr] = None
    CARTESIA_MODEL_ID: str = "sonic-2"
    CARTESIA_KAVITHA_VOICE_ID: Optional[str] = None
    CARTESIA_VOICE_TA: Optional[str] = None
    CARTESIA_VOICE_EN: Optional[str] = None
    CARTESIA_VOICE_HI: Optional[str] = None

    AZURE_SPEECH_KEY: Optional[SecretStr] = None
    AZURE_SPEECH_REGION: str = "centralindia"

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


# Singleton instance
settings = Settings()
