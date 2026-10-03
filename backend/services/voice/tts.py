import os
import time
import base64
import asyncio
import logging
import httpx
from fastapi import WebSocket
from services.voice.audio import AudioProcessor
from core.config import settings

logger = logging.getLogger("voice.tts")

SARVAM_TTS_URL = settings.SARVAM_TTS_URL
CARTESIA_TTS_URL = settings.CARTESIA_TTS_URL
CARTESIA_VERSION = settings.CARTESIA_VERSION

AZURE_VOICES = {
    "en-IN": "en-IN-NeerjaNeural",
    "ta-IN": "ta-IN-PallaviNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "te-IN": "te-IN-ShrutiNeural",
    "kn-IN": "kn-IN-SapnaNeural",
    "ml-IN": "ml-IN-SobhanaNeural",
}


class TTSService:
    """Manages Text-to-Speech synthesis across Cartesia, Sarvam, and Azure providers."""

    def __init__(self, audio_processor: AudioProcessor | None = None):
        self.audio_processor = audio_processor or AudioProcessor()

    async def azure_tts_fetch(self, text: str, lang: str) -> bytes:
        """Fetch audio from Microsoft Azure Neural TTS."""
        azure_key = settings.get_azure_speech_key()
        azure_region = settings.get_azure_speech_region()
        if not azure_key:
            return b""

        voice = AZURE_VOICES.get(lang, "en-IN-NeerjaNeural")

        ssml = f"""<speak version='1.0' xml:lang='{lang}'>
        <voice name='{voice}'>
            <prosody rate='-2%' pitch='+1%'>{text}</prosody>
        </voice>
    </speak>"""

        url = settings.AZURE_TTS_URL_TEMPLATE.format(region=azure_region)
        headers = {
            "Ocp-Apim-Subscription-Key": azure_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
            "User-Agent": "TalentAI-Interviewer",
        }

        try:
            t0 = time.time()
            async with httpx.AsyncClient() as client:
                res = await client.post(url, content=ssml.encode("utf-8"), headers=headers, timeout=15.0)
                if res.status_code != 200:
                    logger.error(f"[AZURE TTS] Error {res.status_code}: {res.text[:200]}")
                    return b""
                audio_bytes = self.audio_processor.strip_wav_header(res.content)
                logger.info(
                    f"[AZURE TTS] Fetched '{text[:40]}' via {voice} in {int((time.time()-t0)*1000)}ms. "
                    f"Raw: {len(audio_bytes)} bytes."
                )
                return audio_bytes
        except Exception as e:
            logger.error(f"[AZURE TTS] Exception: {e}")
            return b""

    async def cartesia_tts_fetch(self, text: str, lang: str) -> bytes:
        """Fetch audio from Cartesia Sonic 3.5 TTS."""
        cartesia_key = settings.get_cartesia_api_key()
        if not cartesia_key:
            return b""

        voice_id = settings.get_cartesia_voice(lang)
        if not voice_id:
            return b""

        cartesia_lang = (lang or "en-IN").split("-")[0]

        payload = {
            "model_id": settings.get_cartesia_model(),
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "language": cartesia_lang,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            },
        }
        headers = {
            "X-API-Key": cartesia_key,
            "Cartesia-Version": CARTESIA_VERSION,
            "Content-Type": "application/json",
        }

        try:
            t0 = time.time()
            async with httpx.AsyncClient() as client:
                res = await client.post(CARTESIA_TTS_URL, json=payload, headers=headers, timeout=15.0)
                if res.status_code != 200:
                    logger.error(f"[CARTESIA TTS] Error {res.status_code}: {res.text[:200]}")
                    return b""
                audio_bytes = res.content
                logger.info(
                    f"[CARTESIA TTS] Fetched '{text[:40]}' via {payload['model_id']} "
                    f"(voice {voice_id[:8]}…, {cartesia_lang}) in {int((time.time()-t0)*1000)}ms. "
                    f"Raw: {len(audio_bytes)} bytes."
                )
                return audio_bytes
        except Exception as e:
            logger.error(f"[CARTESIA TTS] Exception: {e}")
            return b""

    async def sarvam_tts_fetch(self, text: str, lang: str) -> bytes:
        """Fetch audio from Sarvam Bulbul TTS."""
        sarvam_key = settings.get_sarvam_api_key()
        if not sarvam_key:
            return b""

        supported = {"en-IN", "ta-IN", "hi-IN", "te-IN", "kn-IN", "ml-IN"}
        payload = {
            "text": text,
            "target_language_code": lang if lang in supported else "en-IN",
            "speaker": settings.get_sarvam_tts_speaker(),
            "model": "bulbul:v2",
            "speech_sample_rate": 16000,
            "enable_preprocessing": True,
            "pace": 0.93,
        }
        headers = {"api-subscription-key": sarvam_key, "Content-Type": "application/json"}

        try:
            t0 = time.time()
            async with httpx.AsyncClient() as client:
                res = await client.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=15.0)
                if res.status_code != 200:
                    logger.error(f"[SARVAM TTS] Error {res.status_code}: {res.text[:200]}")
                    return b""
                audios = res.json().get("audios") or []
                if not audios:
                    logger.error("[SARVAM TTS] Empty audios in response.")
                    return b""
                audio_bytes = self.audio_processor.strip_wav_header(base64.b64decode(audios[0]))
                logger.info(
                    f"[SARVAM TTS] Fetched '{text[:40]}' via bulbul:v2 in {int((time.time()-t0)*1000)}ms. "
                    f"Raw: {len(audio_bytes)} bytes."
                )
                return audio_bytes
        except Exception as e:
            logger.error(f"[SARVAM TTS] Exception: {e}")
            return b""

    async def tts_fetch(
        self,
        text: str,
        lang: str,
        cartesia_fetch_fn=None,
        sarvam_fetch_fn=None,
        azure_fetch_fn=None,
    ) -> bytes:
        """Primary: Cartesia Sonic 3.5. Fallbacks: Sarvam Bulbul -> Azure Neural."""
        cart_fn = cartesia_fetch_fn or self.cartesia_tts_fetch
        sarv_fn = sarvam_fetch_fn or self.sarvam_tts_fetch
        az_fn = azure_fetch_fn or self.azure_tts_fetch

        audio = await cart_fn(text, lang)
        if audio:
            return audio
        if settings.get_cartesia_api_key() and (
            settings.get_cartesia_voice("ta-IN")
            or settings.get_cartesia_voice("en-IN")
        ):
            logger.warning("[TTS] Cartesia failed — falling back to Sarvam.")

        audio = await sarv_fn(text, lang)
        if audio:
            return audio
        if settings.get_sarvam_api_key():
            logger.warning("[TTS] Sarvam failed — falling back to Azure.")
        return await az_fn(text, lang)

    async def dispatch_tts(
        self,
        text: str,
        lang: str,
        session_state: dict,
        websocket: WebSocket,
        fetch_fn=None,
    ) -> None:
        """Queue up a task with its creation time to handle async barge-ins."""
        f_fn = fetch_fn or self.tts_fetch
        task_time = time.time()
        task = asyncio.create_task(f_fn(text, lang))
        await session_state["tts_queue"].put((task_time, task))

    async def tts_playback_worker(self, session_state: dict, websocket: WebSocket) -> None:
        """Consumes TTS tasks in order and sends audio down the websocket."""
        queue = session_state["tts_queue"]
        while True:
            try:
                item = await queue.get()
                if not isinstance(item, tuple):
                    task_time, task = 0, item
                else:
                    task_time, task = item

                # Skip if a barge-in happened after this task was created
                if task_time < session_state.get("cancel_tts_before", 0):
                    queue.task_done()
                    continue

                audio_bytes = await task

                # Check again in case barge-in happened while awaiting the fetch
                if audio_bytes and task_time >= session_state.get("cancel_tts_before", 0):
                    await websocket.send_json({
                        "event": "media",
                        "media": {"payload": base64.b64encode(audio_bytes).decode("utf-8")},
                    })

                    # Estimate playback duration (16000 Hz * 2 bytes = 32000 bytes/sec)
                    duration_sec = len(audio_bytes) / 32000.0

                    now = time.time()
                    current_end = session_state.get("playback_end_time", 0)
                    playback_start = max(now, current_end)
                    session_state["playback_end_time"] = playback_start + duration_sec

                    recorder = session_state.get("recorder")
                    if recorder:
                        recorder.add_agent(audio_bytes, playback_start)

                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TTS WORKER] Error: {e}")
