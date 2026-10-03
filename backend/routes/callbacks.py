import os
import time
import json
from fastapi import APIRouter, Body
from typing import List, Dict, Any
from core.config import settings
from services.database_manager import callback_repo
from models.callback import Callback

router = APIRouter(prefix="/callbacks", tags=["Callbacks"])

_CALLBACKS_JSONL = os.path.join(str(settings.LOGS_DIR), "callbacks.jsonl")


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
def get_callbacks():
    """Customers who asked to be called back later."""
    rows = callback_repo.get_all()
    if rows is not None:
        return rows
    return _read_jsonl(_CALLBACKS_JSONL)


@router.post("")
def add_callback(cb: Dict[str, Any] = Body(...)):
    """Manually add a callback entry."""
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "call_id": "",
        "direction": "outgoing",
        "phone": cb.get("phone", ""),
        "language": cb.get("language", ""),
        "callback_time": cb.get("callback_time") or cb.get("name", ""),
    }
    ok = callback_repo.save(Callback.from_dict(record))
    return {"success": ok, "callback": record}


@router.post("/{callback_id}/done")
def mark_callback_done(callback_id: int, body: Dict[str, Any] = Body(default_factory=dict)):
    done = bool(body.get("done", True))
    return {"success": callback_repo.mark_done(callback_id, done)}


@router.delete("/{callback_id}")
def delete_callback(callback_id: int):
    return {"success": callback_repo.delete(callback_id)}
