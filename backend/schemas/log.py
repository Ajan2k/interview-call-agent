from pydantic import BaseModel
from typing import Optional


class LogEntrySchema(BaseModel):
    id: str
    timestamp: Optional[str] = ""
    message: str
