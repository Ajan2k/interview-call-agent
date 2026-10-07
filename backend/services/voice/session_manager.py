import os
import re
import json
import time
import base64
import asyncio
import audioop
import logging
from fastapi import WebSocket, WebSocketDisconnect
from core.logging import get_conversation_logger
from core.config import settings
from services import database_manager as db
from services.voice.audio import AudioProcessor, CallRecorder
from services.voice.markers import MarkerService
from services.voice.prompts import PromptManager, LANG_MAP
from services.voice.tts import TTSService
from services.voice.stt import STTService
from services.voice.llm import LLMService
from services.candidate_repository import candidate_repo

logger = logging.getLogger("voice.session")
convo_logger = get_conversation_logger()

SPEECH_THRESHOLD = 1000
SILENCE_THRESHOLD = 500
MIN_SPEECH_DURATION_MS = 300
SILENCE_DURATION_MS = 1000
BARGE_IN_THRESHOLD = 3200
IDLE_TIMEOUT_SECS = 10
MAX_CALL_DURATION_SECS = settings.MAX_CALL_DURATION_SECS


class VoiceSessionManager:
    """Orchestrates end-to-end voice sessions, audio frame VAD loop, barge-in,
    LLM reasoning stream, and call state persistence."""

    def __init__(
        self,
        audio_processor: AudioProcessor | None = None,
        marker_service: MarkerService | None = None,
        prompt_manager: PromptManager | None = None,
        tts_service: TTSService | None = None,
        stt_service: STTService | None = None,
        llm_service: LLMService | None = None,
    ):
        self.audio_processor = audio_processor or AudioProcessor()
        self.marker_service = marker_service or MarkerService()
        self.prompt_manager = prompt_manager or PromptManager()
        self.tts_service = tts_service or TTSService(self.audio_processor)
        self.stt_service = stt_service or STTService()
        self.llm_service = llm_service or LLMService()

    def create_session_state(self) -> dict:
        return {
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

    async def speak_fallback(self, websocket: WebSocket, session_state: dict) -> None:
        logger.info("[FALLBACK] Triggered fallback audio.")
        current_lang = session_state.get("language_code", "en-IN")
        text = self.prompt_manager.get_fallback_message(current_lang)
        convo_logger.info(f"{self.prompt_manager.agent_name.upper()} ({current_lang}) [fallback]: {text}")
        self.marker_service.add_transcript(session_state, "agent", text, current_lang)
        await self.tts_service.dispatch_tts(text, current_lang, session_state, websocket)

    async def finalize_call(
        self,
        websocket: WebSocket,
        session_state: dict,
        goodbye_text: str | None = None,
    ) -> None:
        """Speak an optional goodbye, wait for playback to finish, then tell the
        frontend to hang up the SIP call and close the websocket."""
        if session_state.get("ending"):
            return
        session_state["ending"] = True
        if goodbye_text:
            lang = session_state.get("language_code", "en-IN")
            convo_logger.info(f"{self.prompt_manager.agent_name.upper()} ({lang}) [closing]: {goodbye_text}")
            self.marker_service.add_transcript(session_state, "agent", goodbye_text, lang)
            await self.tts_service.dispatch_tts(goodbye_text, lang, session_state, websocket)
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

    async def play_greeting(
        self,
        websocket: WebSocket,
        session_state: dict,
        candidate_name: str | None = None,
        position: str | None = None,
    ) -> None:
        call_mode = session_state.get("call_mode", "interview")
        text = self.prompt_manager.get_greeting(call_mode, candidate_name=candidate_name, position=position)
        lang = "en-IN"
        session_state["language_code"] = lang
        session_state["history"] = [{"role": "assistant", "content": text}]

        convo_logger.info(f"{self.prompt_manager.agent_name.upper()} ({lang}) [greeting, mode={call_mode}]: {text}")
        self.marker_service.add_transcript(session_state, "agent", text, lang)
        await self.tts_service.dispatch_tts(text, lang, session_state, websocket)

    async def process_utterance(
        self,
        utterance_bytes: bytes,
        session_state: dict,
        websocket: WebSocket,
        script_dir: str | None = None,
    ) -> None:
        if session_state.get("ending"):
            logger.info("[PIPELINE] Call is ending — dropping late utterance.")
            return

        sarvam_key = settings.get_sarvam_api_key()
        groq_key = settings.get_groq_api_key()

        if not groq_key and not sarvam_key:
            logger.error("[PIPELINE] Missing both SARVAM_API_KEY and GROQ_API_KEY in environment or settings.")
            return

        try:
            t_start = time.time()
            wav_data = self.audio_processor.create_wav_buffer(utterance_bytes)

            transcript = None
            lang_code = None

            # 1a. ASR — Sarvam Saarika
            if sarvam_key:
                transcript, lang_code = await self.stt_service.transcribe_sarvam(wav_data, sarvam_key)

            # 1b. ASR fallback — Groq Whisper
            if lang_code is None:
                if not groq_key:
                    await self.speak_fallback(websocket, session_state)
                    return
                transcript, lang_code = await self.stt_service.transcribe_whisper(wav_data, groq_key)
                if transcript is None and lang_code is None:
                    await self.speak_fallback(websocket, session_state)
                    return

            if not transcript or len(transcript.strip()) < 2:
                logger.info(f"[ASR] Discarding empty or ambient noise transcript ('{transcript}').")
                return

            current_lang, should_discard = self.stt_service.resolve_language(
                transcript, lang_code, session_state
            )
            if should_discard:
                return

            # ASR takes ~1s — the call may have started ending while we transcribed
            if session_state.get("ending"):
                logger.info("[PIPELINE] Call ended during ASR — dropping utterance.")
                return

            convo_logger.info(f"CALLER ({current_lang}): {transcript}")
            self.marker_service.add_transcript(session_state, "caller", transcript, current_lang)
            t_asr = time.time()

            # 2. LLM Provider selection & streaming
            client, model_name, max_tokens, provider = self.llm_service.get_client_and_model()
            lang_name = LANG_MAP.get(current_lang, "English")
            few_shot = self.prompt_manager.get_few_shot(lang_name)
            call_mode = session_state.get("call_mode", "interview")

            candidate = session_state.get("candidate")
            if candidate:
                system_prompt_text = self.prompt_manager.build_candidate_interview_prompt(
                    candidate_name=candidate.name,
                    position=candidate.position,
                    questions=[q.to_dict() if hasattr(q, "to_dict") else q for q in candidate.questions],
                    lang_name=lang_name,
                )
            else:
                system_prompt_text = self.prompt_manager.load_script_prompt(
                    call_mode, lang_name, few_shot, base_dir=script_dir
                )
            logger.info(f"[LLM PROMPT] lang={current_lang} | model={model_name}")

            history = self.llm_service.update_history(session_state, transcript, system_prompt_text)

            llm_res, model_name = await self.llm_service.create_chat_stream(
                client, model_name, history, max_tokens, provider
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

                if not hasattr(chunk, "choices") or not chunk.choices:
                    continue
                delta = getattr(chunk.choices[0], "delta", None)
                if not delta:
                    continue
                text = getattr(delta, "content", None) or ""
                if not text:
                    continue

                # Filter <think> blocks
                if "<think>" in text:
                    in_thinking_block = True
                if in_thinking_block:
                    if "</think>" in text:
                        in_thinking_block = False
                        text = text[text.find("</think>") + len("</think>"):]
                    else:
                        continue

                # Strip markdown
                text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
                text = re.sub(r"\*(.*?)\*", r"\1", text)

                if not text.strip():
                    continue

                if t_llm_first is None:
                    t_llm_first = time.time()

                raw_reply += text
                current_sentence += text

                # Split on sentence-ending or comma punctuation
                parts = re.split(r"([.!?।,]+\s+)", current_sentence)
                if len(parts) > 1:
                    idx = 0
                    while idx < len(parts) - 1:
                        sentence = (parts[idx] + parts[idx + 1]).strip()
                        sentence = re.sub(r"\(.*?\)", "", sentence).strip()
                        sentence = self.marker_service.extract_control_markers(sentence, session_state)
                        if any(
                            skip in sentence
                            for skip in ["Step 1", "Step 2", "Step 3", "Call Flow", "OUTBOUND", "INBOUND"]
                        ):
                            logger.warning(f"[LLM] Skipping script narration: {sentence[:60]}")
                            idx += 2
                            continue
                        if sentence:
                            sentences.append(sentence)
                            logger.info(f"[LLM] Sentence emitted: {sentence}")
                            await self.tts_service.dispatch_tts(sentence, current_lang, session_state, websocket)
                        idx += 2
                    current_sentence = parts[-1].lstrip()

            # Flush remaining text
            if current_sentence.strip():
                cleaned = re.sub(r"\(.*?\)", "", current_sentence).strip()
                cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
                cleaned = self.marker_service.extract_control_markers(cleaned, session_state)
                if cleaned and not any(
                    skip in cleaned for skip in ["Step 1", "Step 2", "Step 3", "Call Flow", "OUTBOUND", "INBOUND"]
                ):
                    sentences.append(cleaned)
                    logger.info(f"[LLM] Sentence emitted: {cleaned}")
                    await self.tts_service.dispatch_tts(cleaned, current_lang, session_state, websocket)

            # Catch markers split across boundaries
            self.marker_service.extract_control_markers(raw_reply, session_state)

            full_reply = " ".join(sentences)
            history.append({"role": "assistant", "content": full_reply})
            t_llm_done = time.time()

            llm_latency = (
                int((t_llm_first - t_asr) * 1000) if t_llm_first else int((t_llm_done - t_asr) * 1000)
            )
            logger.info(f"[LATENCY] ASR: {int((t_asr - t_start)*1000)}ms | LLM first chunk: {llm_latency}ms")
            convo_logger.info(
                f"{self.prompt_manager.agent_name.upper()} ({current_lang}) "
                f"[model={model_name}, latency={llm_latency}ms]: {full_reply}"
            )
            self.marker_service.add_transcript(session_state, "agent", full_reply, current_lang)

            # Guard against premature END_CALL
            if session_state.get("pending_end_call"):
                lower_reply = full_reply.lower()
                soliciting_info = any(
                    kw in lower_reply
                    for kw in [
                        "number", "mobile", "phone", "email", "time", "date", "demo", "schedule",
                        "when", "contact", "details", "repeat", "pardon", "again", "convenient",
                        "tell me", "share",
                    ]
                )
                is_question = full_reply.rstrip().endswith(("?", "؟")) or "?" in full_reply

                if is_question or soliciting_info:
                    logger.warning(
                        f"[CALL FLOW] Premature END_CALL ignored — reply is still continuing conversation: "
                        f"'{full_reply[:60]}...'"
                    )
                    session_state["pending_end_call"] = False
                else:
                    await self.finalize_call(websocket, session_state)

        except Exception as e:
            logger.error(f"[PIPELINE] Exception: {e}", exc_info=True)
            convo_logger.info(f"{self.prompt_manager.agent_name.upper()} [PIPELINE ERROR]: {e}")
            await self.speak_fallback(websocket, session_state)

    async def handle_teleforce_stream(
        self,
        websocket: WebSocket,
        recordings_dir: str | None = None,
        calls_log_path: str | None = None,
    ) -> None:
        """Main WebSocket loop handling full duplex audio streaming and state transitions."""
        await websocket.accept()
        logger.info("[TELEFORCE WSS] Connection established")

        session_state = self.create_session_state()
        playback_task = asyncio.create_task(self.tts_service.tts_playback_worker(session_state, websocket))
        pipeline_task = None

        audio_buffer = bytearray()
        silence_bytes_threshold = int(32000 * (SILENCE_DURATION_MS / 1000.0))
        min_speech_bytes = int(32000 * (MIN_SPEECH_DURATION_MS / 1000.0))

        current_silence_bytes = 0
        is_speaking = False

        try:
            while True:
                msg_str = await websocket.receive_text()
                msg = json.loads(msg_str)
                event = msg.get("event")

                if event == "start":
                    mode = msg.get("callMode") or msg.get("mode") or "interview"
                    candidate_id = msg.get("candidate_id") or msg.get("candidateId")
                    session_state["call_mode"] = mode
                    session_state["phone"] = (msg.get("phone") or "").strip()
                    session_state["call_start"] = time.time()
                    session_state["last_activity"] = time.time()
                    call_id = (
                        time.strftime("%Y%m%d_%H%M%S")
                        + ("_incoming" if mode == "inbound" else "_interview")
                    )
                    session_state["call_id"] = call_id
                    session_state["recorder"] = CallRecorder(call_id)

                    cand = None
                    if candidate_id:
                        cand = candidate_repo.get_by_id(candidate_id)
                    elif session_state["phone"]:
                        cand = candidate_repo.get_by_phone(session_state["phone"])

                    if cand:
                        session_state["candidate"] = cand
                        session_state["candidate_id"] = cand.id
                        cand.status = "in_progress"
                        cand.call_id = call_id
                        candidate_repo.save(cand)
                        logger.info(f"[INTERVIEW WSS] Starting interview for {cand.name} (id={cand.id}). Playing greeting...")
                        await self.play_greeting(websocket, session_state, candidate_name=cand.name, position=cand.position)
                    else:
                        logger.info(f"[INTERVIEW WSS] Received 'start' (mode={mode}, id={call_id}). Playing greeting...")
                        await self.play_greeting(websocket, session_state)

                elif event == "media":
                    audio_b64 = msg["media"]["payload"]
                    pcm_bytes = base64.b64decode(audio_b64)

                    recorder = session_state.get("recorder")
                    if recorder:
                        recorder.add_caller(pcm_bytes)

                    if session_state.get("ending"):
                        continue

                    rms = audioop.rms(pcm_bytes, 2)
                    now = time.time()

                    # Max call length cap
                    if now - session_state.get("call_start", now) > MAX_CALL_DURATION_SECS:
                        logger.info(f"[CALL FLOW] Max call duration ({MAX_CALL_DURATION_SECS}s) reached. Wrapping up.")
                        lang = session_state.get("language_code", "en-IN")
                        goodbye = self.prompt_manager.get_timeup_goodbye(lang)
                        asyncio.create_task(self.finalize_call(websocket, session_state, goodbye))
                        continue

                    agent_speaking = now < session_state.get("playback_end_time", 0)

                    if agent_speaking:
                        if rms > BARGE_IN_THRESHOLD:
                            logger.info(f"[BARGE-IN] Detected! RMS: {rms}")
                            session_state["cancel_tts_before"] = time.time()
                            session_state["playback_end_time"] = 0

                            if pipeline_task and not pipeline_task.done():
                                pipeline_task.cancel()

                            await websocket.send_json({"event": "clear"})

                            while not session_state["tts_queue"].empty():
                                try:
                                    session_state["tts_queue"].get_nowait()
                                    session_state["tts_queue"].task_done()
                                except Exception:
                                    pass

                            audio_buffer = bytearray()
                            is_speaking = True
                            current_silence_bytes = 0
                            audio_buffer.extend(pcm_bytes)
                        continue

                    # Normal VAD
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

                            if current_silence_bytes >= silence_bytes_threshold:
                                is_speaking = False
                                session_state["last_activity"] = now
                                logger.info(f"[VAD] Speech ended after {len(audio_buffer)} bytes.")

                                if len(audio_buffer) >= min_speech_bytes:
                                    utterance = bytes(audio_buffer)
                                    session_state["barge_in"] = False
                                    if pipeline_task and not pipeline_task.done():
                                        logger.info(
                                            "[VAD] New utterance while previous reply in flight — superseding it."
                                        )
                                        pipeline_task.cancel()
                                        session_state["cancel_tts_before"] = time.time()
                                    pipeline_task = asyncio.create_task(
                                        self.process_utterance(utterance, session_state, websocket)
                                    )
                                else:
                                    logger.info("[VAD] Utterance too short, discarding.")

                                audio_buffer = bytearray()
                                current_silence_bytes = 0
                        else:
                            # Caller silence check
                            if pipeline_task and not pipeline_task.done():
                                session_state["last_activity"] = now
                            else:
                                idle_base = max(
                                    session_state.get("last_activity", now),
                                    session_state.get("playback_end_time", 0),
                                )
                                if now - idle_base > IDLE_TIMEOUT_SECS:
                                    lang = session_state.get("language_code", "en-IN")
                                    if session_state.get("idle_nudges", 0) == 0:
                                        session_state["idle_nudges"] = 1
                                        session_state["last_activity"] = now
                                        nudge = self.prompt_manager.get_idle_nudge(lang)
                                        logger.info(f"[CALL FLOW] Caller silent for {IDLE_TIMEOUT_SECS}s — nudging.")
                                        convo_logger.info(
                                            f"{self.prompt_manager.agent_name.upper()} ({lang}) [silence nudge]: {nudge}"
                                        )
                                        self.marker_service.add_transcript(session_state, "agent", nudge, lang)
                                        await self.tts_service.dispatch_tts(nudge, lang, session_state, websocket)
                                    else:
                                        goodbye = self.prompt_manager.get_idle_goodbye(lang)
                                        logger.info("[CALL FLOW] Caller still silent after nudge — ending call.")
                                        asyncio.create_task(self.finalize_call(websocket, session_state, goodbye))

                elif event == "stop":
                    logger.info("[TELEFORCE WSS] Call stopped")
                    break

        except WebSocketDisconnect:
            logger.info("[TELEFORCE WSS] WebSocket disconnected")
        except Exception as e:
            logger.error(f"[TELEFORCE WSS] Error: {e}", exc_info=True)
            convo_logger.info(f"===== CALL ERROR: {e} =====")
        finally:
            if not session_state.get("lead_logged"):
                self.marker_service.log_lead("status=INCOMPLETE | call ended without lead capture", session_state)

            recording_file = None
            recorder = session_state.get("recorder")
            if recorder:
                recording_file = recorder.save(recordings_dir=recordings_dir)
            if session_state.get("call_id"):
                try:
                    end_time = time.time()
                    start_time = session_state.get("call_start", end_time)
                    cand_obj = session_state.get("candidate")
                    candidate_id = session_state.get("candidate_id") or (cand_obj.id if cand_obj else None)
                    record = {
                        "id": session_state["call_id"],
                        "candidate_id": candidate_id,
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
                        c_log_path = calls_log_path or os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "calls.jsonl"
                        )
                        os.makedirs(os.path.dirname(c_log_path), exist_ok=True)
                        with open(c_log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception as e:
                    logger.error(f"[CALL HISTORY] Failed to save call record: {e}")

            # Candidate Interview Post-Processing
            cand = session_state.get("candidate")
            if cand:
                cand.status = "completed"
                cand.call_id = session_state.get("call_id")
                candidate_repo.save(cand)
                # Asynchronously generate scorecard evaluation from transcript
                asyncio.create_task(
                    self._evaluate_candidate_session(cand, session_state.get("transcript", []))
                )

            convo_logger.info("===== CALL ENDED =====")
            if playback_task:
                playback_task.cancel()

    async def _evaluate_candidate_session(self, candidate, transcript: list) -> None:
        try:
            from services.interview_service import interview_service
            logger.info(f"[INTERVIEW SESSION] Running automated scorecard evaluation for {candidate.name}...")
            scorecard = await interview_service.evaluate_interview(candidate, transcript)
            candidate.scorecard = scorecard
            candidate.status = "evaluated"
            candidate_repo.save(candidate)
            logger.info(
                f"[INTERVIEW SESSION] Scorecard evaluated for {candidate.name}: "
                f"{scorecard.recommendation} (Score: {scorecard.overall_score}/100)"
            )
        except Exception as e:
            logger.error(f"[INTERVIEW SESSION] Failed post-interview evaluation for {candidate.name}: {e}")
