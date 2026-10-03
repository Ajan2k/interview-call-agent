import os
import io
import csv
import json
import re
from typing import List, Dict, Any, Optional

from services.database_manager import CallRepository


class ReportService:
    """Class-based service for filtering call logs, aggregating metrics, and exporting reports."""

    def __init__(self, call_repo: CallRepository = None, logs_dir: str = None):
        self.call_repo = call_repo
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        self.calls_jsonl_path = os.path.join(self.logs_dir, "calls.jsonl")

    @staticmethod
    def extract_lead_status(call: Dict[str, Any]) -> str:
        status = call.get("lead_status")
        if status:
            return status.upper()
        lead_text = call.get("lead", "") or ""
        m = re.search(r"status\s*=\s*([A-Za-z_]+)", lead_text)
        return m.group(1).upper() if m else ""

    def _read_jsonl_calls(self, limit: int = 5000) -> List[Dict[str, Any]]:
        if not os.path.exists(self.calls_jsonl_path):
            return []
        items = []
        try:
            with open(self.calls_jsonl_path, "r", encoding="utf-8") as f:
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

    def filter_calls(
        self,
        date_from: str = "",
        date_to: str = "",
        direction: str = "",
        lead_status: str = "",
        language: str = "",
    ) -> List[Dict[str, Any]]:
        """Filters calls from PostgreSQL repository or falls back to JSONL file."""
        if self.call_repo:
            rows = self.call_repo.get_all(
                date_from=date_from,
                date_to=date_to,
                direction=direction,
                lead_status=lead_status,
                language=language,
            )
            if rows is not None:
                return rows

        # Fallback to JSONL file
        rows = self._read_jsonl_calls(limit=5000)
        filtered = []
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
                call_lead = self.extract_lead_status(r)
                if call_lead != lead_status.upper():
                    continue
            filtered.append(r)
        return filtered

    def generate_report(
        self,
        date_from: str = "",
        date_to: str = "",
        direction: str = "",
        lead_status: str = "",
        language: str = "",
    ) -> Dict[str, Any]:
        """Calculates KPI metrics across filtered calls."""
        calls = self.filter_calls(date_from, date_to, direction, lead_status, language)

        total = len(calls)
        hot = sum(1 for c in calls if self.extract_lead_status(c) == "HOT")
        warm = sum(1 for c in calls if self.extract_lead_status(c) == "WARM")
        cold = sum(1 for c in calls if self.extract_lead_status(c) == "COLD")
        incomplete = sum(1 for c in calls if self.extract_lead_status(c) in ("INCOMPLETE", ""))
        demos = sum(1 for c in calls if (c.get("meeting") or "").strip())
        incoming = sum(1 for c in calls if c.get("direction") == "incoming")
        outgoing = sum(1 for c in calls if c.get("direction") == "outgoing")
        total_dur = sum(int(c.get("duration_sec", 0) or 0) for c in calls)
        avg_dur = round(total_dur / total) if total else 0

        return {
            "summary": {
                "total": total,
                "incoming": incoming,
                "outgoing": outgoing,
                "hot": hot,
                "warm": warm,
                "cold": cold,
                "incomplete": incomplete,
                "demos_booked": demos,
                "total_duration_sec": total_dur,
                "avg_duration_sec": avg_dur,
            },
            "calls": calls,
        }

    def generate_csv(
        self,
        date_from: str = "",
        date_to: str = "",
        direction: str = "",
        lead_status: str = "",
        language: str = "",
    ) -> str:
        """Generates CSV format string from filtered calls."""
        calls = self.filter_calls(date_from, date_to, direction, lead_status, language)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Direction", "Phone", "Start", "End", "Duration (sec)",
            "Language", "Lead Status", "Lead Details", "Demo Booked", "Ended By", "Recording"
        ])
        for c in calls:
            writer.writerow([
                c.get("direction", ""),
                c.get("phone", ""),
                c.get("start", ""),
                c.get("end", ""),
                c.get("duration_sec", 0),
                c.get("language", ""),
                self.extract_lead_status(c),
                c.get("lead", ""),
                c.get("meeting", ""),
                c.get("ended_by", ""),
                c.get("recording", "") or "",
            ])
        return buf.getvalue()
