import os
from typing import List, Dict, Any


class LogService:
    """Class-based service for accessing and managing conversation and system logs."""

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(backend_dir, "logs")
        self.log_dir = log_dir
        self.conversation_log_path = os.path.join(self.log_dir, "conversation.log")

    def get_recent_conversation_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent conversation log lines formatted with id and timestamp."""
        logs_data = []
        if os.path.exists(self.conversation_log_path):
            try:
                with open(self.conversation_log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for idx, line in enumerate(reversed(lines[-limit:])):
                        logs_data.append({
                            "id": str(idx + 1),
                            "timestamp": line[:19] if len(line) >= 19 else "",
                            "message": line.strip(),
                        })
            except Exception:
                pass
        return logs_data

    def clear_conversation_logs(self) -> bool:
        """Truncates the conversation log file."""
        if os.path.exists(self.conversation_log_path):
            try:
                with open(self.conversation_log_path, "w", encoding="utf-8") as f:
                    f.write("")
                return True
            except Exception:
                return False
        return True
