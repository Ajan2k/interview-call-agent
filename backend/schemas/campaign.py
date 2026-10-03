from pydantic import BaseModel, Field
from typing import Optional


class CampaignCreateSchema(BaseModel):
    name: str = Field(..., description="Campaign name")
    status: Optional[str] = Field("Active", description="Campaign status")
    contacts_count: Optional[int] = Field(0, description="Total contacts count")
    date: Optional[str] = Field("Today", description="Date created")


class CampaignResponseSchema(BaseModel):
    id: str
    name: str
    status: str = "Active"
    contacts_count: int = 0
    date: str = "Today"
