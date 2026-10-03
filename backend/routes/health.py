from fastapi import APIRouter
from core.config import settings
from services.database_manager import db_manager
from schemas.health import HealthResponseSchema

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponseSchema)
def get_health():
    groq_key = settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else ""
    azure_key = settings.AZURE_SPEECH_KEY.get_secret_value() if settings.AZURE_SPEECH_KEY else ""
    has_api_key = bool(groq_key and azure_key)

    db_manager.init_db()
    conn = db_manager.get_connection()
    db_connected = bool(conn)
    if conn:
        conn.close()

    return {
        "status": "ok",
        "hasApiKey": has_api_key,
        "databaseConnected": db_connected,
        "databaseType": "PostgreSQL" if db_connected else "In-Memory (Fallback)",
        "services": {
            "stt": "Sarvam (Groq Whisper fallback)",
            "llm": "Groq LLaMA 3.1 8B Instant",
            "tts": "Cartesia Sonic 3.5 (Sarvam/Azure fallback)",
        },
    }
