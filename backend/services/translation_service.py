import os
import httpx
from typing import Dict, Any


class TranslationService:
    """Class-based service for language translation via Sarvam AI API."""

    SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"

    def __init__(self, api_key: str = None):
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        return self._api_key or os.getenv("SARVAM_API_KEY", "")

    def translate(
        self,
        text: str,
        source_language_code: str = "auto",
        target_language_code: str = "en-IN",
    ) -> Dict[str, Any]:
        """Translates text from source language to target language.
        Returns original text if empty or if same language."""
        text = (text or "").strip()
        source = source_language_code or "auto"
        target = target_language_code or "en-IN"

        if not text:
            return {"translated": "", "source": source}

        # Already in the target language (e.g. en-IN → en-IN)
        if source != "auto" and source.split("-")[0] == target.split("-")[0]:
            return {"translated": text, "source": source, "same_language": True}

        key = self.api_key
        if not key:
            return {"translated": text, "source": source, "error": "No SARVAM_API_KEY"}

        try:
            res = httpx.post(
                self.SARVAM_TRANSLATE_URL,
                headers={"api-subscription-key": key, "Content-Type": "application/json"},
                json={
                    "input": text,
                    "source_language_code": source,
                    "target_language_code": target,
                    "mode": "formal",
                },
                timeout=15.0,
            )
            if res.status_code == 200:
                j = res.json()
                return {
                    "translated": j.get("translated_text", text),
                    "source": j.get("source_language_code", source),
                }
            return {"translated": text, "source": source, "error": f"Sarvam {res.status_code}"}
        except Exception as e:
            return {"translated": text, "source": source, "error": str(e)}
