from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class VoiceConfig:
    speech_mode: str = "Natural Female Voice (Azure Neerja / Pallavi)"
    language_focus: str = "Automatic Multi-language (Tamil, Hindi, English)"
    prompt_template: str = (
        "You are Daffy, a warm AI Sales Consultant calling from Daffytel Technologies..."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speechMode": self.speech_mode,
            "languageFocus": self.language_focus,
            "promptTemplate": self.prompt_template,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceConfig":
        return cls(
            speech_mode=str(data.get("speechMode") or data.get("speech_mode", "")),
            language_focus=str(data.get("languageFocus") or data.get("language_focus", "")),
            prompt_template=str(data.get("promptTemplate") or data.get("prompt_template", "")),
        )
