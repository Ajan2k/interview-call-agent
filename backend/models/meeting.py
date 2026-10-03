from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Meeting:
    time: str
    call_id: str
    direction: str
    phone: str
    language: str
    details: str
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "time": self.time,
            "call_id": self.call_id,
            "direction": self.direction,
            "phone": self.phone,
            "language": self.language,
            "details": self.details,
        }
        if self.id is not None:
            data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Meeting":
        return cls(
            time=str(data.get("time", "")),
            call_id=str(data.get("call_id", "")),
            direction=str(data.get("direction", "")),
            phone=str(data.get("phone", "")),
            language=str(data.get("language", "")),
            details=str(data.get("details", "")),
            id=int(data["id"]) if "id" in data and data["id"] is not None else None,
        )
