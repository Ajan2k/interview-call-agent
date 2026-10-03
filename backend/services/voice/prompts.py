import os
import logging

logger = logging.getLogger("voice.prompts")

COMPANY_NAME = "Daffytel Technologies"
AGENT_NAME = "caffy"
CALL_MODE = "outbound"

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
    "mr": "hi-IN",  # Marathi -> treat as Hindi
}

FEW_SHOT = {
    "Tamil": (
        "Daffy's natural spoken TANGLISH style (Tamil script + everyday English words, exactly how people actually talk on the phone):\n"
        "- சரிங்க! உங்க business ல daily எவ்வளோ calls வரும்?\n"
        "- ஓ அப்படியா! Night ல வர்ற calls எல்லாம் miss ஆகுதா? எங்க AI agent 24/7 எல்லா calls யும் attend பண்ணிடும்.\n"
        "- Super! உங்களுக்கு ஒரு free demo arrange பண்ணிடுறேன் — எந்த day, என்ன time convenient ஆ இருக்கும்?\n"
    ),
    "Hindi": (
        "Daffy's natural Hinglish style — short, warm, colloquial:\n"
        "- Bilkul samajh gaya! Din mein roughly kitne calls aate hain?\n"
        "- Raat ke calls miss ho jaate hain? Hamara AI agent 24/7 saare calls attend karta hai.\n"
    ),
    "English": (
        "Daffy's natural English style — warm, casual, NOT robotic:\n"
        "- Oh gotcha! And roughly how many calls do you get in a day?\n"
        "- Got it — so after-hours calls just go unanswered? Our AI agent attends every single call, 24/7.\n"
    ),
    "Telugu": (
        "Daffy's natural spoken Telugu style (Telugu script + everyday English words, exactly how people talk):\n"
        "- సరే sir! మీ business కి daily ఎన్ని calls వస్తాయి?\n"
        "- ఓ అలాగా! Night లో వచ్చే calls అన్నీ miss అవుతున్నాయా? మా AI agent 24/7 అన్ని calls attend చేస్తుంది.\n"
    ),
    "Kannada": (
        "Daffy's natural spoken Kannada style (Kannada script + everyday English words, exactly how people talk):\n"
        "- ಸರಿ sir! ನಿಮ್ಮ business ಗೆ daily ಎಷ್ಟು calls ಬರುತ್ತವೆ?\n"
        "- ಓ ಹೌದಾ! Night ಲಿ ಬರುವ calls ಎಲ್ಲಾ miss ಆಗ್ತಿವೆಯಾ? ನಮ್ಮ AI agent 24/7 ಎಲ್ಲಾ calls attend ಮಾಡುತ್ತೆ.\n"
    ),
    "Malayalam": (
        "Daffy's natural spoken Malayalam style (Malayalam script + everyday English words, exactly how people talk):\n"
        "- ശരി sir! നിങ്ങളുടെ business ൽ daily എത്ര calls വരും?\n"
        "- ഓ അങ്ങനെയാണോ! Night ൽ വരുന്ന calls എല്ലാം miss ആകുന്നുണ്ടോ? ഞങ്ങളുടെ AI agent 24/7 എല്ലാ calls ഉം attend ചെയ്യും.\n"
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
    "ml-IN": "ഹലോ, കേൾക്കുന്നുണ്ടോ?",
}

IDLE_GOODBYE_MSGS = {
    "en-IN": "Seems like this isn't a good time. I'll call back later. Thank you, bye!",
    "ta-IN": "நீங்க பிசியா இருக்கீங்க போல. நான் அப்புறமா கால் பண்றேன். நன்றி, வணக்கம்!",
    "hi-IN": "लगता है आप अभी व्यस्त हैं। मैं बाद में कॉल करती हूँ। धन्यवाद, नमस्ते!",
    "te-IN": "మీరు బిజీగా ఉన్నట్టున్నారు. నేను తర్వాత కాల్ చేస్తాను. ధన్యవాదాలు!",
    "kn-IN": "ನೀವು ಬ್ಯುಸಿ ಇದ್ದೀರಾ ಅನ್ಸುತ್ತೆ. ನಾನು ಆಮೇಲೆ ಕಾಲ್ ಮಾಡ್ತೀನಿ. ಧನ್ಯವಾದಗಳು!",
    "ml-IN": "നിങ്ങൾ തിരക്കിലാണെന്ന് തോന്നുന്നു. ഞാൻ പിന്നീട് വിളിക്കാം. നന്ദി!",
}

TIMEUP_GOODBYE_MSGS = {
    "en-IN": "I don't want to take more of your time. Our team will follow up with the details. Thanks a lot, bye!",
    "ta-IN": "உங்க நேரத்தை அதிகமா எடுத்துக்க விரும்பல. மீதி விவரங்களை எங்க டீம் ஷேர் பண்ணும். ரொம்ப நன்றி, வணக்கம்!",
    "hi-IN": "मैं आपका ज़्यादा समय नहीं लेना चाहती। बाकी जानकारी हमारी टीम भेज देगी। धन्यवाद, नमस्ते!",
    "te-IN": "మీ సమయం ఎక్కువ తీసుకోవడం ఇష్టం లేదు. మిగతా వివరాలు మా టీమ్ పంపుతుంది. ధన్యవాదాలు!",
    "kn-IN": "ನಿಮ್ಮ ಹೆಚ್ಚು ಸಮಯ ತೆಗೆದುಕೊಳ್ಳಲು ಇಷ್ಟವಿಲ್ಲ. ಉಳಿದ ವಿವರಗಳನ್ನು ನಮ್ಮ ತಂಡ ಕಳುಹಿಸುತ್ತದೆ. ಧನ್ಯವಾದಗಳು!",
    "ml-IN": "നിങ്ങളുടെ കൂടുതൽ സമയം എടുക്കാൻ ആഗ്രഹിക്കുന്നില്ല. ബാക്കി വിവരങ്ങൾ ഞങ്ങളുടെ ടീം അയയ്ക്കും. നന്ദി!",
}


class PromptManager:
    """Manages conversation prompts, multilingual scripts, and predefined dialog nudges."""

    def __init__(self, company_name: str = COMPANY_NAME, agent_name: str = AGENT_NAME):
        self.company_name = company_name
        self.agent_name = agent_name

    def load_script_prompt(
        self, call_mode: str, lang_name: str, few_shot: str, base_dir: str | None = None
    ) -> str:
        """Load the sales script for this call mode from prompts/ (or fallback Scripts/),
        filling in {lang_name} and {few_shot} placeholders."""
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
            logger.error(f"[SCRIPT] Failed to read {filename}: {e} — using minimal fallback prompt.")
            content = (
                f"You are {self.agent_name}, a friendly human-sounding salesperson from {self.company_name} selling an"
                " AI Calling Agent that attends business calls 24/7. Ask ONE short question at a time,"
                " book a free demo, and append [END_CALL] with a [LEAD: status=...] tag in your final goodbye reply.\n"
                "{few_shot}\nReply ONLY in {lang_name}. MAX 1-2 short sentences."
            )
        return content.replace("{lang_name}", lang_name).replace("{few_shot}", few_shot)

    def get_few_shot(self, lang_name: str) -> str:
        return FEW_SHOT.get(lang_name, FEW_SHOT["English"])

    def get_greeting(self, call_mode: str) -> str:
        if call_mode == "outbound":
            return (
                f"Hello! I'm {self.agent_name.capitalize()}, calling from {self.company_name}. "
                "We help businesses attend every customer call 24/7 with our AI calling agent. "
                "May I know who I'm speaking with?"
            )
        return f"Hello! Thanks for calling {self.company_name}, I'm {self.agent_name.capitalize()}. How can I help you today?"

    def get_fallback_message(self, lang_code: str) -> str:
        return FALLBACK_MSGS.get(lang_code, FALLBACK_MSGS["en-IN"])

    def get_idle_nudge(self, lang_code: str) -> str:
        return IDLE_NUDGE_MSGS.get(lang_code, IDLE_NUDGE_MSGS["en-IN"])

    def get_idle_goodbye(self, lang_code: str) -> str:
        return IDLE_GOODBYE_MSGS.get(lang_code, IDLE_GOODBYE_MSGS["en-IN"])

    def get_timeup_goodbye(self, lang_code: str) -> str:
        return TIMEUP_GOODBYE_MSGS.get(lang_code, TIMEUP_GOODBYE_MSGS["en-IN"])
