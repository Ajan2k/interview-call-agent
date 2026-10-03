import os
import logging
from typing import Optional, List, Dict, Any
from core.config import settings

logger = logging.getLogger("voice.prompts")

COMPANY_NAME = settings.COMPANY_NAME
AGENT_NAME = settings.AGENT_NAME
CALL_MODE = "interview"

LANG_MAP = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
}

NATIVE_LANG_NAMES = {
    "en-IN": ["english", "ஆங்கிலம்", "अंग्रेजी", "angrezi"],
    "hi-IN": ["hindi", "ஹிந்தி", "हिंदी"],
    "ta-IN": ["tamil", "தமிழ்", "தமில்", "tamizh"],
    "te-IN": ["telugu", "தெலுங்கு", "తెలుగు"],
    "kn-IN": ["kannada", "கன்னடம்", "ಕನ್ನಡ"],
    "ml-IN": ["malayalam", "மலையாளம்", "മലയാളം"],
}

SUPPORTED_LANGS = {"ta-IN", "ml-IN", "te-IN", "kn-IN", "hi-IN", "en-IN"}

FILLER_WORDS = {"जी", "हाँ जी", "ठीक है", "हुम", "हूँ", "कम", "ಹ್ಞೂ", "पोकम"}

WHISPER_LANG_MAP = {
    "ta": "ta-IN",
    "hi": "hi-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "en": "en-IN",
    "mr": "hi-IN",
}

FEW_SHOT = {
    "Tamil": (
        "Spoken Tamil / Tanglish conversational interview style:\n"
        "- வணக்கம்! Interview கு join பண்ணதுக்கு ரொம்ப நன்றி. நாம முதல் கேள்விக்கு போகலாமா?\n"
        "- Super! உங்க previous project ல பண்ண architecture decision பத்தி கொஞ்சம் explain பண்ணுங்க.\n"
    ),
    "Hindi": (
        "Spoken Hinglish conversational interview style:\n"
        "- Namaste! Interview join karne ke liye shukriya. Kya hum start karein?\n"
        "- Bohot badhiya. Apne past project ke architecture aur scaling challenges ke baare mein batayein.\n"
    ),
    "English": (
        "Professional yet warm, conversational technical interviewer style:\n"
        "- Hello! Thank you so much for joining today's interview. Are you ready to begin?\n"
        "- That's a great example. Could you walk me through the trade-offs you considered when choosing that architecture?\n"
    ),
    "Telugu": (
        "Spoken Telugu conversational interview style:\n"
        "- నమస్కారం! Interview కి join అయినందుకు ధన్యవాదాలు. Start చేద్దామా?\n"
    ),
    "Kannada": (
        "Spoken Kannada conversational interview style:\n"
        "- ನಮಸ್ಕಾರ! Interview ಗೆ join ಆಗಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. Start ಮಾಡೋಣವಾ?\n"
    ),
    "Malayalam": (
        "Spoken Malayalam conversational interview style:\n"
        "- നമസ്കാരം! Interview ൽ പങ്കെടുത്തതിന് വളരെ നന്ദി. നമുക്ക് ആരംഭിക്കാം?\n"
    ),
}

FALLBACK_MSGS = {
    "en-IN": "Sorry, I didn't quite catch that. Could you repeat?",
    "ta-IN": "மன்னிக்கவும், எனக்கு சரியா கேக்கல. இன்னொரு தடவை சொல்ல முடியுமா?",
    "hi-IN": "क्षमा करें, मुझे समझ नहीं आया। क्या आप दोहरा सकते हैं?",
    "te-IN": "క్షమించండి, నాకు అర్థం కాలేదు. దయచేసి మళ్లీ చెప్పగలరా?",
    "kn-IN": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
    "ml-IN": "ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?",
}

IDLE_NUDGE_MSGS = {
    "en-IN": "Hello, are you still there?",
    "ta-IN": "ஹலோ, லைன்ல இருக்கீங்களா?",
    "hi-IN": "हेलो, क्या आप सुन रहे हैं?",
    "te-IN": "హలో, వింటున్నారా?",
    "kn-IN": "ಹಲೋ, ಕೇಳಿಸ್ತಿದೆಯಾ?",
    "ml-IN": "ಹಲೋ, കേൾക്കുന്നുണ്ടോ?",
}

IDLE_GOODBYE_MSGS = {
    "en-IN": "Seems like you might be having audio issues. We'll reschedule this interview. Thank you!",
    "ta-IN": "ஆடியோ பிரச்சனை இருக்கு போல. நாம அப்புறமா reschedule பண்ணிக்கலாம். நன்றி!",
    "hi-IN": "लगता है ऑडियो में कोई समस्या है। हम बाद में reschedule करेंगे। धन्यवाद!",
    "te-IN": "ఆడియో సమస్య ఉన్నట్టుంది. తర్వాత reschedule చేద్దాం. ధన్యవాదాలు!",
    "kn-IN": "ಆಡಿಯೋ ಸಮಸ್ಯೆ ಇದೆ ಅನ್ಸುತ್ತೆ. ನಾವು ಆಮೇಲೆ reschedule ಮಾಡೋಣ. ಧನ್ಯವಾದಗಳು!",
    "ml-IN": "ഓഡിയോ പ്രശ്നമുണ്ടെന്ന് തോന്നുന്നു. നമുക്ക് പിന്നീട് റീഷെഡ്യൂൾ ചെയ്യാം. നന്ദി!",
}

TIMEUP_GOODBYE_MSGS = {
    "en-IN": "That concludes our allocated interview time today! Thank you so much for your insightful answers. Our hiring team will review everything and follow up soon. Have a great day!",
    "ta-IN": "நமது இன்டர்வியூ நேரம் முடிவடைந்தது! உங்கள் பதில்களுக்கு மிக்க நன்றி. எங்கள் அணி விரைவில் தொடர்புகொள்ளும். நன்றி, வணக்கம்!",
    "hi-IN": "आज का इंटरव्यू समय यहीं समाप्त होता है। आपके उत्तरों के लिए बहुत धन्यवाद। हमारी हायरिंग टीम जल्द संपर्क करेगी। धन्यवाद!",
    "te-IN": "ఇంటర్వ్యూ సమయం ముగిసింది! మీ సమాధానాలకు ధన్యవాదాలు. మా బృందం త్వరలో సంప్రదిస్తుంది!",
    "kn-IN": "ಇಂಟರ್ವ್ಯೂ ಸಮಯ ಮುಗಿದಿದೆ! ನಿಮ್ಮ ವಿವರವಾದ ಉತ್ತರಗಳಿಗೆ ಧನ್ಯವಾದಗಳು. ನಮ್ಮ ತಂಡ ಶೀಘ್ರದಲ್ಲೇ ಸಂಪರ್ಕಿಸುತ್ತದೆ!",
    "ml-IN": "ഇന്റർവ്യൂ സമയം അവസാനിച്ചു! പങ്കെടുത്തതിന് വളരെ നന്ദി. ഞങ്ങളുടെ ടീം ഉടൻ ബന്ധപ്പെടും!",
}


class PromptManager:
    """Manages conversation prompts, multilingual scripts, and autonomous interview flow prompts."""

    def __init__(self, company_name: str = COMPANY_NAME, agent_name: str = AGENT_NAME):
        self.company_name = company_name
        self.agent_name = agent_name

    def load_script_prompt(
        self, call_mode: str, lang_name: str, few_shot: str, base_dir: str | None = None
    ) -> str:
        """Load prompt template or provide standard interview prompt."""
        filename = "outbound_prompt.txt" if call_mode == "outbound" else "inbound_prompt.txt"

        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        prompts_dir = os.path.join(base_dir, "prompts")
        if not os.path.exists(os.path.join(prompts_dir, filename)):
            prompts_dir = os.path.join(base_dir, "Scripts")

        script_path = os.path.join(prompts_dir, filename)
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except Exception as e:
            logger.info(f"[SCRIPT] Reading {filename}: {e} — using standard interview prompt.")
            content = (
                f"You are {self.agent_name}, an expert AI Technical Interviewer from {self.company_name}. "
                "Conduct a professional, warm, and thorough technical and behavioral interview. "
                "Ask ONE question at a time. Listen carefully to the candidate's response. "
                "If the response is brief, ask a quick probing follow-up; otherwise acknowledge warmly and proceed to the next question. "
                "When all questions are answered or wrap-up is reached, politely conclude the interview and append [END_CALL].\n"
                "{few_shot}\nReply ONLY in {lang_name}. MAX 1-2 short sentences."
            )
        return content.replace("{lang_name}", lang_name).replace("{few_shot}", few_shot)

    def build_candidate_interview_prompt(
        self,
        candidate_name: str,
        position: str,
        questions: List[Dict[str, Any]],
        lang_name: str = "English",
    ) -> str:
        """Constructs an autonomous interview prompt incorporating candidate questions."""
        q_lines = []
        for q in questions:
            order = q.get("order", 1)
            cat = q.get("category", "technical").upper()
            comp = q.get("competency", "")
            text = q.get("text", "")
            q_lines.append(f"{order}. [{cat} - {comp}]: {text}")

        questions_block = "\n".join(q_lines)

        return (
            f"You are {self.agent_name}, a friendly, senior AI Technical Interviewer at {self.company_name}.\n"
            f"You are currently conducting an official voice interview with candidate: {candidate_name} for the position: '{position}'.\n\n"
            "INTERVIEW QUESTIONS ROADMAP:\n"
            f"{questions_block}\n\n"
            "CORE INTERVIEW RULES:\n"
            "1. You must ask ONE question at a time. Never ask multiple questions in a single reply.\n"
            "2. Listen actively to what the candidate says. If they answer well, give brief encouraging acknowledgement ('Great point', 'Understood', 'That makes sense') and ask the next question in the roadmap.\n"
            "3. If their answer is very short or vague, ask a single crisp follow-up to probe their depth before moving on.\n"
            "4. Keep your spoken responses CONCISE (1 to 2 sentences max) so the candidate speaks 80% of the time.\n"
            "5. After all questions have been addressed or the candidate wishes to conclude, warmly thank them for their time, explain that hiring team will follow up, and append [END_CALL].\n"
            f"6. Reply in {lang_name}."
        )

    def get_few_shot(self, lang_name: str) -> str:
        return FEW_SHOT.get(lang_name, FEW_SHOT["English"])

    def get_greeting(
        self,
        call_mode: str = "interview",
        candidate_name: str | None = None,
        position: str | None = None,
    ) -> str:
        c_name = candidate_name or "there"
        pos = position or "the position"
        return (
            f"Hello {c_name}! I'm {self.agent_name}, your AI interviewer from {self.company_name} for {pos}. "
            "Thank you for joining today's interview session! We'll go through a few behavioral and technical questions. "
            "Are you ready to begin?"
        )

    def get_fallback_message(self, lang_code: str) -> str:
        return FALLBACK_MSGS.get(lang_code, FALLBACK_MSGS["en-IN"])

    def get_idle_nudge(self, lang_code: str) -> str:
        return IDLE_NUDGE_MSGS.get(lang_code, IDLE_NUDGE_MSGS["en-IN"])

    def get_idle_goodbye(self, lang_code: str) -> str:
        return IDLE_GOODBYE_MSGS.get(lang_code, IDLE_GOODBYE_MSGS["en-IN"])

    def get_timeup_goodbye(self, lang_code: str) -> str:
        return TIMEUP_GOODBYE_MSGS.get(lang_code, TIMEUP_GOODBYE_MSGS["en-IN"])
