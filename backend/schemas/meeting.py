from pydantic import BaseModel, Field
from typing import Optional


class MeetingResponseSchema(BaseModel):
    time: str = Field(..., description="Timestamp of meeting booking")
    call_id: str = Field(..., description="Call identifier")
    direction: str = Field(..., description="Call direction (incoming/outgoing)")
    phone: str = Field(..., description="Caller/client phone number")
    language: str = Field(..., description="Language of call")
    details: str = Field(..., description="Booked meeting details/slot")
    id: Optional[int] = None
