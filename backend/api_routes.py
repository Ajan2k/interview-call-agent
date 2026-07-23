import os
import json
from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Any

import database as db

router = APIRouter(prefix="/api")

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
            "stt": "Groq Whisper",
            "llm": "Groq LLaMA 3.3 70B",
            "tts": "Azure Neural TTS"
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
