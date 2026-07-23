import os
import io
import csv
import json
import httpx
from fastapi import APIRouter, HTTPException, Body, Query
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Dict, Any, Optional

import database as db

router = APIRouter(prefix="/api")

_BACKEND_DIR = os.path.dirname(__file__)
_RECORDINGS_DIR = os.path.join(_BACKEND_DIR, "recordings")


def _read_jsonl(path: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Read a JSON-lines file, newest entries first."""
    if not os.path.exists(path):
        return []
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return []
    return list(reversed(items[-limit:]))

# In-memory fallbacks
contacts_db: List[Dict[str, Any]] = []
campaigns_db: List[Dict[str, Any]] = []
voice_config_db: Dict[str, Any] = {
    "speechMode": "Natural Female Voice (Azure Neerja / Pallavi)",
    "languageFocus": "Automatic Multi-language (Tamil, Hindi, English)",
    "promptTemplate": "You are Daffy, a warm AI Sales Consultant calling from Daffytel Technologies..."
}

@router.get("/health")
def get_health():
    groq_key = os.getenv("GROQ_API_KEY", "")
    azure_key = os.getenv("AZURE_SPEECH_KEY", "")
    has_api_key = bool(groq_key and azure_key)

    # Ensure PostgreSQL tables are created in skyagent database
    db.init_db()
    conn = db.get_db_connection()
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
            "tts": "Cartesia Sonic 3.5 (Sarvam/Azure fallback)"
        }
    }

@router.get("/voice-config")
def get_voice_config():
    db_cfg = db.db_get_voice_config()
    if db_cfg and db_cfg.get("promptTemplate"):
        return db_cfg
    return voice_config_db

@router.post("/voice-config")
def update_voice_config(config: Dict[str, Any] = Body(...)):
    global voice_config_db
    voice_config_db.update(config)
    db.db_save_voice_config(config)
    return {"status": "ok", "config": voice_config_db}

@router.get("/campaigns")
def get_campaigns():
    return campaigns_db

@router.get("/contacts")
def get_contacts():
    pg_contacts = db.db_get_contacts()
    if pg_contacts:
        return pg_contacts
    return contacts_db

@router.post("/contacts")
def add_contact(contact: Dict[str, Any] = Body(...)):
    global contacts_db
    contact["id"] = str(len(contacts_db) + 1)
    if "status" not in contact:
        contact["status"] = "Pending"
    if "lastCalled" not in contact:
        contact["lastCalled"] = "Never"
    contacts_db.append(contact)
    db.db_save_contact(contact)
    return contact

@router.put("/contacts/{contact_id}")
def update_contact(contact_id: str, updates: Dict[str, Any] = Body(...)):
    for c in contacts_db:
        if c["id"] == contact_id:
            c.update(updates)
            return c
    raise HTTPException(status_code=404, detail="Contact not found")

@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: str):
    global contacts_db
    contacts_db = [c for c in contacts_db if c["id"] != contact_id]
    db.db_delete_contact(contact_id)
    return {"success": True}

@router.get("/call-history")
def get_call_history():
    """Completed calls, newest first: direction, phone, duration, lead, meeting, recording.
    Served from PostgreSQL; falls back to the JSONL file if the DB is unavailable."""
    rows = db.db_get_calls()
    if rows is not None:
        return rows
    return _read_jsonl(os.path.join(_BACKEND_DIR, "logs", "calls.jsonl"))


@router.get("/meetings")
def get_meetings():
    """Demo meetings booked by the agent, newest first."""
    rows = db.db_get_meetings()
    if rows is not None:
        return rows
    return _read_jsonl(os.path.join(_BACKEND_DIR, "logs", "meetings.jsonl"))


@router.get("/callbacks")
def get_callbacks():
    """Customers who asked to be called back later (pending first, then done)."""
    rows = db.db_get_callbacks()
    if rows is not None:
        return rows
    return _read_jsonl(os.path.join(_BACKEND_DIR, "logs", "callbacks.jsonl"))


@router.get("/call-history/{call_id}/transcript")
def get_call_transcript(call_id: str):
    """Full conversation of one call: list of {role, text, lang, time}."""
    result = db.db_get_call_transcript(call_id)
    if result is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return result


_SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"


@router.post("/translate")
def translate_text(body: Dict[str, Any] = Body(...)):
    """Translate a chat message to English (for the conversation viewer).
    Uses Sarvam's translate API; returns the original text if translation fails."""
    text = (body.get("text") or "").strip()
    source = body.get("source_language_code") or "auto"
    target = body.get("target_language_code") or "en-IN"
    if not text:
        return {"translated": "", "source": source}

    # Already in the target language (e.g. en-IN → en-IN) — nothing to translate.
    if source != "auto" and source.split("-")[0] == target.split("-")[0]:
        return {"translated": text, "source": source, "same_language": True}

    sarvam_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_key:
        return {"translated": text, "source": source, "error": "No SARVAM_API_KEY"}

    try:
        res = httpx.post(
            _SARVAM_TRANSLATE_URL,
            headers={"api-subscription-key": sarvam_key, "Content-Type": "application/json"},
            json={
                "input": text,
                "source_language_code": source,
                "target_language_code": target,
                "mode": "formal",
            },
            timeout=15.0,
        )
        if res.status_code == 200:
            j = res.json()
            return {"translated": j.get("translated_text", text), "source": j.get("source_language_code", source)}
        return {"translated": text, "source": source, "error": f"Sarvam {res.status_code}"}
    except Exception as e:
        return {"translated": text, "source": source, "error": str(e)}


@router.post("/callbacks")
def add_callback(cb: Dict[str, Any] = Body(...)):
    """Manually add a callback entry (from the Scheduler's Add form)."""
    import time as _time
    record = {
        "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
        "call_id": "",
        "direction": "outgoing",
        "phone": cb.get("phone", ""),
        "language": cb.get("language", ""),
        "callback_time": cb.get("callback_time") or cb.get("name", ""),
    }
    ok = db.db_save_callback(record)
    return {"success": ok, "callback": record}


@router.post("/callbacks/{callback_id}/done")
def mark_callback_done(callback_id: int, body: Dict[str, Any] = Body(default={})):
    done = bool(body.get("done", True))
    return {"success": db.db_mark_callback_done(callback_id, done)}


@router.delete("/callbacks/{callback_id}")
def delete_callback(callback_id: int):
    return {"success": db.db_delete_callback(callback_id)}


def _filtered_calls(date_from: str, date_to: str, direction: str,
                    lead_status: str, language: str) -> List[Dict[str, Any]]:
    """Apply report filters against the DB, or against the JSONL file as fallback."""
    rows = db.db_get_calls(date_from=date_from, date_to=date_to, direction=direction,
                           lead_status=lead_status, language=language)
    if rows is not None:
        return rows
    # JSONL fallback with in-Python filtering
    rows = _read_jsonl(os.path.join(_BACKEND_DIR, "logs", "calls.jsonl"), limit=5000)
    out = []
    for r in rows:
        start = r.get("start", "")
        if date_from and start[:10] < date_from:
            continue
        if date_to and start[:10] > date_to:
            continue
        if direction and r.get("direction") != direction:
            continue
        if language and r.get("language") != language:
            continue
        if lead_status:
            import re
            m = re.search(r"status\s*=\s*([A-Za-z_]+)", r.get("lead", "") or "")
            if not m or m.group(1).upper() != lead_status.upper():
                continue
        out.append(r)
    return out


@router.get("/report")
def get_report(
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    direction: str = Query(""),
    lead_status: str = Query("", alias="lead"),
    language: str = Query(""),
):
    """Customizable report: filtered calls plus summary counts for the dashboard."""
    calls = _filtered_calls(date_from, date_to, direction, lead_status, language)

    total = len(calls)
    hot = sum(1 for c in calls if _lead_of(c) == "HOT")
    warm = sum(1 for c in calls if _lead_of(c) == "WARM")
    cold = sum(1 for c in calls if _lead_of(c) == "COLD")
    incomplete = sum(1 for c in calls if _lead_of(c) in ("INCOMPLETE", ""))
    demos = sum(1 for c in calls if (c.get("meeting") or "").strip())
    incoming = sum(1 for c in calls if c.get("direction") == "incoming")
    outgoing = sum(1 for c in calls if c.get("direction") == "outgoing")
    total_dur = sum(int(c.get("duration_sec", 0) or 0) for c in calls)
    avg_dur = round(total_dur / total) if total else 0

    return {
        "summary": {
            "total": total, "incoming": incoming, "outgoing": outgoing,
            "hot": hot, "warm": warm, "cold": cold, "incomplete": incomplete,
            "demos_booked": demos, "total_duration_sec": total_dur, "avg_duration_sec": avg_dur,
        },
        "calls": calls,
    }


@router.get("/report/export")
def export_report_csv(
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    direction: str = Query(""),
    lead_status: str = Query("", alias="lead"),
    language: str = Query(""),
):
    """Download the filtered report as a CSV file."""
    calls = _filtered_calls(date_from, date_to, direction, lead_status, language)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Direction", "Phone", "Start", "End", "Duration (sec)",
                     "Language", "Lead Status", "Lead Details", "Demo Booked", "Ended By", "Recording"])
    for c in calls:
        writer.writerow([
            c.get("direction", ""), c.get("phone", ""), c.get("start", ""), c.get("end", ""),
            c.get("duration_sec", 0), c.get("language", ""), _lead_of(c),
            c.get("lead", ""), c.get("meeting", ""), c.get("ended_by", ""), c.get("recording", "") or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=call_report.csv"},
    )


def _lead_of(call: Dict[str, Any]) -> str:
    status = call.get("lead_status")
    if status:
        return status.upper()
    import re
    m = re.search(r"status\s*=\s*([A-Za-z_]+)", call.get("lead", "") or "")
    return m.group(1).upper() if m else ""


@router.get("/recordings/{filename}")
def get_recording(filename: str):
    """Serve a saved call recording WAV."""
    if os.path.sep in filename or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(_RECORDINGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(path, media_type="audio/wav", filename=filename)


@router.get("/logs")
def get_logs():
    # Read conversation log if available
    log_file = os.path.join(os.path.dirname(__file__), "logs", "conversation.log")
    logs_data = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Parse last 50 lines
                for idx, line in enumerate(reversed(lines[-50:])):
                    logs_data.append({
                        "id": str(idx + 1),
                        "timestamp": line[:19] if len(line) >= 19 else "",
                        "message": line.strip()
                    })
        except Exception:
            pass
    return logs_data

@router.delete("/logs")
def clear_all_logs():
    log_file = os.path.join(os.path.dirname(__file__), "logs", "conversation.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
    return {"success": True}

@router.delete("/logs/{log_id}")
def delete_single_log(log_id: str):
    return {"success": True}
