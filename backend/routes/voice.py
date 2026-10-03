import os
import httpx
from fastapi import APIRouter, WebSocket
from core.logging import get_conversation_logger
from services import database_manager as db
from services.voice import (
    AudioProcessor,
    CallRecorder as BaseCallRecorder,
    MarkerService,
    PromptManager,
    TTSService,
    STTService,
    LLMService,
    VoiceSessionManager,
    COMPANY_NAME,
    AGENT_NAME,
    CALL_MODE,
    CARTESIA_TTS_URL,
    CARTESIA_VERSION,
    SPEECH_THRESHOLD,
    SILENCE_THRESHOLD,
    MIN_SPEECH_DURATION_MS,
    SILENCE_DURATION_MS,
    BARGE_IN_THRESHOLD,
    IDLE_TIMEOUT_SECS,
    MAX_CALL_DURATION_SECS,
)

from core.config import settings

convo_logger = get_conversation_logger()
router = APIRouter(tags=["voice"])

# Directory and log paths from settings
RECORDINGS_DIR = str(settings.RECORDINGS_DIR)
LOGS_DIR = str(settings.LOGS_DIR)
CALLS_LOG_PATH = os.path.join(LOGS_DIR, "calls.jsonl")
MEETINGS_LOG_PATH = os.path.join(LOGS_DIR, "meetings.jsonl")
LEADS_LOG_PATH = os.path.join(str(settings.BACKEND_DIR), "leads.log")

# Model configuration defaults (used by tests for env-var contracts & guardrails)
DEFAULT_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "qwen/qwen3.8-27b")
FALLBACK_MODEL = "openai/gpt-oss-20b"

# Initialize modular service instances
audio_processor = AudioProcessor()
marker_service = MarkerService()
prompt_manager = PromptManager(company_name=COMPANY_NAME, agent_name=AGENT_NAME)
tts_service = TTSService(audio_processor)
stt_service = STTService()
llm_service = LLMService()
session_manager = VoiceSessionManager(
    audio_processor=audio_processor,
    marker_service=marker_service,
    prompt_manager=prompt_manager,
    tts_service=tts_service,
    stt_service=stt_service,
    llm_service=llm_service,
)

# Export audio helpers
create_wav_buffer = audio_processor.create_wav_buffer
strip_wav_header = audio_processor.strip_wav_header


class CallRecorder(BaseCallRecorder):
    """Subclass that defaults to the module-level RECORDINGS_DIR dynamically."""

    def save(self, recordings_dir: str | None = None) -> str | None:
        target_dir = recordings_dir or globals().get("RECORDINGS_DIR", RECORDINGS_DIR)
        return super().save(recordings_dir=target_dir)


def load_script_prompt(call_mode: str, lang_name: str, few_shot: str) -> str:
    """Load sales script prompt using backend base dir."""
    base_dir = os.path.dirname(__file__)
    if base_dir.endswith("routes") or base_dir.endswith("routes" + os.sep):
        base_dir = os.path.dirname(base_dir)
    return prompt_manager.load_script_prompt(call_mode, lang_name, few_shot, base_dir=base_dir)


def add_transcript(session_state: dict, role: str, text: str, lang: str) -> None:
    return marker_service.add_transcript(session_state, role, text, lang)


def log_meeting(details: str, session_state: dict) -> None:
    return marker_service.log_meeting(
        details,
        session_state,
        db_save_fn=db.db_save_meeting,
        meetings_log_path=globals().get("MEETINGS_LOG_PATH", MEETINGS_LOG_PATH),
    )


def log_callback(details: str, session_state: dict) -> None:
    cb_dir = os.path.dirname(__file__)
    if cb_dir.endswith("routes") or cb_dir.endswith("routes" + os.sep):
        cb_dir = os.path.dirname(cb_dir)
    cb_path = os.path.join(cb_dir, "logs", "callbacks.jsonl")
    return marker_service.log_callback(
        details,
        session_state,
        db_save_fn=db.db_save_callback,
        callbacks_log_path=cb_path,
    )


def log_lead(details: str, session_state: dict) -> None:
    base_dir = os.path.dirname(__file__)
    if base_dir.endswith("routes") or base_dir.endswith("routes" + os.sep):
        base_dir = os.path.dirname(base_dir)
    leads_path = os.path.join(base_dir, "leads.log")
    return marker_service.log_lead(
        details,
        session_state,
        leads_log_path=leads_path,
    )


def extract_control_markers(text: str, session_state: dict) -> str:
    return marker_service.extract_control_markers(
        text,
        session_state,
        log_meeting_fn=globals()["log_meeting"],
        log_callback_fn=globals()["log_callback"],
        log_lead_fn=globals()["log_lead"],
    )


async def cartesia_tts_fetch(text: str, lang: str) -> bytes:
    return await tts_service.cartesia_tts_fetch(text, lang)


async def sarvam_tts_fetch(text: str, lang: str) -> bytes:
    return await tts_service.sarvam_tts_fetch(text, lang)


async def azure_tts_fetch(text: str, lang: str) -> bytes:
    return await tts_service.azure_tts_fetch(text, lang)


async def tts_fetch(text: str, lang: str) -> bytes:
    return await tts_service.tts_fetch(
        text,
        lang,
        cartesia_fetch_fn=globals()["cartesia_tts_fetch"],
        sarvam_fetch_fn=globals()["sarvam_tts_fetch"],
        azure_fetch_fn=globals()["azure_tts_fetch"],
    )


async def dispatch_tts(text: str, lang: str, session_state: dict, websocket: WebSocket) -> None:
    return await tts_service.dispatch_tts(
        text,
        lang,
        session_state,
        websocket,
        fetch_fn=globals()["tts_fetch"],
    )


async def tts_playback_worker(session_state: dict, websocket: WebSocket) -> None:
    return await tts_service.tts_playback_worker(session_state, websocket)


async def speak_fallback(websocket: WebSocket, session_state: dict) -> None:
    return await session_manager.speak_fallback(websocket, session_state)


async def finalize_call(websocket: WebSocket, session_state: dict, goodbye_text: str | None = None) -> None:
    return await session_manager.finalize_call(websocket, session_state, goodbye_text)


async def play_greeting(websocket: WebSocket, session_state: dict) -> None:
    return await session_manager.play_greeting(websocket, session_state)


async def process_utterance(utterance_bytes: bytes, session_state: dict, websocket: WebSocket) -> None:
    script_dir = os.path.dirname(os.path.dirname(__file__))
    return await session_manager.process_utterance(utterance_bytes, session_state, websocket, script_dir=script_dir)


@router.websocket("/api/voice/teleforce_stream")
async def teleforce_websocket_endpoint(websocket: WebSocket):
    await session_manager.handle_teleforce_stream(
        websocket,
        recordings_dir=globals().get("RECORDINGS_DIR", RECORDINGS_DIR),
        calls_log_path=globals().get("CALLS_LOG_PATH", CALLS_LOG_PATH),
    )
