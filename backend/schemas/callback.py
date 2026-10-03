from pydantic import BaseModel, Field
from typing import Optional


class CallbackCreateSchema(BaseModel):
    phone: str = Field(..., description="Phone number for callback")
    language: Optional[str] = Field("English", description="Preferred language")
    callback_time: Optional[str] = Field(None, description="Requested callback time or notes")
    name: Optional[str] = Field(None, description="Contact name or label")


class CallbackDoneSchema(BaseModel):
    done: bool = Field(True, description="Mark as completed or pending")


class CallbackResponseSchema(BaseModel):
    id: Optional[int] = None
    time: str
    call_id: str
    direction: str
    phone: str
    language: str
    callback_time: str
    done: bool = False
