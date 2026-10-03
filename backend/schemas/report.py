from pydantic import BaseModel, Field
from typing import List, Dict, Any


class ReportSummarySchema(BaseModel):
    total: int = Field(0, description="Total calls matching filter")
    incoming: int = Field(0, description="Total incoming calls")
    outgoing: int = Field(0, description="Total outgoing calls")
    hot: int = Field(0, description="HOT lead count")
    warm: int = Field(0, description="WARM lead count")
    cold: int = Field(0, description="COLD lead count")
    incomplete: int = Field(0, description="Incomplete calls")
    demos_booked: int = Field(0, description="Booked demos count")
    total_duration_sec: int = Field(0, description="Total duration in seconds")
    avg_duration_sec: int = Field(0, description="Average duration in seconds")


class ReportResponseSchema(BaseModel):
    summary: ReportSummarySchema
    calls: List[Dict[str, Any]] = Field(default_factory=list)
