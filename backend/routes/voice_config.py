from fastapi import APIRouter, Body
from typing import Dict, Any
from services.database_manager import voice_config_repo

router = APIRouter(prefix="/voice-config", tags=["Voice Config"])

# In-memory fallback
voice_config_db: Dict[str, Any] = {
    "speechMode": "Natural Female Voice (Azure Neerja / Pallavi)",
    "languageFocus": "Automatic Multi-language (Tamil, Hindi, English)",
    "promptTemplate": (
        "You are Alex, an intelligent, empathetic, and professional AI Technical Recruiter and Interviewer.\n"
        "Your objective is to conduct an interactive preliminary screening interview with the candidate.\n"
        "You will ask 5 behavioral questions and up to 10 personalized technical questions tailored to their resume and the job requirements.\n"
        "Be encouraging, listen carefully to their answers, ask natural follow-ups if needed, and maintain a concise conversational pace."
    ),
}


@router.get("", response_model=Dict[str, Any])
def get_voice_config():
    db_cfg = voice_config_repo.get()
    if db_cfg and db_cfg.get("promptTemplate"):
        return db_cfg
    return voice_config_db


@router.post("")
def update_voice_config_post(config: Dict[str, Any] = Body(...)):
    global voice_config_db
    voice_config_db.update(config)
    voice_config_repo.save(config)
    return {"status": "ok", "config": voice_config_db}


@router.put("")
def update_voice_config_put(config: Dict[str, Any] = Body(...)):
    return update_voice_config_post(config)
