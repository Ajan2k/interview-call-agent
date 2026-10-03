from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any


class VoiceConfigSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    speechMode: Optional[str] = Field(None, description="TTS voice speech mode")
    languageFocus: Optional[str] = Field(None, description="Primary language focus")
    promptTemplate: Optional[str] = Field(None, description="System prompt template")
