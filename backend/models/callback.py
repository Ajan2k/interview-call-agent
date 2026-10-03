from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Callback:
    time: str
    call_id: str
    direction: str
    phone: str
    language: str
    callback_time: str
    done: bool = False
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "time": self.time,
            "call_id": self.call_id,
            "direction": self.direction,
            "phone": self.phone,
            "language": self.language,
            "callback_time": self.callback_time,
            "done": self.done,
        }
        if self.id is not None:
            data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Callback":
        return cls(
            time=str(data.get("time", "")),
            call_id=str(data.get("call_id", "")),
            direction=str(data.get("direction", "")),
            phone=str(data.get("phone", "")),
            language=str(data.get("language", "")),
            callback_time=str(data.get("callback_time", "")),
            done=bool(data.get("done", False)),
            id=int(data["id"]) if "id" in data and data["id"] is not None else None,
        )
