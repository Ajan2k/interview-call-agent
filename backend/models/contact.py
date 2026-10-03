from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


@dataclass
class Contact:
    id: str
    name: str
    phone: str
    status: str = "Pending"
    last_called: str = "Never"
    notes: Optional[str] = ""
    is_incoming: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "status": self.status,
            "lastCalled": self.last_called,
            "notes": self.notes or "",
            "isIncoming": self.is_incoming,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contact":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            phone=str(data.get("phone", "")),
            status=str(data.get("status", "Pending")),
            last_called=str(data.get("lastCalled") or data.get("last_called", "Never")),
            notes=data.get("notes", ""),
            is_incoming=bool(data.get("isIncoming") or data.get("is_incoming", False)),
        )
