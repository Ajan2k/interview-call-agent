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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("voice")
convo_logger = get_conversation_logger()

router = APIRouter()

SPEECH_THRESHOLD = 1000
SILENCE_THRESHOLD = 500
MIN_SPEECH_DURATION_MS = 300
SILENCE_DURATION_MS = 700
# Higher than SPEECH_THRESHOLD: line/speaker echo of the agent's own TTS tends to come
# back quieter than a caller actually talking, so barge-in needs a stricter bar to
# avoid the agent interrupting itself.
BARGE_IN_THRESHOLD = 2200

# Caller-silence handling: after this many seconds of dead air the agent asks
# "are you there?"; another timeout with no reply and it says goodbye and hangs up.
IDLE_TIMEOUT_SECS = 10
# Hard cap on total call length — the agent wraps up politely once this is reached.
MAX_CALL_DURATION_SECS = int(os.getenv("MAX_CALL_DURATION_SECS", "300"))

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

COMPANY_NAME = "Daffytel Technologies"
AGENT_NAME = "Daffy"

# Set to "outbound" when Daffy is calling the customer (lead gen)
# Set to "inbound" when the customer is calling in (support/sales inquiry)
CALL_MODE = "outbound"  # <-- change this to switch modes

def get_system_persona(lang_name: str) -> str:
    script_filename = f"{lang_name.lower()}_system_prompt.txt"
    script_path = os.path.join(os.path.dirname(__file__), "Scripts", script_filename)

    default_script = f"""You are Amira, a friendly, warm, and highly conversational AI assistant for {COMPANY_NAME}, a software company.
Your job is to help callers understand how our AI Voice Agents and AI Chatbots can automate their customer support, sales, appointment booking, and daily office work.
Rules:
- Keep replies VERY SHORT and casual (1-2 sentences for phone).
- Speak using natural everyday slang and colloquial phrasing. DO NOT use formal, robotic, or textbook translations. Speak like a friendly local!
- If asked personal questions (e.g. age), respond casually ("I'm Amira, your virtual assistant!").
- Stay on topic (software and AI automation); gently steer back if the caller goes off-topic."""
    
    if os.path.exists(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error reading script file {script_filename}: {e}")
            return default_script
    else:
        return default_script

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

async def process_utterance(utterance_bytes: bytes, session_state: dict, websocket: WebSocket):
    sarvam_key = os.getenv("SARVAM_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    if not groq_key:
        logger.error("[PIPELINE] Missing GROQ_API_KEY in environment.")
        return
        
    try:
        t_start = time.time()
        
        # 1. ASR — Groq Whisper (free, fast, excellent Indian language support)
        wav_data = create_wav_buffer(utterance_bytes)
        logger.info(f"[ASR] Sending {len(wav_data)} bytes of WAV to Groq Whisper.")
        
        # Language code mapping: Whisper short codes → BCP-47
        WHISPER_LANG_MAP = {
            "ta": "ta-IN", "hi": "hi-IN", "te": "te-IN",
            "kn": "kn-IN", "ml": "ml-IN", "en": "en-IN",
            "mr": "hi-IN",  # Marathi → treat as Hindi for now
        }
        
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
        
        if not transcript:
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

        convo_logger.info(f"CALLER ({current_lang}): {transcript}")

        # 2. LLM Provider (Groq llama-3.3-70b-versatile)
        llm_client = AsyncGroq(api_key=groq_key, max_retries=0)
        model_name = "llama-3.3-70b-versatile"
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
        }
        
        few_shot = FEW_SHOT.get(lang_name, FEW_SHOT["English"])
        
        call_mode = session_state.get("call_mode", "outbound")
        
        if call_mode == "outbound":
            system_prompt_text = (
                f"You are Daffy, a friendly salesperson from Daffytel Technologies, calling business owners to introduce"
                f" Daffytel's AI CALLING AGENT — an AI that attends incoming calls and makes outgoing calls for a business"
                f" 24/7, in Tamil, English, Hindi and more, books appointments, answers customer questions and captures leads."
                f" You sound completely human — warm, confident, natural.\n\n"
                f"PRODUCT KNOWLEDGE (know it like a real rep):\n"
                f"- AI Calling Agent attends every call day and night — no missed calls, no extra staff cost\n"
                f"- Speaks naturally in Tamil, English, Hindi and other Indian languages\n"
                f"- Books appointments/demos, answers FAQs, qualifies leads, shares details on WhatsApp\n"
                f"- Works for any business that gets calls: clinics, shops, real estate, service centres, agencies\n"
                f"- Pricing: depends on call volume and requirements — exact quote is given in the demo\n\n"
                f"ANSWERING CUSTOMER QUESTIONS (like a real human, never robotic):\n"
                f"- 'How does it work?' → 'We connect it to your business number — it attends calls and talks to customers naturally, just like a person.'\n"
                f"- 'Price?' → 'It depends on your call volume — our team will give you an exact quote in the demo.'\n"
                f"- 'Will customers know it's a machine?' → 'It talks so naturally most people can't tell — you can test it yourself in the demo!'\n"
                f"- 'Tamil support?' → 'Yes! Tamil, English, Hindi — it talks to your customers in their own language.'\n"
                f"- 'Are YOU an AI?' (only if directly asked) → proudly confirm: 'Yes! You're talking to our AI agent right now — this call itself is the live demo!'\n"
                f"- Any question you can't answer → 'Good question! Our team will cover that in the demo.'\n\n"
                f"CALL SCRIPT (follow this order, ONE step per turn, react before asking):\n"
                f"1. Confirm you have the right person, ask for 2 minutes\n"
                f"2. HOOK: ask how they handle customer calls today — do calls get missed after hours or when staff are busy?\n"
                f"3. DISCOVER: business type → daily call volume → who attends the calls → biggest pain\n"
                f"4. PITCH: connect THEIR pain to the AI calling agent in ONE line\n"
                f"5. QUALIFY: if interested, collect their name, business name and mobile number, one at a time\n"
                f"6. CLOSE: offer a FREE live demo, ask preferred day/time, confirm it back\n"
                f"7. END: thank warmly and close the call\n\n"
                f"OBJECTIONS (handle naturally):\n"
                f"- 'Already have staff for calls' → 'That's great! And after they leave in the evening, who picks up? That's exactly where our AI helps.'\n"
                f"- 'Send on WhatsApp' → 'Sure! Can I grab your number? Our team will send the details.'\n"
                f"- 'Not interested' → one gentle follow-up: 'No problem! Just curious — do you ever miss customer calls when you're busy?' If still no, close graciously.\n\n"
                f"ENDING THE CALL (every call MUST reach a clear ending):\n"
                f"- If demo confirmed: repeat the day/time back, thank warmly, close\n"
                f"- If not interested / busy / says bye: ONE short warm goodbye, close\n"
                f"- NEVER keep asking new questions after the goal (demo booked OR clearly declined) is reached\n\n"
                f"CONTROL MARKERS (silent — never speak, spell or translate them; place at the very END of the reply):\n"
                f"- [END_CALL] → append ONLY in your final goodbye reply. NEVER in a reply that asks the customer a question.\n"
                f"- [MEETING_BOOKED: Wednesday 4 PM] → ONLY after the customer states a SPECIFIC day/time; write their ACTUAL day/time. NEVER write placeholders.\n"
                f"- [LEAD: status=HOT | name=Ravi | business=textile shop | phone=98xxxxxxxx | need=missed evening calls] → append in the SAME final reply as [END_CALL], on EVERY call.\n"
                f"  status=HOT (demo booked / very interested), WARM (interested, no demo yet / callback), COLD (not interested).\n"
                f"  Fill ONLY details the customer actually said; omit unknown fields. Minimum: [LEAD: status=COLD]\n"
                f"  Example final reply: 'சரிங்க, Wednesday 4 PM க்கு demo fix! ரொம்ப நன்றி, வணக்கம்! [MEETING_BOOKED: Wednesday 4 PM] [LEAD: status=HOT | name=Ravi | business=clinic] [END_CALL]'\n\n"
                f"RULES:\n"
                f"- MAX 1-2 SHORT sentences per reply\n"
                f"- NEVER repeat a question you already asked; NEVER re-introduce yourself after the first turn\n"
                f"- Never volunteer that you're an AI (only confirm if directly asked, as above)\n"
                f"- No politics, no religion, no false claims\n\n"
                f"{few_shot}\n"
                f"CRITICAL LANGUAGE RULE: Reply ONLY in {lang_name}."
                f" If Tamil: speak natural everyday TANGLISH exactly how people talk — Tamil script for Tamil words, and keep common English words in English letters"
                f" (business, calls, demo, AI, miss, staff, time, free, book). Example: 'உங்க business ல daily எவ்வளோ calls வரும்?'"
                f" NEVER use formal/literary Tamil words like 'வணிகம்', 'அழைப்புகள்', 'மென்பொருள்' — say 'business', 'calls', 'software'. MAX 1-2 short sentences."
            )
        else:  # inbound
            system_prompt_text = (
                f"You are Daffy, a friendly sales consultant at Daffytel Technologies answering an inbound call."
                f" You sound completely human — warm, attentive, natural."
                f" Daffytel's main product is the AI CALLING AGENT — an AI that attends incoming calls and makes outgoing calls"
                f" for a business 24/7, in Tamil, English, Hindi and more, books appointments, answers customer questions and captures leads.\n\n"
                f"PRODUCT KNOWLEDGE (know it like a real rep):\n"
                f"- AI Calling Agent attends every call day and night — no missed calls, no extra staff cost\n"
                f"- Speaks naturally in Tamil, English, Hindi and other Indian languages\n"
                f"- Books appointments/demos, answers FAQs, qualifies leads, shares details on WhatsApp\n"
                f"- Works for any business that gets calls: clinics, shops, real estate, service centres, agencies\n"
                f"- Pricing: depends on call volume and requirements — exact quote is given in the demo\n\n"
                f"ANSWERING QUESTIONS (like a real human, never robotic):\n"
                f"- 'How does it work?' → 'We connect it to your business number — it attends calls and talks to customers naturally, just like a person.'\n"
                f"- 'Price?' → 'It depends on your call volume — our team will give you an exact quote in the demo.'\n"
                f"- 'Will customers know it's a machine?' → 'It talks so naturally most people can't tell — you can test it in the demo!'\n"
                f"- 'Are YOU an AI?' (only if directly asked) → proudly confirm: 'Yes! You're talking to our AI agent right now — this call itself is the live demo!'\n"
                f"- Any question you can't answer → 'Good question! Our team will cover that in the demo.'\n\n"
                f"CALL FLOW (ONE step per turn):\n"
                f"1. Greet warmly, ask how you can help\n"
                f"2. Listen, understand their need, ask short clarifying questions\n"
                f"3. Learn: business type, call volume, biggest pain with handling calls\n"
                f"4. Explain how the AI calling agent solves THEIR specific problem, in ONE line\n"
                f"5. Collect lead info one at a time: name, business name, mobile number\n"
                f"6. Offer a FREE live demo — ask preferred day/time, confirm it back\n"
                f"7. Thank warmly and close the call\n\n"
                f"OBJECTIONS:\n"
                f"- 'Just exploring' → 'Perfect timing! What made you curious about this?'\n"
                f"- 'Too expensive' → 'Totally get that — we have packages for all sizes, let me understand your setup first.'\n"
                f"- 'Want to talk to a person' → 'Of course! Can I grab your number? One of our consultants will reach out.'\n\n"
                f"ENDING THE CALL (every call MUST reach a clear ending):\n"
                f"- If demo confirmed: repeat the day/time back, thank warmly, close\n"
                f"- If their query is answered and nothing else is needed, or they say bye: ONE short warm goodbye, close\n"
                f"- NEVER keep asking new questions once their need is handled\n\n"
                f"CONTROL MARKERS (silent — never speak, spell or translate them; place at the very END of the reply):\n"
                f"- [END_CALL] → append ONLY in your final goodbye reply. NEVER in a reply that asks the caller a question.\n"
                f"- [MEETING_BOOKED: Wednesday 4 PM] → ONLY after the caller states a SPECIFIC day/time; write their ACTUAL day/time. NEVER write placeholders.\n"
                f"- [LEAD: status=HOT | name=Ravi | business=textile shop | phone=98xxxxxxxx | need=missed evening calls] → append in the SAME final reply as [END_CALL], on EVERY call.\n"
                f"  status=HOT (demo booked / very interested), WARM (interested, no demo yet / callback), COLD (not interested / wrong number).\n"
                f"  Fill ONLY details the caller actually said; omit unknown fields. Minimum: [LEAD: status=COLD]\n\n"
                f"RULES:\n"
                f"- MAX 1-2 SHORT sentences per reply\n"
                f"- NEVER repeat a question you already asked\n"
                f"- Never volunteer that you're an AI (only confirm if directly asked, as above)\n"
                f"- No politics, no religion\n\n"
                f"{few_shot}\n"
                f"CRITICAL LANGUAGE RULE: Reply ONLY in {lang_name}."
                f" If Tamil: speak natural everyday TANGLISH exactly how people talk — Tamil script for Tamil words, and keep common English words in English letters"
                f" (business, calls, demo, AI, miss, staff, time, free, book). Example: 'உங்க business ல daily எவ்வளோ calls வரும்?'"
                f" NEVER use formal/literary Tamil words like 'வணிகம்', 'அழைப்புகள்', 'மென்பொருள்' — say 'business', 'calls', 'software'. MAX 1-2 short sentences."
            )
        
        logger.info(f'[LLM PROMPT] lang={current_lang} | model={model_name}')
            
        history = session_state.get("history", [])
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": system_prompt_text})
        else:
            history[0] = {"role": "system", "content": system_prompt_text}
            
        history.append({"role": "user", "content": transcript})
        
        # Cap history to last 10 turns (plus system prompt) to avoid token bloat
        if len(history) > 11:
            history = [history[0]] + history[-10:]
            
        session_state["history"] = history
        
        logger.info(f"[LLM] Calling model {model_name}...")
        try:
            llm_res = await llm_client.chat.completions.create(
                model=model_name,
                messages=history,
                temperature=0.75,
                max_tokens=220,
                stream=True
            )
        except Exception as llm_err:
            err_str = str(llm_err)
            logger.warning(f"[LLM] Primary model '{model_name}' error: {err_str}. Retrying with {FALLBACK_MODEL} on Groq...")
            groq_client2 = AsyncGroq(api_key=groq_key, max_retries=0)
            llm_res = await groq_client2.chat.completions.create(
                model=FALLBACK_MODEL,
                messages=history,
                temperature=0.7,
                max_tokens=200,
                stream=True
            )
        
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
                
            text = chunk.choices[0].delta.content
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

        # LLM signalled the conversation is over — hang up gracefully.
        # Guard: if the reply still asks the customer a question, the LLM fired
        # END_CALL prematurely — ignore it and keep the conversation going.
        if session_state.get("pending_end_call"):
            if full_reply.rstrip().endswith(("?", "؟")):
                logger.warning("[CALL FLOW] END_CALL ignored — reply still asks a question.")
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
    await dispatch_tts(text, current_lang, session_state, websocket)

# Control markers the LLM appends to signal call state (never spoken aloud)
ENDCALL_RE = re.compile(r'\[?END[_ ]?CALL\]?')
MEETING_RE = re.compile(r'\[MEETING[_ ]?BOOKED\s*:?\s*([^\]]*)\]')
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
    lang = session_state.get("language_code", "en-IN")
    convo_logger.info(f"===== MEETING BOOKED ({lang}): {details} =====")
    try:
        meetings_path = os.path.join(os.path.dirname(__file__), "meetings.log")
        with open(meetings_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | lang={lang} | {details}\n")
    except Exception as e:
        logger.error(f"[MEETING] Failed to write meetings.log: {e}")

def log_lead(details: str, session_state: dict):
    if session_state.get("lead_logged") or not details:
        return
    session_state["lead_logged"] = True
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
        "User-Agent": "InfiniteTechAI"
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


async def dispatch_tts(text: str, lang: str, session_state: dict, websocket: WebSocket):
    # Queue up a task with its creation time to handle async barge-ins
    task_time = time.time()
    task = asyncio.create_task(azure_tts_fetch(text, lang))
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
                session_state["playback_end_time"] = max(now, current_end) + duration_sec
                
            queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[TTS WORKER] Error: {e}")

async def play_greeting(websocket: WebSocket, session_state: dict):
    call_mode = session_state.get("call_mode", "outbound")
    if call_mode == "outbound":
        # Outbound: Daffy is calling the customer — introduce and ask if they have a moment
        text = "Hello! Am I speaking with the business owner? I'm Daffy from Daffytel Technologies — I'm calling about our AI calling agent that attends your business calls 24/7, so you never miss a customer. Do you have just 2 minutes?"
    else:
        # Inbound: Customer called in — welcome them
        text = "Hello! Thanks for calling Daffytel Technologies, I'm Daffy. How can I help you today?"
    
    lang = "en-IN"
    session_state["language_code"] = lang
    
    # Pre-seed the conversation history so the LLM knows we already said this
    session_state["history"] = [{"role": "assistant", "content": text}]

    convo_logger.info(f"{AGENT_NAME.upper()} ({lang}) [greeting, mode={call_mode}]: {text}")
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
                session_state["call_start"] = time.time()
                session_state["last_activity"] = time.time()
                logger.info(f"[TELEFORCE WSS] Received 'start' (mode={mode}). Playing greeting...")
                await play_greeting(websocket, session_state)

            elif event == "media":
                # Call is being wrapped up — ignore incoming audio
                if session_state.get("ending"):
                    continue

                audio_b64 = msg["media"]["payload"]
                pcm_bytes = base64.b64decode(audio_b64)
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
        convo_logger.info("===== CALL ENDED =====")
        if playback_task:
            playback_task.cancel()
