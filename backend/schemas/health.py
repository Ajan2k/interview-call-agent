from pydantic import BaseModel
from typing import Dict, Any


class HealthResponseSchema(BaseModel):
    status: str
    hasApiKey: bool
    databaseConnected: bool
    databaseType: str
    services: Dict[str, str]
