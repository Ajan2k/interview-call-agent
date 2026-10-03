from pydantic import BaseModel, Field
from typing import Optional


class ContactCreateSchema(BaseModel):
    name: str = Field(..., description="Contact's full name")
    phone: str = Field(..., description="Phone number with country code")
    status: Optional[str] = Field("Pending", description="Call status")
    notes: Optional[str] = Field("", description="Additional notes")
    isIncoming: Optional[bool] = Field(False, description="Whether contact called in")
    lastCalled: Optional[str] = Field("Never", description="Timestamp of last call")
    campaignId: Optional[str] = Field(None, description="Associated campaign ID")


class ContactUpdateSchema(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    isIncoming: Optional[bool] = None
    lastCalled: Optional[str] = None
    campaignId: Optional[str] = None


class ContactResponseSchema(BaseModel):
    id: str
    name: str
    phone: str
    status: str = "Pending"
    lastCalled: Optional[str] = "Never"
    notes: Optional[str] = ""
    isIncoming: Optional[bool] = False
