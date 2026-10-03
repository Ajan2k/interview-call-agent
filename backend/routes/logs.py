from fastapi import APIRouter
from typing import List, Dict, Any
from services.log_service import LogService

router = APIRouter(prefix="/logs", tags=["Logs"])

_log_service = LogService()


@router.get("", response_model=List[Dict[str, Any]])
def get_logs():
    """Retrieve recent conversation log lines."""
    return _log_service.get_recent_conversation_logs(limit=50)


@router.delete("")
def clear_all_logs():
    """Clear conversation log history."""
    ok = _log_service.clear_conversation_logs()
    return {"success": ok}


@router.delete("/{log_id}")
def delete_single_log(log_id: str):
    return {"success": True}
