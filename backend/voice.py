import json
import base64
import audioop
import logging
import wave
import io
import os
import time
import re
import asyncio
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from groq import AsyncGroq
from openai import AsyncOpenAI
from logging_config import get_conversation_logger
from services import database_manager as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice")
convo_logger = get_conversation_logger()

router = APIRouter()

SPEECH_THRESHOLD = 1000
SILENCE_THRESHOLD = 500
MIN_SPEECH_DURATION_MS = 300
# How long the caller must stay quiet before we treat the utterance as finished.
# Too short cuts callers off mid-question (the LLM then answers a half-question).
SILENCE_DURATION_MS = 1000
# Higher than SPEECH_THRESHOLD: line/speaker echo of the agent's own TTS tends to come
# back quieter than a caller actually talking, so barge-in needs a stricter bar to
# avoid the agent interrupting itself.
BARGE_IN_THRESHOLD = 3200

# Caller-silence handling: after this many seconds of dead air the agent asks
# "are you there?"; another timeout with no reply and it says goodbye and hangs up.
IDLE_TIMEOUT_SECS = 10
# Hard cap on total call length — the agent wraps up politely once this is reached.
MAX_CALL_DURATION_SECS = int(os.getenv("MAX_CALL_DURATION_SECS", "300"))

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_VERSION = "2024-11-13"
SARVAM_LLM_BASE_URL = "https://api.sarvam.ai/v1"
CEREBRAS_LLM_BASE_URL = "https://api.cerebras.ai/v1"
GEMINI_LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
TOGETHER_LLM_BASE_URL = "https://api.together.xyz/v1"

COMPANY_NAME = "Daffytel Technologies"
AGENT_NAME = "caffy"

# Set to "outbound" when Daffy is calling the customer (lead gen)
# Set to "inbound" when the customer is calling in (support/sales inquiry)
CALL_MODE = "outbound"  # <-- change this to switch modes

def load_script_prompt(call_mode: str, lang_name: str, few_shot: str) -> str:
    """Load the sales script for this call mode from prompts/ (or fallback Scripts/),
    filling in {lang_name} and {few_shot} placeholders."""
    filename = "outbound_prompt.txt" if call_mode == "outbound" else "inbound_prompt.txt"
    prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
    if not os.path.exists(os.path.join(prompts_dir, filename)):
        prompts_dir = os.path.join(os.path.dirname(__file__), "Scripts")
    script_path = os.path.join(prompts_dir, filename)
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception as e:
        logger.error(f"[SCRIPT] Failed to read {filename}: {e} — using minimal fallback prompt.")
        content = (
            f"You are {AGENT_NAME}, a friendly human-sounding salesperson from {COMPANY_NAME} selling an"
            " AI Calling Agent that attends business calls 24/7. Ask ONE short question at a time,"
            " book a free demo, and append [END_CALL] with a [LEAD: status=...] tag in your final goodbye reply.\n"
            "{few_shot}\nReply ONLY in {lang_name}. MAX 1-2 short sentences."
        )
    return content.replace("{lang_name}", lang_name).replace("{few_shot}", few_shot)

def create_wav_buffer(pcm_bytes: bytes, sample_rate=16000) -> bytes:
    """Wrap raw PCM bytes into a valid WAV file in-memory."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return wav_io.getvalue()

def strip_wav_header(audio_bytes: bytes, target_rate: int = 16000) -> bytes:
    """If the bytes have a RIFF WAV header, strip it and resample to target_rate using Python's wave module."""
    if not audio_bytes.startswith(b"RIFF"):
        return audio_bytes
    try:
        wav_io = io.BytesIO(audio_bytes)
        with wave.open(wav_io, 'rb') as wf:
            framerate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            nchannels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())

        if nchannels != 1:
            frames = audioop.tomono(frames, sampwidth, 0.5, 0.5)

        if framerate != target_rate:
            logger.info(f"[TTS] Resampling audio from {framerate}Hz to {target_rate}Hz")
            frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, target_rate, None)
        else:
            logger.info(f"[TTS] Parsed WAV header: Sample Rate = {framerate}Hz (matches target)")

        return frames
    except Exception as e:
        logger.error(f"[TTS] Failed to parse WAV header: {e}")
        return audio_bytes[44:] if len(audio_bytes) > 44 else audio_bytes

RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
CALLS_LOG_PATH = os.path.join(LOGS_DIR, "calls.jsonl")
MEETINGS_LOG_PATH = os.path.join(LOGS_DIR, "meetings.jsonl")
LEADS_LOG_PATH = os.path.join(LOGS_DIR, "leads.log")


class CallRecorder:
    """Records both sides of a call as 16 kHz mono PCM tracks aligned by wall clock,
    then mixes them into a single WAV. The caller's mic frames stream continuously,
    so they form the timeline; agent audio is padded to its scheduled playback time."""

    BYTES_PER_SEC = 32000  # 16000 Hz * 2 bytes

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.start_time = time.time()
        self.caller_track = bytearray()
        self.agent_track = bytearray()

    def _pad_to(self, track: bytearray, at_time: float):
        target = int((at_time - self.start_time) * self.BYTES_PER_SEC)
        target -= target % 2
        if target > len(track):
            track.extend(b"\x00" * (target - len(track)))

    def add_caller(self, pcm: bytes):
        self.caller_track.extend(pcm)

    def add_agent(self, pcm: bytes, at_time: float):
        self._pad_to(self.agent_track, at_time)
        self.agent_track.extend(pcm)

    def save(self) -> str | None:
        try:
            if not self.caller_track and not self.agent_track:
                return None
            n = max(len(self.caller_track), len(self.agent_track))
            caller = bytes(self.caller_track) + b"\x00" * (n - len(self.caller_track))
            agent = bytes(self.agent_track) + b"\x00" * (n - len(self.agent_track))
            mixed = audioop.add(caller, agent, 2)
            os.makedirs(RECORDINGS_DIR, exist_ok=True)
            filename = f"{self.call_id}.wav"
            path = os.path.join(RECORDINGS_DIR, filename)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(mixed)
            logger.info(f"[RECORDING] Saved {filename} ({len(mixed)} bytes, {len(mixed)/self.BYTES_PER_SEC:.1f}s)")
            return filename
        except Exception as e:
            logger.error(f"[RECORDING] Failed to save: {e}")
            return None


def add_transcript(session_state: dict, role: str, text: str, lang: str):
    """Append one chat turn to the per-call transcript (shown in the dashboard's
    conversation viewer). role is 'caller' or 'agent'."""
    text = (text or "").strip()
    if not text:
        return
    session_state.setdefault("transcript", []).append({
        "role": role,
        "text": text,
        "lang": lang,
        "time": time.strftime("%H:%M:%S"),
    })


async def process_utterance(utterance_bytes: bytes, session_state: dict, websocket: WebSocket):
    # Utterance captured just before the goodbye triggered call-ending — drop it,
    # otherwise the agent speaks a duplicate reply over its own goodbye.
    if session_state.get("ending"):
        logger.info("[PIPELINE] Call is ending — dropping late utterance.")
        return

    sarvam_key = os.getenv("SARVAM_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not groq_key and not sarvam_key:
        logger.error("[PIPELINE] Missing both SARVAM_API_KEY and GROQ_API_KEY in environment.")
        return

    try:
        t_start = time.time()

        wav_data = create_wav_buffer(utterance_bytes)

        # Language code mapping: Whisper short codes → BCP-47 (Groq fallback path)
        WHISPER_LANG_MAP = {
            "ta": "ta-IN", "hi": "hi-IN", "te": "te-IN",
            "kn": "kn-IN", "ml": "ml-IN", "en": "en-IN",
            "mr": "hi-IN",  # Marathi → treat as Hindi for now
        }

        transcript = None
        lang_code = None

        # 1a. ASR — Sarvam Saarika (Indic-specialised, auto language detection,
        # returns BCP-47 codes directly; far fewer misdetections than Whisper)
        if sarvam_key:
            try:
                stt_model = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
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
                else:
                    logger.error(f"[ASR] Sarvam error {res.status_code}: {res.text[:200]} — falling back to Groq Whisper.")
            except Exception as e:
                logger.error(f"[ASR] Sarvam exception: {e} — falling back to Groq Whisper.")

        # 1b. ASR fallback — Groq Whisper
        if lang_code is None:
            if not groq_key:
                await speak_fallback(websocket, session_state)
                return
            logger.info(f"[ASR] Sending {len(wav_data)} bytes of WAV to Groq Whisper.")
            try:
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
            except Exception as asr_err:
                logger.error(f"[ASR] Groq Whisper error: {asr_err}")
                await speak_fallback(websocket, session_state)
                return

        if not transcript or len(transcript.strip()) < 2:
            logger.info(f"[ASR] Discarding empty or ambient noise transcript ('{transcript}').")
            return

        current_lang = session_state.get("language_code", "en-IN")
        t_asr = time.time()
        language_locked = session_state.get("language_locked", False)
            
        # Detect if transcript contains South Indian / Hindi script characters
        # (Whisper often misidentifies Tamil/Telugu/Malayalam script as 'en-IN')
        def contains_non_latin_script(text: str) -> bool:
            for c in text:
                cp = ord(c)
                # Tamil: 0B80-0BFF | Telugu: 0C00-0C7F | Kannada: 0C80-0CFF
                # Malayalam: 0D00-0D7F | Devanagari (Hindi): 0900-097F
                if 0x0900 <= cp <= 0x0D7F:
                    return True
            return False

        has_native_script = contains_non_latin_script(transcript)
        
        # Sticky language for robust session consistency
        SUPPORTED_LANGS = {"ta-IN", "ml-IN", "te-IN", "kn-IN", "hi-IN", "en-IN"}
        FILLER_WORDS = {"जी", "हाँ जी", "ठीक है", "हुम", "हूँ", "कम", "ಹ್ಞೂ", "पोकम"}
        words_count = len(transcript.split())
        
        is_filler = transcript.strip() in FILLER_WORDS
        
        if lang_code in SUPPORTED_LANGS:
            if is_filler:
                logger.info(f"[LANG] switch=NO reason=FILLER_DETECTED Keeping {current_lang}.")
            elif lang_code == "en-IN" and current_lang != "en-IN" and (language_locked or has_native_script or words_count < 8):
                # Protect non-English session: Whisper misidentifies South Indian script as en-IN,
                # or session is locked after explicit override, or utterance is too short
                reason = "LOCKED" if language_locked else ("NATIVE_SCRIPT_DETECTED" if has_native_script else f"TANGLISH_PROTECTION ({words_count} words)")
                logger.info(f"[LANG] switch=NO reason={reason}. Keeping {current_lang}.")
            elif words_count >= 2:
                session_state["language_code"] = lang_code
                current_lang = lang_code
                logger.info(f"[LANG] switch=YES reason=SUBSTANTIAL_UTTERANCE NewLang={lang_code}.")
            else:
                logger.info(f"[LANG] switch=NO reason=TOO_SHORT ({words_count} words). Keeping {current_lang}.")
        else:
            if words_count <= 1:
                logger.info(f"[ASR] Discarding likely noise artifact ('{transcript}', {lang_code}).")
                return
            logger.info(f"[LANG] switch=NO reason=UNSUPPORTED_LANGUAGE ({lang_code}). Keeping {current_lang}.")
            
        # Explicit language override check
        LANG_MAP = {
            "en-IN": "English",
            "hi-IN": "Hindi",
            "ta-IN": "Tamil",
            "te-IN": "Telugu",
            "kn-IN": "Kannada",
            "ml-IN": "Malayalam"
        }
        
        NATIVE_LANG_NAMES = {
            "en-IN": ["english", "ஆங்கிலம்", "अंग्रेजी", "angrezi"],
            "hi-IN": ["hindi", "ஹிந்தி", "हिंदी"],
            "ta-IN": ["tamil", "தமிழ்", "தமில்", "tamizh"],
            "te-IN": ["telugu", "தெலுங்கு", "తెలుగు"],
            "kn-IN": ["kannada", "கன்னடம்", "ಕನ್ನಡ"],
            "ml-IN": ["malayalam", "மலையாளம்", "മലയാളം"]
        }
        
        lower_trans = transcript.lower()
        for code, names in NATIVE_LANG_NAMES.items():
            if any(name in lower_trans for name in names) and (
                "speak" in lower_trans or "talk" in lower_trans or "in " in lower_trans
                or "பேசு" in lower_trans or "பண்ணு" in lower_trans
                or "bolo" in lower_trans or "baat" in lower_trans
                or len(lower_trans.split()) <= 4
            ):
                session_state["language_code"] = code
                session_state["language_locked"] = True  # Lock to prevent Whisper drift
                current_lang = code
                language_locked = True
                logger.info(f"[ASR] Explicit override detected for {code}: forced + LOCKED session to {code}")
                break

        # ASR takes ~1s — the call may have started ending while we transcribed
        if session_state.get("ending"):
            logger.info("[PIPELINE] Call ended during ASR — dropping utterance.")
            return

        convo_logger.info(f"CALLER ({current_lang}): {transcript}")
        add_transcript(session_state, "caller", transcript, current_lang)

        # 2. LLM provider. Best free option (tested 2026-07): Gemini flash-lite —
        # ~1s latency, clean Tanglish, follows the control markers. Fallback chain
        # on error: Sarvam-30b → Groq 8b. Override with LLM_PROVIDER.
        together_key = os.getenv("TOGETHER_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")
        cerebras_key = os.getenv("CEREBRAS_API_KEY")
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()

        if llm_provider == "together" and together_key:
            llm_client = AsyncOpenAI(base_url=TOGETHER_LLM_BASE_URL, api_key=together_key, max_retries=0)
            model_name = os.getenv("TOGETHER_LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
            llm_max_tokens = 400
        elif llm_provider == "gemini" and gemini_key:
            llm_client = AsyncOpenAI(base_url=GEMINI_LLM_BASE_URL, api_key=gemini_key, max_retries=0)
            model_name = os.getenv("GEMINI_LLM_MODEL", "gemini-flash-lite-latest")
            llm_max_tokens = 400
        elif llm_provider == "cerebras" and cerebras_key:
            llm_client = AsyncOpenAI(base_url=CEREBRAS_LLM_BASE_URL, api_key=cerebras_key, max_retries=0)
            model_name = os.getenv("CEREBRAS_LLM_MODEL", "zai-glm-4.7")
            llm_max_tokens = 400
        elif llm_provider == "sarvam" and sarvam_key:
            llm_client = AsyncOpenAI(base_url=SARVAM_LLM_BASE_URL, api_key=sarvam_key, max_retries=0)
            model_name = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
            llm_max_tokens = 1600
        else:
            llm_client = AsyncGroq(api_key=groq_key, max_retries=0)
            model_name = os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")
            llm_max_tokens = 400
        FALLBACK_MODEL = "llama-3.1-8b-instant"
        
        lang_name = LANG_MAP.get(current_lang, "English")
        
        # Natural speaking style examples per language
        FEW_SHOT = {
            "Tamil": (
                "Daffy's natural spoken TANGLISH style (Tamil script + everyday English words, exactly how people actually talk on the phone):\n"
                "- சரிங்க! உங்க business ல daily எவ்வளோ calls வரும்?\n"
                "- ஓ அப்படியா! Night ல வர்ற calls எல்லாம் miss ஆகுதா? எங்க AI agent 24/7 எல்லா calls யும் attend பண்ணிடும்.\n"
                "- Super! உங்களுக்கு ஒரு free demo arrange பண்ணிடுறேன் — எந்த day, என்ன time convenient ஆ இருக்கும்?\n"
            ),
            "Hindi": (
                "Daffy's natural Hinglish style — short, warm, colloquial:\n"
                "- Bilkul samajh gaya! Din mein roughly kitne calls aate hain?\n"
                "- Raat ke calls miss ho jaate hain? Hamara AI agent 24/7 saare calls attend karta hai.\n"
            ),
            "English": (
                "Daffy's natural English style — warm, casual, NOT robotic:\n"
                "- Oh gotcha! And roughly how many calls do you get in a day?\n"
                "- Got it — so after-hours calls just go unanswered? Our AI agent attends every single call, 24/7.\n"
            ),
            "Telugu": (
                "Daffy's natural spoken Telugu style (Telugu script + everyday English words, exactly how people talk):\n"
                "- సరే sir! మీ business కి daily ఎన్ని calls వస్తాయి?\n"
                "- ఓ అలాగా! Night లో వచ్చే calls అన్నీ miss అవుతున్నాయా? మా AI agent 24/7 అన్ని calls attend చేస్తుంది.\n"
            ),
            "Kannada": (
                "Daffy's natural spoken Kannada style (Kannada script + everyday English words, exactly how people talk):\n"
                "- ಸರಿ sir! ನಿಮ್ಮ business ಗೆ daily ಎಷ್ಟು calls ಬರುತ್ತವೆ?\n"
                "- ಓ ಹೌದಾ! Night ಲಿ ಬರುವ calls ಎಲ್ಲಾ miss ಆಗ್ತಿವೆಯಾ? ನಮ್ಮ AI agent 24/7 ಎಲ್ಲಾ calls attend ಮಾಡುತ್ತೆ.\n"
            ),
            "Malayalam": (
                "Daffy's natural spoken Malayalam style (Malayalam script + everyday English words, exactly how people talk):\n"
                "- ശരി sir! നിങ്ങളുടെ business ൽ daily എത്ര calls വരും?\n"
                "- ഓ അങ്ങനെയാണോ! Night ൽ വരുന്ന calls എല്ലാം miss ആകുന്നുണ്ടോ? ഞങ്ങളുടെ AI agent 24/7 എല്ലാ calls ഉം attend ചെയ്യും.\n"
            ),
        }
        
        few_shot = FEW_SHOT.get(lang_name, FEW_SHOT["English"])
        
        call_mode = session_state.get("call_mode", "outbound")
        
        # System prompt lives in Scripts/outbound_prompt.txt / Scripts/inbound_prompt.txt
        system_prompt_text = load_script_prompt(call_mode, lang_name, few_shot)
        
        logger.info(f'[LLM PROMPT] lang={current_lang} | model={model_name}')
            
        history = session_state.get("history", [])
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": system_prompt_text})
        else:
            history[0] = {"role": "system", "content": system_prompt_text}
            
        history.append({"role": "user", "content": transcript})
        
        # Cap history to last 6 turns (plus system prompt). Keeping this small matters:
        # Groq free tier allows only 6000 tokens/min on the 70B model, and every extra
        # turn of history pushes each request closer to that ceiling (429 → fallback).
        if len(history) > 7:
            history = [history[0]] + history[-6:]
            
        session_state["history"] = history
        
        logger.info(f"[LLM] Calling model {model_name}...")
        try:
            llm_res = await llm_client.chat.completions.create(
                model=model_name,
                messages=history,
                temperature=0.75,
                max_tokens=llm_max_tokens,
                stream=True
            )
        except Exception as llm_err:
            err_str = str(llm_err)
            # Prefer Sarvam as fallback: slower (reasoning model) but coherent and
            # follows the script. Groq's 8b-instant produces garbage Tamil and
            # hallucinates markers — keep it only as the last resort.
            if sarvam_key and llm_provider != "sarvam":
                model_name = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
                logger.warning(f"[LLM] Primary model error: {err_str}. Falling back to Sarvam {model_name}...")
                sarvam_client = AsyncOpenAI(base_url=SARVAM_LLM_BASE_URL, api_key=sarvam_key, max_retries=0)
                llm_res = await sarvam_client.chat.completions.create(
                    model=model_name,
                    messages=history,
                    temperature=0.7,
                    max_tokens=1600,
                    stream=True
                )
            else:
                logger.warning(f"[LLM] Primary model '{model_name}' error: {err_str}. Retrying with {FALLBACK_MODEL} on Groq...")
                groq_client2 = AsyncGroq(api_key=groq_key, max_retries=0)
                llm_res = await groq_client2.chat.completions.create(
                    model=FALLBACK_MODEL,
                    messages=history,
                    temperature=0.7,
                    max_tokens=400,
                    stream=True
                )
                model_name = FALLBACK_MODEL  # so the transcript log shows the model that actually replied
        
        # 3. Streaming and sentence splitting
        sentences = []
        current_sentence = ""
        raw_reply = ""
        in_thinking_block = False

        t_llm_first = None

        async for chunk in llm_res:
            if session_state.get("barge_in"):
                logger.info("[LLM] Barge-in detected, saving emitted sentences to history & cancelling LLM stream.")
                if sentences:
                    history.append({"role": "assistant", "content": " ".join(sentences)})
                return
                
            # Defensive check to handle empty usage/metadata chunks safely
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            delta = getattr(chunk.choices[0], "delta", None)
            if not delta:
                continue
            text = getattr(delta, "content", None) or ""
            if not text:
                continue
            
            # --- Filter <think> blocks (Qwen thinking mode) ---
            if "<think>" in text:
                in_thinking_block = True
            if in_thinking_block:
                if "</think>" in text:
                    in_thinking_block = False
                    text = text[text.find("</think>") + len("</think>"):]
                else:
                    continue  # skip all thinking content
            
            # Strip markdown bold (**text**) that Gemini sometimes outputs
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
            text = re.sub(r'\*(.*?)\*', r'\1', text)
            
            if not text.strip():
                continue
            
            if t_llm_first is None:
                t_llm_first = time.time()

            raw_reply += text
            current_sentence += text
            
            # Split at sentence-ending or comma punctuation for fast time-to-first-audio
            parts = re.split(r'([.!?।,]+\s+)', current_sentence)
            if len(parts) > 1:
                idx = 0
                while idx < len(parts) - 1:
                    sentence = (parts[idx] + parts[idx+1]).strip()
                    # Strip meta-instructions like (Wait), (Wait for response.) from TTS
                    sentence = re.sub(r'\(.*?\)', '', sentence).strip()
                    # Strip [END_CALL] / [MEETING_BOOKED: ...] control markers
                    sentence = extract_control_markers(sentence, session_state)
                    # Skip if it looks like the model is narrating the script to itself
                    if any(skip in sentence for skip in ["Step 1", "Step 2", "Step 3", "Call Flow", "OUTBOUND", "INBOUND"]):
                        logger.warning(f"[LLM] Skipping script narration: {sentence[:60]}")
                        idx += 2
                        continue
                    if sentence:
                        sentences.append(sentence)
                        logger.info(f"[LLM] Sentence emitted: {sentence}")
                        await dispatch_tts(sentence, current_lang, session_state, websocket)
                    idx += 2
                current_sentence = parts[-1].lstrip()
            
        # Flush remaining text
        if current_sentence.strip():
            cleaned = re.sub(r'\(.*?\)', '', current_sentence).strip()
            cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
            cleaned = extract_control_markers(cleaned, session_state)
            if cleaned and not any(skip in cleaned for skip in ["Step 1", "Step 2", "Step 3", "Call Flow", "OUTBOUND", "INBOUND"]):
                sentences.append(cleaned)
                logger.info(f"[LLM] Sentence emitted: {cleaned}")
                await dispatch_tts(cleaned, current_lang, session_state, websocket)

        # Catch markers that were split across sentence boundaries (detection only)
        extract_control_markers(raw_reply, session_state)

        full_reply = " ".join(sentences)
        history.append({"role": "assistant", "content": full_reply})
        t_llm_done = time.time()

        llm_latency = int((t_llm_first - t_asr)*1000) if t_llm_first else int((t_llm_done - t_asr)*1000)
        logger.info(f"[LATENCY] ASR: {int((t_asr - t_start)*1000)}ms | LLM first chunk: {llm_latency}ms")
        convo_logger.info(f"{AGENT_NAME.upper()} ({current_lang}) [model={model_name}, latency={llm_latency}ms]: {full_reply}")
        add_transcript(session_state, "agent", full_reply, current_lang)

        # LLM signalled the conversation is over — hang up gracefully.
        # Guard: if the reply still asks the customer a question or solicits information,
        # the LLM fired END_CALL prematurely — ignore it and keep the conversation going.
        if session_state.get("pending_end_call"):
            lower_reply = full_reply.lower()
            soliciting_info = any(kw in lower_reply for kw in [
                "number", "mobile", "phone", "email", "time", "date", "demo", "schedule", "when", "contact",
                "details", "repeat", "pardon", "again", "convenient", "tell me", "share"
            ])
            is_question = full_reply.rstrip().endswith(("?", "؟")) or "?" in full_reply
            
            if is_question or soliciting_info:
                logger.warning(f"[CALL FLOW] Premature END_CALL ignored — reply is still continuing conversation: '{full_reply[:60]}...'")
                session_state["pending_end_call"] = False
            else:
                await finalize_call(websocket, session_state)

    except Exception as e:
        logger.error(f"[PIPELINE] Exception: {e}", exc_info=True)
        convo_logger.info(f"{AGENT_NAME.upper()} [PIPELINE ERROR]: {e}")
        await speak_fallback(websocket, session_state)

async def speak_fallback(websocket: WebSocket, session_state: dict):
    logger.info("[FALLBACK] Triggered fallback audio.")
    current_lang = session_state.get("language_code", "en-IN")
    
    FALLBACK_MSGS = {
        "en-IN": "Sorry, I didn't quite catch that. Could you repeat?",
        "ta-IN": "மன்னிக்கவும், எனக்கு சரியா கேக்கல. இன்னொரு தடவை சொல்ல முடியுமா?",
        "hi-IN": "क्षमा करें, मुझे समझ नहीं आया। क्या आप दोहरा सकते हैं?",
        "te-IN": "క్షమించండి, నాకు అర్థం కాలేదు. దయచేసి మళ్లీ చెప్పగలరా?",
        "kn-IN": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
        "ml-IN": "ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?"
    }
    
    text = FALLBACK_MSGS.get(current_lang, FALLBACK_MSGS["en-IN"])
    convo_logger.info(f"{AGENT_NAME.upper()} ({current_lang}) [fallback]: {text}")
    add_transcript(session_state, "agent", text, current_lang)
    await dispatch_tts(text, current_lang, session_state, websocket)

# Control markers the LLM appends to signal call state (never spoken aloud)
ENDCALL_RE = re.compile(r'\[?END[_ ]?CALL\]?')
MEETING_RE = re.compile(r'\[MEETING[_ ]?BOOKED\s*:?\s*([^\]]*)\]')
CALLBACK_RE = re.compile(r'\[CALLBACK\s*:?\s*([^\]]*)\]')
LEAD_RE = re.compile(r'\[LEAD\s*:?\s*([^\]]*)\]')

IDLE_NUDGE_MSGS = {
    "en-IN": "Hello, are you still there?",
    "ta-IN": "ஹலோ, லைன்ல இருக்கீங்களா?",
    "hi-IN": "हेलो, क्या आप सुन रहे हैं?",
    "te-IN": "హలో, వింటున్నారా?",
    "kn-IN": "ಹಲೋ, ಕೇಳಿಸ್ತಿದೆಯಾ?",
    "ml-IN": "ഹലോ, കേൾക്കുന്നുണ്ടോ?",
}

IDLE_GOODBYE_MSGS = {
    "en-IN": "Seems like this isn't a good time. I'll call back later. Thank you, bye!",
    "ta-IN": "நீங்க பிசியா இருக்கீங்க போல. நான் அப்புறமா கால் பண்றேன். நன்றி, வணக்கம்!",
    "hi-IN": "लगता है आप अभी व्यस्त हैं। मैं बाद में कॉल करती हूँ। धन्यवाद, नमस्ते!",
    "te-IN": "మీరు బిజీగా ఉన్నట్టున్నారు. నేను తర్వాత కాల్ చేస్తాను. ధన్యవాదాలు!",
    "kn-IN": "ನೀವು ಬ್ಯುಸಿ ಇದ್ದೀರಾ ಅನ್ಸುತ್ತೆ. ನಾನು ಆಮೇಲೆ ಕಾಲ್ ಮಾಡ್ತೀನಿ. ಧನ್ಯವಾದಗಳು!",
    "ml-IN": "നിങ്ങൾ തിരക്കിലാണെന്ന് തോന്നുന്നു. ഞാൻ പിന്നീട് വിളിക്കാം. നന്ദി!",
}

TIMEUP_GOODBYE_MSGS = {
    "en-IN": "I don't want to take more of your time. Our team will follow up with the details. Thanks a lot, bye!",
    "ta-IN": "உங்க நேரத்தை அதிகமா எடுத்துக்க விரும்பல. மீதி விவரங்களை எங்க டீம் ஷேர் பண்ணும். ரொம்ப நன்றி, வணக்கம்!",
    "hi-IN": "मैं आपका ज़्यादा समय नहीं लेना चाहती। बाकी जानकारी हमारी टीम भेज देगी। धन्यवाद, नमस्ते!",
    "te-IN": "మీ సమయం ఎక్కువ తీసుకోవడం ఇష్టం లేదు. మిగతా వివరాలు మా టీమ్ పంపుతుంది. ధన్యవాదాలు!",
    "kn-IN": "ನಿಮ್ಮ ಹೆಚ್ಚು ಸಮಯ ತೆಗೆದುಕೊಳ್ಳಲು ಇಷ್ಟವಿಲ್ಲ. ಉಳಿದ ವಿವರಗಳನ್ನು ನಮ್ಮ ತಂಡ ಕಳುಹಿಸುತ್ತದೆ. ಧನ್ಯವಾದಗಳು!",
    "ml-IN": "നിങ്ങളുടെ കൂടുതൽ സമയം എടുക്കാൻ ആഗ്രഹിക്കുന്നില്ല. ബാക്കി വിവരങ്ങൾ ഞങ്ങളുടെ ടീം അയയ്ക്കും. നന്ദി!",
}

def log_meeting(details: str, session_state: dict):
    if session_state.get("meeting_logged"):
        return
    session_state["meeting_logged"] = True
    session_state["meeting_details"] = details
    lang = session_state.get("language_code", "en-IN")
    mode = session_state.get("call_mode", "outbound")
    convo_logger.info(f"===== MEETING BOOKED ({lang}): {details} =====")
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "call_id": session_state.get("call_id", ""),
        "direction": "incoming" if mode == "inbound" else "outgoing",
        "phone": session_state.get("phone", ""),
        "language": lang,
        "details": details,
    }
    if not db.db_save_meeting(record):
        # PostgreSQL unavailable — fall back to the JSONL file
        try:
            os.makedirs(os.path.dirname(MEETINGS_LOG_PATH), exist_ok=True)
            with open(MEETINGS_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[MEETING] Failed to write meetings.jsonl: {e}")

def log_callback(details: str, session_state: dict):
    if session_state.get("callback_logged") or not details:
        return
    session_state["callback_logged"] = True
    session_state["callback_details"] = details
    lang = session_state.get("language_code", "en-IN")
    mode = session_state.get("call_mode", "outbound")
    convo_logger.info(f"===== CALLBACK REQUESTED ({lang}): {details} =====")
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "call_id": session_state.get("call_id", ""),
        "direction": "incoming" if mode == "inbound" else "outgoing",
        "phone": session_state.get("phone", ""),
        "language": lang,
        "callback_time": details,
    }
    if not db.db_save_callback(record):
        try:
            path = os.path.join(os.path.dirname(__file__), "logs", "callbacks.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[CALLBACK] Failed to write callbacks.jsonl: {e}")


def log_lead(details: str, session_state: dict):
    if session_state.get("lead_logged") or not details:
        return
    session_state["lead_logged"] = True
    session_state["lead_details"] = details
    lang = session_state.get("language_code", "en-IN")
    mode = session_state.get("call_mode", "outbound")
    convo_logger.info(f"===== LEAD ({mode}, {lang}): {details} =====")
    try:
        leads_path = os.path.join(os.path.dirname(__file__), "leads.log")
        with open(leads_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | mode={mode} | lang={lang} | {details}\n")
    except Exception as e:
        logger.error(f"[LEAD] Failed to write leads.log: {e}")

def extract_control_markers(text: str, session_state: dict) -> str:
    """Strip [END_CALL] / [MEETING_BOOKED: ...] / [LEAD: ...] markers from LLM text
    before TTS, recording their effects on the session."""
    m = MEETING_RE.search(text)
    if m:
        details = m.group(1).strip()
        # Ignore hallucinated placeholders like "<day and time>" — only log real bookings
        if details and '<' not in details and 'day and time' not in details.lower():
            log_meeting(details, session_state)
        text = MEETING_RE.sub('', text)
    cb = CALLBACK_RE.search(text)
    if cb:
        cb_details = cb.group(1).strip()
        if cb_details and '<' not in cb_details:
            log_callback(cb_details, session_state)
        text = CALLBACK_RE.sub('', text)
    lm = LEAD_RE.search(text)
    if lm:
        log_lead(lm.group(1).strip(), session_state)
        text = LEAD_RE.sub('', text)
    if ENDCALL_RE.search(text):
        session_state["pending_end_call"] = True
        logger.info("[CALL FLOW] LLM signalled END_CALL.")
        text = ENDCALL_RE.sub('', text)
    # Drop an unterminated trailing marker fragment like "[MEETING_BOOKED: Mon"
    text = re.sub(r'\[[A-Z_][^\]]*$', '', text)
    return text.strip()

async def finalize_call(websocket: WebSocket, session_state: dict, goodbye_text: str = None):
    """Speak an optional goodbye, wait for playback to finish, then tell the
    frontend to hang up the SIP call and close the websocket."""
    if session_state.get("ending"):
        return
    session_state["ending"] = True
    if goodbye_text:
        lang = session_state.get("language_code", "en-IN")
        convo_logger.info(f"{AGENT_NAME.upper()} ({lang}) [closing]: {goodbye_text}")
        add_transcript(session_state, "agent", goodbye_text, lang)
        await dispatch_tts(goodbye_text, lang, session_state, websocket)
    try:
        await asyncio.wait_for(session_state["tts_queue"].join(), timeout=20)
    except asyncio.TimeoutError:
        logger.warning("[CALL FLOW] TTS queue drain timed out while ending call.")
    remaining = session_state.get("playback_end_time", 0) - time.time() + 1.0
    if remaining > 0:
        await asyncio.sleep(min(remaining, 30))
    convo_logger.info("===== AGENT ENDED CALL =====")
    try:
        await websocket.send_json({"event": "end_call"})
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass

async def azure_tts_fetch(text: str, lang: str) -> bytes:
    """Fetch audio from Microsoft Azure Neural TTS. Sounds significantly more human than Sarvam."""
    azure_key = os.getenv("AZURE_SPEECH_KEY")
    azure_region = os.getenv("AZURE_SPEECH_REGION", "centralindia")
    if not azure_key:
        return b""
    
    # Map language codes to Azure Neural voice names
    AZURE_VOICES = {
        "en-IN": "en-IN-NeerjaNeural",
        "ta-IN": "ta-IN-PallaviNeural",
        "hi-IN": "hi-IN-SwaraNeural",
        "te-IN": "te-IN-ShrutiNeural",
        "kn-IN": "kn-IN-SapnaNeural",
        "ml-IN": "ml-IN-SobhanaNeural",
    }
    voice = AZURE_VOICES.get(lang, "en-IN-NeerjaNeural")
    
    ssml = f"""<speak version='1.0' xml:lang='{lang}'>
        <voice name='{voice}'>
            <prosody rate='-2%' pitch='+1%'>{text}</prosody>
        </voice>
    </speak>"""
    
    url = f"https://{azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": azure_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
        "User-Agent": "DaffytelAI"
    }
    
    try:
        t0 = time.time()
        async with httpx.AsyncClient() as client:
            res = await client.post(url, content=ssml.encode("utf-8"), headers=headers, timeout=15.0)
            if res.status_code != 200:
                logger.error(f"[AZURE TTS] Error {res.status_code}: {res.text[:200]}")
                return b""
            # Azure returns RIFF WAV — strip the 44-byte header to get raw PCM
            audio_bytes = strip_wav_header(res.content)
            logger.info(f"[AZURE TTS] Fetched '{text[:40]}' via {voice} in {int((time.time()-t0)*1000)}ms. Raw: {len(audio_bytes)} bytes.")
            return audio_bytes
    except Exception as e:
        logger.error(f"[AZURE TTS] Exception: {e}")
        return b""


async def cartesia_tts_fetch(text: str, lang: str) -> bytes:
    """Fetch audio from Cartesia Sonic 3.5 TTS. Uses the Tamil 'Kavitha' voice for the
    agent. Requests raw 16kHz mono PCM so it drops straight into the playback pipeline
    with no header stripping needed."""
    cartesia_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_key:
        return b""

    # Per-language voice ids (Cartesia voice ids are UUIDs). Kavitha is the Tamil voice.
    CARTESIA_VOICES = {
        "ta-IN": os.getenv("CARTESIA_VOICE_TA", os.getenv("CARTESIA_KAVITHA_VOICE_ID", "")),
        "en-IN": os.getenv("CARTESIA_VOICE_EN", ""),
        "hi-IN": os.getenv("CARTESIA_VOICE_HI", ""),
    }
    # Default the agent's voice to Kavitha (Tamil) when a language-specific id isn't set.
    voice_id = CARTESIA_VOICES.get(lang) or os.getenv("CARTESIA_KAVITHA_VOICE_ID", "")
    if not voice_id:
        return b""

    # Cartesia language codes are ISO-639-1 (e.g. "ta"), not the "ta-IN" locale form.
    cartesia_lang = (lang or "en-IN").split("-")[0]

    payload = {
        "model_id": os.getenv("CARTESIA_MODEL_ID", "sonic-2"),
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
            # container=raw returns bare PCM — no WAV header to strip.
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


async def sarvam_tts_fetch(text: str, lang: str) -> bytes:
    """Fetch audio from Sarvam Bulbul TTS — Indic-specialised, handles Tanglish
    (Tamil script mixed with English words) naturally."""
    sarvam_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_key:
        return b""

    SUPPORTED = {"en-IN", "ta-IN", "hi-IN", "te-IN", "kn-IN", "ml-IN"}
    payload = {
        "text": text,
        "target_language_code": lang if lang in SUPPORTED else "en-IN",
        "speaker": os.getenv("SARVAM_TTS_SPEAKER", "anushka"),
        "model": "bulbul:v2",
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "pace": 0.93
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
            audio_bytes = strip_wav_header(base64.b64decode(audios[0]))
            logger.info(f"[SARVAM TTS] Fetched '{text[:40]}' via bulbul:v2 in {int((time.time()-t0)*1000)}ms. Raw: {len(audio_bytes)} bytes.")
            return audio_bytes
    except Exception as e:
        logger.error(f"[SARVAM TTS] Exception: {e}")
        return b""


async def tts_fetch(text: str, lang: str) -> bytes:
    """Primary: Cartesia Sonic 3.5 with the Tamil 'Kavitha' voice (when CARTESIA_API_KEY
    is set). Fallbacks: Sarvam Bulbul → Azure Neural."""
    audio = await cartesia_tts_fetch(text, lang)
    if audio:
        return audio
    if os.getenv("CARTESIA_API_KEY") and (os.getenv("CARTESIA_KAVITHA_VOICE_ID") or os.getenv("CARTESIA_VOICE_TA") or os.getenv("CARTESIA_VOICE_EN")):
        logger.warning("[TTS] Cartesia failed — falling back to Sarvam.")

    audio = await sarvam_tts_fetch(text, lang)
    if audio:
        return audio
    if os.getenv("SARVAM_API_KEY"):
        logger.warning("[TTS] Sarvam failed — falling back to Azure.")
    return await azure_tts_fetch(text, lang)


async def dispatch_tts(text: str, lang: str, session_state: dict, websocket: WebSocket):
    # Queue up a task with its creation time to handle async barge-ins
    task_time = time.time()
    task = asyncio.create_task(tts_fetch(text, lang))
    await session_state["tts_queue"].put((task_time, task))

async def tts_playback_worker(session_state: dict, websocket: WebSocket):
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
                # Send immediately to frontend
                await websocket.send_json({
                    "event": "media",
                    "media": {"payload": base64.b64encode(audio_bytes).decode('utf-8')}
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

async def play_greeting(websocket: WebSocket, session_state: dict):
    call_mode = session_state.get("call_mode", "outbound")
    if call_mode == "outbound":
        # Outbound: introduce FIRST, then ask who we're speaking with
        text = "Hello! I'm Daffy, calling from Daffytel Technologies. We help businesses attend every customer call 24/7 with our AI calling agent. May I know who I'm speaking with?"
    else:
        # Inbound: Customer called in — welcome them
        text = "Hello! Thanks for calling Daffytel Technologies, I'm Daffy. How can I help you today?"
    
    lang = "en-IN"
    session_state["language_code"] = lang
    
    # Pre-seed the conversation history so the LLM knows we already said this
    session_state["history"] = [{"role": "assistant", "content": text}]

    convo_logger.info(f"{AGENT_NAME.upper()} ({lang}) [greeting, mode={call_mode}]: {text}")
    add_transcript(session_state, "agent", text, lang)
    await dispatch_tts(text, lang, session_state, websocket)

@router.websocket("/api/voice/teleforce_stream")
async def teleforce_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("[TELEFORCE WSS] Connection established")

    session_state = {
        "language_code": "en-IN",
        "history": [],
        "tts_queue": asyncio.Queue(),
        "playback_end_time": 0,
        "barge_in": False,
        "call_mode": "outbound",
        "call_start": time.time(),
        "last_activity": time.time(),
        "idle_nudges": 0,
        "pending_end_call": False,
        "ending": False,
        "transcript": [],
    }
    
    playback_task = asyncio.create_task(tts_playback_worker(session_state, websocket))
    pipeline_task = None
    
    audio_buffer = bytearray()
    
    # 16000 hz * 2 bytes = 32000 bytes / sec.
    SILENCE_BYTES = int(32000 * (SILENCE_DURATION_MS / 1000.0))
    MIN_SPEECH_BYTES = int(32000 * (MIN_SPEECH_DURATION_MS / 1000.0))
    
    current_silence_bytes = 0
    is_speaking = False
    
    try:
        while True:
            msg_str = await websocket.receive_text()
            msg = json.loads(msg_str)
            event = msg.get("event")
            
            if event == "start":
                mode = msg.get("callMode") or msg.get("mode") or "outbound"
                session_state["call_mode"] = mode
                session_state["phone"] = (msg.get("phone") or "").strip()
                session_state["call_start"] = time.time()
                session_state["last_activity"] = time.time()
                call_id = time.strftime("%Y%m%d_%H%M%S") + ("_incoming" if mode == "inbound" else "_outgoing")
                session_state["call_id"] = call_id
                session_state["recorder"] = CallRecorder(call_id)
                logger.info(f"[TELEFORCE WSS] Received 'start' (mode={mode}, id={call_id}). Playing greeting...")
                await play_greeting(websocket, session_state)

            elif event == "media":
                audio_b64 = msg["media"]["payload"]
                pcm_bytes = base64.b64decode(audio_b64)

                recorder = session_state.get("recorder")
                if recorder:
                    recorder.add_caller(pcm_bytes)

                # Call is being wrapped up — record but don't process further
                if session_state.get("ending"):
                    continue

                rms = audioop.rms(pcm_bytes, 2)

                now = time.time()

                # Hard cap on call length — wrap up politely
                if now - session_state.get("call_start", now) > MAX_CALL_DURATION_SECS:
                    logger.info(f"[CALL FLOW] Max call duration ({MAX_CALL_DURATION_SECS}s) reached. Wrapping up.")
                    lang = session_state.get("language_code", "en-IN")
                    goodbye = TIMEUP_GOODBYE_MSGS.get(lang, TIMEUP_GOODBYE_MSGS["en-IN"])
                    asyncio.create_task(finalize_call(websocket, session_state, goodbye))
                    continue

                # Check if agent is currently speaking on the frontend
                agent_speaking = now < session_state.get("playback_end_time", 0)

                if agent_speaking:
                    if rms > BARGE_IN_THRESHOLD:
                        logger.info(f"[BARGE-IN] Detected! RMS: {rms}")
                        session_state["cancel_tts_before"] = time.time()
                        session_state["playback_end_time"] = 0  # Stop agent speaking state
                        
                        if pipeline_task and not pipeline_task.done():
                            pipeline_task.cancel()
                            
                        await websocket.send_json({"event": "clear"})
                        
                        # Empty TTS queue
                        while not session_state["tts_queue"].empty():
                            try:
                                session_state["tts_queue"].get_nowait()
                                session_state["tts_queue"].task_done()
                            except:
                                pass
                        
                        # Reset VAD to capture the interruption
                        audio_buffer = bytearray()
                        is_speaking = True
                        current_silence_bytes = 0
                        audio_buffer.extend(pcm_bytes)
                    continue # Ignore normal VAD buffering while agent speaks
                
                # Normal VAD logic (agent not speaking)
                if rms > SPEECH_THRESHOLD:
                    if not is_speaking:
                        is_speaking = True
                        session_state["idle_nudges"] = 0
                        logger.info(f"[VAD] Speech started. RMS: {rms}")
                    session_state["last_activity"] = now
                    audio_buffer.extend(pcm_bytes)
                    current_silence_bytes = 0
                else:
                    if is_speaking:
                        audio_buffer.extend(pcm_bytes)
                        current_silence_bytes += len(pcm_bytes)

                        if current_silence_bytes >= SILENCE_BYTES:
                            # Speech ended
                            is_speaking = False
                            session_state["last_activity"] = now
                            logger.info(f"[VAD] Speech ended after {len(audio_buffer)} bytes.")

                            # Check minimum duration
                            if len(audio_buffer) >= MIN_SPEECH_BYTES:
                                utterance = bytes(audio_buffer)
                                session_state["barge_in"] = False
                                # A newer utterance supersedes a reply still being
                                # generated — otherwise rapid utterances spawn
                                # parallel replies that speak over each other.
                                if pipeline_task and not pipeline_task.done():
                                    logger.info("[VAD] New utterance while previous reply in flight — superseding it.")
                                    pipeline_task.cancel()
                                    session_state["cancel_tts_before"] = time.time()
                                pipeline_task = asyncio.create_task(process_utterance(utterance, session_state, websocket))
                            else:
                                logger.info(f"[VAD] Utterance too short, discarding.")

                            audio_buffer = bytearray()
                            current_silence_bytes = 0
                    else:
                        # Dead air: agent finished speaking and caller says nothing.
                        # Skip while an utterance is still being processed (LLM/TTS in flight).
                        if pipeline_task and not pipeline_task.done():
                            session_state["last_activity"] = now
                        else:
                            idle_base = max(session_state.get("last_activity", now),
                                            session_state.get("playback_end_time", 0))
                            if now - idle_base > IDLE_TIMEOUT_SECS:
                                lang = session_state.get("language_code", "en-IN")
                                if session_state.get("idle_nudges", 0) == 0:
                                    session_state["idle_nudges"] = 1
                                    session_state["last_activity"] = now
                                    nudge = IDLE_NUDGE_MSGS.get(lang, IDLE_NUDGE_MSGS["en-IN"])
                                    logger.info(f"[CALL FLOW] Caller silent for {IDLE_TIMEOUT_SECS}s — nudging.")
                                    convo_logger.info(f"{AGENT_NAME.upper()} ({lang}) [silence nudge]: {nudge}")
                                    add_transcript(session_state, "agent", nudge, lang)
                                    await dispatch_tts(nudge, lang, session_state, websocket)
                                else:
                                    goodbye = IDLE_GOODBYE_MSGS.get(lang, IDLE_GOODBYE_MSGS["en-IN"])
                                    logger.info("[CALL FLOW] Caller still silent after nudge — ending call.")
                                    asyncio.create_task(finalize_call(websocket, session_state, goodbye))
                            
            elif event == "stop":
                logger.info("[TELEFORCE WSS] Call stopped")
                break
                
    except WebSocketDisconnect:
        logger.info("[TELEFORCE WSS] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[TELEFORCE WSS] Error: {e}", exc_info=True)
        convo_logger.info(f"===== CALL ERROR: {e} =====")
    finally:
        # Every call leaves exactly one line in leads.log — if the LLM never
        # emitted a [LEAD: ...] marker (silent caller, dropped call), record that too.
        if not session_state.get("lead_logged"):
            log_lead("status=INCOMPLETE | call ended without lead capture", session_state)

        # Save the call recording and append the call-history record
        recording_file = None
        recorder = session_state.get("recorder")
        if recorder:
            recording_file = recorder.save()
        if session_state.get("call_id"):
            try:
                end_time = time.time()
                start_time = session_state.get("call_start", end_time)
                record = {
                    "id": session_state["call_id"],
                    "direction": "incoming" if session_state.get("call_mode") == "inbound" else "outgoing",
                    "phone": session_state.get("phone", ""),
                    "start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
                    "end": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time)),
                    "duration_sec": int(end_time - start_time),
                    "language": session_state.get("language_code", "en-IN"),
                    "lead": session_state.get("lead_details", ""),
                    "meeting": session_state.get("meeting_details", ""),
                    "callback": session_state.get("callback_details", ""),
                    "ended_by": "agent" if session_state.get("ending") else "caller",
                    "recording": recording_file,
                    "transcript": session_state.get("transcript", []),
                }
                if not db.db_save_call(record):
                    # PostgreSQL unavailable — fall back to the JSONL file
                    os.makedirs(os.path.dirname(CALLS_LOG_PATH), exist_ok=True)
                    with open(CALLS_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"[CALL HISTORY] Failed to save call record: {e}")

        convo_logger.info("===== CALL ENDED =====")
        if playback_task:
            playback_task.cancel()
