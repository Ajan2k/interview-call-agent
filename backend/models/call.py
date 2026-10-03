from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import re


@dataclass
class Call:
    id: str
    direction: str
    phone: str
    start: Optional[str] = None
    end: Optional[str] = None
    duration_sec: int = 0
    language: str = "en-IN"
    lead: Optional[str] = ""
    lead_status: Optional[str] = ""
    meeting: Optional[str] = ""
    callback: Optional[str] = ""
    ended_by: Optional[str] = ""
    recording: Optional[str] = ""
    transcript: List[Dict[str, Any]] = field(default_factory=list)

    def resolved_lead_status(self) -> str:
        if self.lead_status:
            return self.lead_status.upper()
        if self.lead:
            m = re.search(r"status\s*=\s*([A-Za-z_]+)", self.lead)
            if m:
                return m.group(1).upper()
        return ""

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "direction": self.direction,
            "phone": self.phone,
            "start": self.start,
            "end": self.end,
            "duration_sec": self.duration_sec,
            "language": self.language,
            "lead": self.lead or "",
            "lead_status": self.resolved_lead_status(),
            "meeting": self.meeting or "",
            "callback": self.callback or "",
            "ended_by": self.ended_by or "",
            "recording": self.recording or "",
        }
        if self.transcript is not None:
            data["transcript"] = self.transcript
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Call":
        return cls(
            id=str(data.get("id", "")),
            direction=str(data.get("direction", "")),
            phone=str(data.get("phone", "")),
            start=data.get("start") or data.get("start_time"),
            end=data.get("end") or data.get("end_time"),
            duration_sec=int(data.get("duration_sec", 0) or 0),
            language=str(data.get("language", "en-IN")),
            lead=data.get("lead", ""),
            lead_status=data.get("lead_status", ""),
            meeting=data.get("meeting", ""),
            callback=data.get("callback", ""),
            ended_by=data.get("ended_by", ""),
            recording=data.get("recording", ""),
            transcript=data.get("transcript"),
        )
