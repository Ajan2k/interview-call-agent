from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class CallTranscriptItemSchema(BaseModel):
    role: str = Field(..., description="Role of the speaker (caller, agent, system)")
    text: str = Field(..., description="Spoken message text")
    lang: Optional[str] = Field("en-IN", description="Language code")
    time: Optional[str] = Field("", description="Timestamp of message")


class CallResponseSchema(BaseModel):
    id: str
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_position: Optional[str] = None
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


class CallTranscriptResponseSchema(BaseModel):
    found: bool
    phone: Optional[str] = ""
    direction: Optional[str] = ""
    start: Optional[str] = ""
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
    transcript: List[Dict[str, Any]] = Field(default_factory=list)
