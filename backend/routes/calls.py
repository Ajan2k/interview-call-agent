import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List, Dict, Any
from core.config import settings
from services.database_manager import call_repo

router = APIRouter(tags=["Calls"])

_RECORDINGS_DIR = str(settings.RECORDINGS_DIR)
_CALLS_JSONL = os.path.join(str(settings.LOGS_DIR), "calls.jsonl")


def _read_jsonl(path: str, limit: int = 200) -> List[Dict[str, Any]]:
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


@router.get("/call-history")
def get_call_history():
    """Completed calls, newest first. Served from PostgreSQL; falls back to JSONL file."""
    rows = call_repo.get_all()
    if rows is not None:
        return rows
    return _read_jsonl(_CALLS_JSONL)


@router.get("/call-history/{call_id}/transcript")
def get_call_transcript(call_id: str):
    """Full conversation transcript for one call with candidate metadata."""
    result = call_repo.get_transcript(call_id)
    if result is not None:
        return result
    for item in _read_jsonl(_CALLS_JSONL):
        if item.get("id") == call_id:
            return {
                "found": True,
                "phone": item.get("phone", ""),
                "direction": item.get("direction", ""),
                "start": item.get("start", ""),
                "candidate_id": item.get("candidate_id"),
                "candidate_name": item.get("candidate_name"),
                "transcript": item.get("transcript", []) or [],
            }
    raise HTTPException(status_code=404, detail="Call transcript not found")


@router.get("/recordings/{filename}")
def get_recording(filename: str):
    """Serve a saved call recording WAV file."""
    if os.path.sep in filename or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(_RECORDINGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(path, media_type="audio/wav", filename=filename)
