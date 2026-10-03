import os
import logging
import httpx
from groq import AsyncGroq
from core.config import settings
from services.voice.prompts import (
    WHISPER_LANG_MAP,
    SUPPORTED_LANGS,
    FILLER_WORDS,
    NATIVE_LANG_NAMES,
)

logger = logging.getLogger("voice.stt")

SARVAM_STT_URL = settings.SARVAM_STT_URL


class STTService:
    """Manages Speech-to-Text transcription with Sarvam Saarika and Groq Whisper fallback,
    along with Indic script and language detection."""

    @staticmethod
    def contains_non_latin_script(text: str) -> bool:
        """Detect if transcript contains South Indian or Hindi script characters."""
        for c in text:
            cp = ord(c)
            # Tamil: 0B80-0BFF | Telugu: 0C00-0C7F | Kannada: 0C80-0CFF
            # Malayalam: 0D00-0D7F | Devanagari (Hindi): 0900-097F
            if 0x0900 <= cp <= 0x0D7F:
                return True
        return False

    async def transcribe_sarvam(self, wav_data: bytes, sarvam_key: str) -> tuple[str | None, str | None]:
        """Transcribe using Indic-specialised Sarvam Saarika."""
        try:
            stt_model = settings.get_sarvam_stt_model()
            logger.info(f"[ASR] Sending {len(wav_data)} bytes of WAV to Sarvam {stt_model}.")
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    SARVAM_STT_URL,
                    headers={"api-subscription-key": sarvam_key},
                    files={"file": ("audio.wav", wav_data, "audio/wav")},
                    data={"model": stt_model, "language_code": "unknown"},
                    timeout=15.0,
                )
            if res.status_code == 200:
                j = res.json()
                transcript = (j.get("transcript") or "").strip()
                lang_code = j.get("language_code") or "en-IN"
                logger.info(f"[ASR] Sarvam transcript: '{transcript}' (Lang: {lang_code})")
                return transcript, lang_code
            logger.error(f"[ASR] Sarvam error {res.status_code}: {res.text[:200]} — falling back to Groq Whisper.")
            return None, None
        except Exception as e:
            logger.error(f"[ASR] Sarvam exception: {e} — falling back to Groq Whisper.")
            return None, None

    async def transcribe_whisper(self, wav_data: bytes, groq_key: str) -> tuple[str | None, str | None]:
        """Transcribe using Groq Whisper fallback."""
        try:
            logger.info(f"[ASR] Sending {len(wav_data)} bytes of WAV to Groq Whisper.")
            asr_client = AsyncGroq(api_key=groq_key)
            transcription = await asr_client.audio.transcriptions.create(
                file=("audio.wav", wav_data),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                temperature=0.0,
            )
            transcript = (transcription.text or "").strip()
            detected_lang_short = getattr(transcription, "language", "en") or "en"
            lang_code = WHISPER_LANG_MAP.get(detected_lang_short, "en-IN")
            logger.info(f"[ASR] Transcript: '{transcript}' (Lang: {lang_code})")
            return transcript, lang_code
        except Exception as asr_err:
            logger.error(f"[ASR] Groq Whisper error: {asr_err}")
            return None, None

    def resolve_language(
        self,
        transcript: str,
        detected_lang: str | None,
        session_state: dict,
    ) -> tuple[str, bool]:
        """Applies sticky language filtering, non-Latin script protection, and explicit override checks.
        Returns (resolved_lang_code, should_discard)."""
        current_lang = session_state.get("language_code", "en-IN")
        language_locked = session_state.get("language_locked", False)
        words_count = len(transcript.split())
        has_native_script = self.contains_non_latin_script(transcript)
        is_filler = transcript.strip() in FILLER_WORDS

        resolved_lang = current_lang
        should_discard = False

        if detected_lang in SUPPORTED_LANGS:
            if is_filler:
                logger.info(f"[LANG] switch=NO reason=FILLER_DETECTED Keeping {current_lang}.")
            elif detected_lang == "en-IN" and current_lang != "en-IN" and (
                language_locked or has_native_script or words_count < 8
            ):
                reason = (
                    "LOCKED"
                    if language_locked
                    else ("NATIVE_SCRIPT_DETECTED" if has_native_script else f"TANGLISH_PROTECTION ({words_count} words)")
                )
                logger.info(f"[LANG] switch=NO reason={reason}. Keeping {current_lang}.")
            elif words_count >= 2:
                session_state["language_code"] = detected_lang
                resolved_lang = detected_lang
                logger.info(f"[LANG] switch=YES reason=SUBSTANTIAL_UTTERANCE NewLang={detected_lang}.")
            else:
                logger.info(f"[LANG] switch=NO reason=TOO_SHORT ({words_count} words). Keeping {current_lang}.")
        else:
            if words_count <= 1:
                logger.info(f"[ASR] Discarding likely noise artifact ('{transcript}', {detected_lang}).")
                return resolved_lang, True
            logger.info(f"[LANG] switch=NO reason=UNSUPPORTED_LANGUAGE ({detected_lang}). Keeping {current_lang}.")

        # Check explicit language override phrases
        lower_trans = transcript.lower()
        for code, names in NATIVE_LANG_NAMES.items():
            if any(name in lower_trans for name in names) and (
                "speak" in lower_trans
                or "talk" in lower_trans
                or "in " in lower_trans
                or "பேசு" in lower_trans
                or "பண்ணு" in lower_trans
                or "bolo" in lower_trans
                or "baat" in lower_trans
                or len(lower_trans.split()) <= 4
            ):
                session_state["language_code"] = code
                session_state["language_locked"] = True
                resolved_lang = code
                logger.info(f"[ASR] Explicit override detected for {code}: forced + LOCKED session to {code}")
                break

        return resolved_lang, should_discard
