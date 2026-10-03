from pydantic import BaseModel, Field
from typing import Optional


class TranslateRequestSchema(BaseModel):
    text: str = Field(..., description="Text to translate")
    source_language_code: Optional[str] = Field("auto", description="Source BCP-47 language code")
    target_language_code: Optional[str] = Field("en-IN", description="Target BCP-47 language code")


class TranslateResponseSchema(BaseModel):
    translated: str
    source: Optional[str] = None
    same_language: Optional[bool] = None
    error: Optional[str] = None
