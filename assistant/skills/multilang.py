"""
Multi-language Support + Auto-Detection + Voice Selection for Shweta.
Supports: Hindi, English, Marathi, Hinglish.
Auto-detects user language and responds in same language.
"""

import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Edge TTS voices per language
VOICES = {
    "hindi": {"voice": "hi-IN-SwaraNeural", "code": "hi-IN", "name": "Hindi"},
    "hinglish": {"voice": "en-IN-NeerjaNeural", "code": "en-IN", "name": "Hinglish"},
    "english": {"voice": "en-IN-NeerjaNeural", "code": "en-IN", "name": "English"},
    "marathi": {"voice": "mr-IN-AarohiNeural", "code": "mr-IN", "name": "Marathi"},
    "tamil": {"voice": "ta-IN-PallaviNeural", "code": "ta-IN", "name": "Tamil"},
    "telugu": {"voice": "te-IN-ShrutiNeural", "code": "te-IN", "name": "Telugu"},
}

# AI language instructions (appended to system prompt dynamically)
LANG_PROMPTS = {
    "hindi": "User is speaking Hindi. Reply in Hindi (Devanagari script). Be natural and friendly.",
    "hinglish": "User is speaking Hinglish. Reply in Hinglish (Hindi words in Roman/English script). Mix Hindi-English naturally.",
    "english": "User is speaking English. Reply in simple, friendly English.",
    "marathi": "User is speaking Marathi. Reply in Marathi (Devanagari script). Use casual friendly Marathi like a young Maharashtrian friend.",
    "tamil": "User is speaking Tamil. Reply in Tamil script. Use casual Tamil.",
    "telugu": "User is speaking Telugu. Reply in Telugu script. Use casual Telugu.",
}

# --- Language Detection Patterns ---

# Devanagari Unicode range
_DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')

# Marathi-specific Devanagari words (NOT shared with Hindi)
_MARATHI_DEVANAGARI = [
    "काय", "आहे", "नाही", "करा", "सांग", "बोल", "चल", "कर",
    "मला", "तुला", "त्याला", "तिला", "आम्ही", "तुम्ही",
    "कसं", "कुठे", "केव्हा", "कोण", "काही", "असं", "तसं",
    "बरं", "चांगलं", "वाईट", "मोठं", "लहान",
    "आणि", "पण", "म्हणून", "तर", "जर", "की",
    "गाणं", "लाव", "सांगा", "बघ",
    "चाललंय", "झालं", "होतं", "आलं", "गेलं", "केलं",
    "अरे",
]

# Hindi-specific words (Devanagari context)
_HINDI_WORDS = [
    "है", "हूँ", "हैं", "था", "थी", "थे", "हो", "होगा",
    "क्या", "कैसे", "कहाँ", "कब", "कौन", "क्यों",
    "मुझे", "तुम्हें", "उसे", "हमें", "आपको",
    "करो", "बताओ", "सुनो", "देखो", "चलो",
    "अच्छा", "बुरा", "ठीक", "सही", "गलत",
]

# Hinglish indicators (Roman script Hindi words)
_HINGLISH_WORDS = [
    "kya", "kaise", "kahan", "kab", "kaun", "kyun", "kyu",
    "mujhe", "tumhe", "usse", "hume", "aapko",
    "karo", "batao", "suno", "dekho", "chalo", "bolo",
    "accha", "theek", "sahi", "galat", "bahut", "bohot",
    "hai", "hoon", "hain", "tha", "thi", "the",
    "nahi", "haan", "ji", "yaar", "bhai", "dost",
    "abhi", "phir", "lekin", "aur", "ya", "toh",
    "mera", "tera", "uska", "hamara", "tumhara",
    "kuch", "sab", "koi", "kahin", "kabhi",
    "raha", "rahi", "rahe", "wala", "wali", "wale",
    "kar", "de", "le", "ja", "aa", "sun",
    "dukh", "khushi", "gussa", "pyaar", "dard",
    "gana", "bajao", "kholo", "band", "chalu",
]

# Marathi Roman script words
_MARATHI_ROMAN = [
    "kay", "aahe", "nahi", "kara", "sang", "bol", "mala", "tula",
    "kasa", "kuthe", "kevha", "kon", "kahi", "asa", "tasa",
    "bara", "changla", "vait", "motha", "lahan", "pan", "ani",
    "tumhi", "amhi", "tyala", "tila", "he", "te", "ti",
    "challay", "zala", "hota", "ala", "gela", "kela",
]

# Pure English indicators
_ENGLISH_WORDS = [
    "the", "is", "are", "was", "were", "have", "has", "had",
    "what", "how", "where", "when", "who", "why", "which",
    "please", "thank", "sorry", "hello", "okay", "sure",
    "can", "could", "would", "should", "will", "shall",
    "this", "that", "these", "those", "here", "there",
    "want", "need", "like", "know", "think", "feel",
    "open", "close", "play", "stop", "start", "search",
    "tell", "show", "give", "make", "take", "find",
]


def detect_language(text: str) -> str:
    """
    Auto-detect language from user input text.
    Returns: 'hindi', 'english', 'marathi', or 'hinglish'
    """
    if not text or not text.strip():
        return "hinglish"

    text_stripped = text.strip()

    # Check for Devanagari script
    devanagari_chars = len(_DEVANAGARI_RE.findall(text_stripped))
    total_alpha = sum(1 for c in text_stripped if c.isalpha())

    if total_alpha == 0:
        return "hinglish"

    devanagari_ratio = devanagari_chars / total_alpha if total_alpha > 0 else 0

    # If mostly Devanagari -> Hindi or Marathi
    if devanagari_ratio > 0.5:
        marathi_score = sum(1 for w in _MARATHI_DEVANAGARI if w in text_stripped)
        hindi_score = sum(1 for w in _HINDI_WORDS if w in text_stripped)

        if marathi_score >= 1 and marathi_score >= hindi_score:
            return "marathi"
        elif hindi_score > marathi_score:
            return "hindi"
        elif marathi_score >= 1:
            return "marathi"
        else:
            return "hindi"

    # Roman script — distinguish English vs Hinglish vs Romanized Marathi
    text_lower = text_stripped.lower()
    words = re.findall(r'[a-zA-Z]+', text_lower)

    if not words:
        return "hinglish"

    total_words = len(words)
    hinglish_count = sum(1 for w in words if w in _HINGLISH_WORDS)
    english_count = sum(1 for w in words if w in _ENGLISH_WORDS)
    marathi_count = sum(1 for w in words if w in _MARATHI_ROMAN)

    hinglish_ratio = hinglish_count / total_words
    english_ratio = english_count / total_words
    marathi_ratio = marathi_count / total_words

    if marathi_ratio > 0.3 and marathi_ratio >= hinglish_ratio:
        return "marathi"
    elif hinglish_ratio > 0.3 and hinglish_ratio > english_ratio:
        return "hinglish"
    elif english_ratio > 0.4 and english_ratio > hinglish_ratio:
        return "english"
    elif hinglish_count > english_count:
        return "hinglish"
    elif english_count > 0 and hinglish_count == 0:
        return "english"
    else:
        return "hinglish"


class LanguageManager:
    """Manages language switching for voice + AI responses."""

    def __init__(self) -> None:
        self.current_lang: str = "hinglish"
        self._auto_mode: bool = True

    def set_language(self, lang: str) -> Dict[str, str]:
        """Manually switch language (disables auto-detect)."""
        lang = lang.lower().strip()
        aliases = {
            "hindi": "hindi", "marathi": "marathi", "tamil": "tamil",
            "telugu": "telugu", "english": "english", "hinglish": "hinglish",
            "auto": "auto",
        }
        lang = aliases.get(lang, lang)

        if lang == "auto":
            self._auto_mode = True
            return {"status": "success", "message": "Auto language detection ON!"}

        if lang in VOICES:
            self.current_lang = lang
            self._auto_mode = False
            name = VOICES[lang]["name"]
            logger.info(f"Language manually set to: {name}")
            return {"status": "success", "message": f"Language {name} mein switch kar diya!"}
        else:
            available = ", ".join(VOICES.keys())
            return {"status": "error", "message": f"Language nahi mili. Available: {available}"}

    def detect_and_set(self, user_text: str) -> str:
        """Auto-detect language from user input and update current_lang."""
        if not self._auto_mode:
            return self.current_lang

        detected = detect_language(user_text)
        if detected != self.current_lang:
            logger.info(f"Language auto-switched: {self.current_lang} -> {detected}")
            self.current_lang = detected
        return detected

    def get_voice(self) -> str:
        """Get current Edge TTS voice name."""
        return VOICES.get(self.current_lang, VOICES["hinglish"])["voice"]

    def get_lang_code(self) -> str:
        """Get language code for STT."""
        return VOICES.get(self.current_lang, VOICES["hinglish"])["code"]

    def get_ai_prompt(self) -> str:
        """Get language instruction for AI."""
        return LANG_PROMPTS.get(self.current_lang, LANG_PROMPTS["hinglish"])

    def get_current(self) -> str:
        return self.current_lang

    def is_auto(self) -> bool:
        return self._auto_mode
