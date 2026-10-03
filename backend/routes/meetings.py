import os
import json
from fastapi import APIRouter
from typing import List, Dict, Any
from core.config import settings
from services.database_manager import meeting_repo

router = APIRouter(prefix="/meetings", tags=["Meetings"])

_MEETINGS_JSONL = os.path.join(str(settings.LOGS_DIR), "meetings.jsonl")


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


@router.get("", response_model=List[Dict[str, Any]])
def get_meetings():
    """Demo meetings booked by the agent, newest first."""
    rows = meeting_repo.get_all()
    if rows is not None:
        return rows
    return _read_jsonl(_MEETINGS_JSONL)
