from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Campaign:
    id: str
    name: str
    status: str = "Active"
    contacts_count: int = 0
    date: str = "Today"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "contacts_count": self.contacts_count,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Campaign":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            status=str(data.get("status", "Active")),
            contacts_count=int(data.get("contacts_count", 0)),
            date=str(data.get("date", "Today")),
        )
