from fastapi import APIRouter, Body
from typing import Dict, Any
from services.translation_service import TranslationService
from schemas.translate import TranslateRequestSchema, TranslateResponseSchema

router = APIRouter(prefix="/translate", tags=["Translate"])

_translation_service = TranslationService()


@router.post("", response_model=TranslateResponseSchema)
def translate_text(body: Dict[str, Any] = Body(...)):
    """Translate a chat message using Sarvam Translation Service."""
    text = body.get("text", "")
    source = body.get("source_language_code") or "auto"
    target = body.get("target_language_code") or "en-IN"
    return _translation_service.translate(
        text=text,
        source_language_code=source,
        target_language_code=target,
    )
