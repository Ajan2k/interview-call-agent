import os
import re
import json
import time
import logging
from core.logging import get_conversation_logger
from services import database_manager as db

logger = logging.getLogger("voice.markers")
convo_logger = get_conversation_logger()

# Control markers the LLM appends to signal call state (never spoken aloud)
ENDCALL_RE = re.compile(r'\[?END[_ ]?CALL\]?')
MEETING_RE = re.compile(r'\[MEETING[_ ]?BOOKED\s*:?\s*([^\]]*)\]')
CALLBACK_RE = re.compile(r'\[CALLBACK\s*:?\s*([^\]]*)\]')
LEAD_RE = re.compile(r'\[LEAD\s*:?\s*([^\]]*)\]')


class MarkerService:
    """Handles detection, parsing, and logging of conversation control markers."""

    @staticmethod
    def add_transcript(session_state: dict, role: str, text: str, lang: str) -> None:
        """Append one chat turn to the per-call transcript."""
        text = (text or "").strip()
        if not text:
            return
        session_state.setdefault("transcript", []).append({
            "role": role,
            "text": text,
            "lang": lang,
            "time": time.strftime("%H:%M:%S"),
        })

    def extract_control_markers(
        self,
        text: str,
        session_state: dict,
        log_meeting_fn=None,
        log_callback_fn=None,
        log_lead_fn=None,
    ) -> str:
        """Strip [END_CALL] / [MEETING_BOOKED: ...] / [LEAD: ...] markers from LLM text
        before TTS, recording their effects on the session."""
        m_fn = log_meeting_fn or self.log_meeting
        cb_fn = log_callback_fn or self.log_callback
        lead_fn = log_lead_fn or self.log_lead

        m = MEETING_RE.search(text)
        if m:
            details = m.group(1).strip()
            # Ignore hallucinated placeholders like "<day and time>" — only log real bookings
            if details and "<" not in details and "day and time" not in details.lower():
                m_fn(details, session_state)
            text = MEETING_RE.sub("", text)

        cb = CALLBACK_RE.search(text)
        if cb:
            cb_details = cb.group(1).strip()
            if cb_details and "<" not in cb_details:
                cb_fn(cb_details, session_state)
            text = CALLBACK_RE.sub("", text)

        lm = LEAD_RE.search(text)
        if lm:
            lead_fn(lm.group(1).strip(), session_state)
            text = LEAD_RE.sub("", text)

        if ENDCALL_RE.search(text):
            session_state["pending_end_call"] = True
            logger.info("[CALL FLOW] LLM signalled END_CALL.")
            text = ENDCALL_RE.sub("", text)

        # Drop an unterminated trailing marker fragment like "[MEETING_BOOKED: Mon"
        text = re.sub(r'\[[A-Z_][^\]]*$', '', text)
        return text.strip()

    def log_meeting(
        self,
        details: str,
        session_state: dict,
        db_save_fn=None,
        meetings_log_path: str | None = None,
    ) -> None:
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

        saver = db_save_fn if db_save_fn is not None else db.db_save_meeting
        if not saver(record):
            # PostgreSQL unavailable — fall back to the JSONL file
            try:
                path = meetings_log_path or os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "meetings.jsonl"
                )
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"[MEETING] Failed to write meetings.jsonl: {e}")

    def log_callback(
        self,
        details: str,
        session_state: dict,
        db_save_fn=None,
        callbacks_log_path: str | None = None,
    ) -> None:
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

        saver = db_save_fn if db_save_fn is not None else db.db_save_callback
        if not saver(record):
            try:
                path = callbacks_log_path or os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "callbacks.jsonl"
                )
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"[CALLBACK] Failed to write callbacks.jsonl: {e}")

    def log_lead(
        self,
        details: str,
        session_state: dict,
        leads_log_path: str | None = None,
    ) -> None:
        if session_state.get("lead_logged") or not details:
            return
        session_state["lead_logged"] = True
        session_state["lead_details"] = details
        lang = session_state.get("language_code", "en-IN")
        mode = session_state.get("call_mode", "outbound")
        convo_logger.info(f"===== LEAD ({mode}, {lang}): {details} =====")
        try:
            path = leads_log_path or os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "leads.log"
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | mode={mode} | lang={lang} | {details}\n")
        except Exception as e:
            logger.error(f"[LEAD] Failed to write leads.log: {e}")
