"""
Smart Daily Briefing for Shweta AI Desktop Assistant.
Personalized morning briefing — weather, date, reminders, crypto, fun fact.
Triggers on Windows startup (once per day) or on demand.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import PROJECT_ROOT, DEFAULT_CITY, GROQ_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# --- Settings ---
BRIEFING_USER_NAME = os.getenv("BRIEFING_USER_NAME", "Prathamesh")
BRIEFING_CITY = os.getenv("BRIEFING_CITY", DEFAULT_CITY or "Nashik")
BRIEFING_SHOW_CRYPTO = os.getenv("BRIEFING_SHOW_CRYPTO", "true").lower() == "true"
BRIEFING_SHOW_WEATHER = os.getenv("BRIEFING_SHOW_WEATHER", "true").lower() == "true"
BRIEFING_STARTUP_DELAY = int(os.getenv("BRIEFING_STARTUP_DELAY", "5"))

# State file
APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
STATE_DIR = APPDATA / "Shweta"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "briefing_state.json"

# Hindi days
HINDI_DAYS = ["Somwar", "Mangalwar", "Budhwar", "Guruwar", "Shukrawar", "Shaniwar", "Raviwar"]
HINDI_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


# --- Hardcoded Fun Facts (offline fallback, 30 facts) ---
HARDCODED_FACTS = [
    "Aur haan — Octopus ke teen dil hote hain aur khoon neela hota hai!",
    "Aur haan — Honey kabhi kharab nahi hota, 3000 saal purana honey bhi khaane layak hota hai!",
    "Aur haan — Ek din mein insaan average 48 baar apna phone check karta hai!",
    "Aur haan — Bananas technically berries hain lekin strawberries nahi hain scientifically!",
    "Aur haan — Ek insaan apni poori life mein 2 swimming pools bhar ke thook produce karta hai!",
    "Aur haan — Dolphins ek aankh khol ke sote hain taaki danger se bach sakein!",
    "Aur haan — Eiffel Tower garmi mein 15 cm lamba ho jaata hai iron expand hone ki wajah se!",
    "Aur haan — Teri body mein itna iron hai ki usse ek 3 inch ki nail ban sakti hai!",
    "Aur haan — Cows ke best friends hote hain aur wo alag hone pe stressed ho jaati hain!",
    "Aur haan — Ek average insaan apni life ka 6 mahina red lights pe wait karta hai!",
    "Aur haan — Sharks dinosaurs se bhi pehle se exist karte hain — 400 million years!",
    "Aur haan — Tera brain 80% paani hai — isliye dehydration se headache hota hai!",
    "Aur haan — Ek lightning bolt ka temperature sun ki surface se 5 guna zyada hota hai!",
    "Aur haan — Koalas din mein 22 ghante sote hain — meri dream life hai ye!",
    "Aur haan — Tera nose 1 trillion different smells detect kar sakta hai!",
    "Aur haan — Space mein astronauts 2 inch lambe ho jaate hain kyunki gravity nahi hoti!",
    "Aur haan — Ek average cloud ka weight 500,000 kg hota hai — haan sach mein!",
    "Aur haan — Butterflies apne pair se taste karte hain — weird but true!",
    "Aur haan — Tera heart ek din mein 100,000 baar beat karta hai!",
    "Aur haan — Venus pe ek din ek saal se bhi lamba hota hai!",
    "Aur haan — Ants kabhi sote nahi hain — 24/7 kaam karte hain bechare!",
    "Aur haan — Ek teaspoon neutron star ka weight 6 billion tons hota hai!",
    "Aur haan — Cats apni life ka 70% sote hue bitaati hain — goals hai ye!",
    "Aur haan — Tera DNA sun tak stretch kiya jaye toh 600 baar reach karega!",
    "Aur haan — Flamingos actually white hote hain, pink colour unke food se aata hai!",
    "Aur haan — Ek pencil se 35 miles lambi line draw ho sakti hai!",
    "Aur haan — Tera left lung right lung se chhota hota hai — dil ko jagah dene ke liye!",
    "Aur haan — Wombat ki potty cube shaped hoti hai — nature weird hai bhai!",
    "Aur haan — Ek insaan apni life mein average 25 saal so ke bitaata hai!",
    "Aur haan — Tera phone mein toilet seat se 10 guna zyada bacteria hote hain!",
]


# ============================================================
# Data Fetching Functions
# ============================================================

def fetch_weather(city: str) -> Optional[str]:
    """Fetch weather from wttr.in (free, no key). Returns Hinglish line or None."""
    if not BRIEFING_SHOW_WEATHER:
        return None
    try:
        url = f"https://wttr.in/{city}?format=j1"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        current = data.get("current_condition", [{}])[0]
        temp = current.get("temp_C", "?")
        desc = current.get("weatherDesc", [{}])[0].get("value", "").lower()

        # Map to Hinglish
        if "clear" in desc or "sunny" in desc:
            condition = "sunny rahega, dhoop nikli hai"
        elif "cloud" in desc or "overcast" in desc:
            condition = "thoda cloudy rahega"
        elif "rain" in desc or "drizzle" in desc:
            condition = "baarish ho sakti hai, umbrella rakh"
        elif "thunder" in desc:
            condition = "toofan aa sakta hai, ghar pe reh"
        elif "snow" in desc or "ice" in desc:
            condition = "thand bahut zyada hai aaj"
        elif "fog" in desc or "mist" in desc:
            condition = "fog hai bahar, dhyan se drive karna"
        elif "haze" in desc:
            condition = "haze hai, pollution zyada lag raha"
        else:
            condition = f"{desc}"

        return f"Aaj {city} mein {temp} degree hai aur {condition}."

    except requests.Timeout:
        logger.debug("[Briefing] Weather timeout.")
        return None
    except Exception as e:
        logger.debug(f"[Briefing] Weather failed: {e}")
        return None


def fetch_crypto() -> Optional[str]:
    """Fetch Bitcoin price from CoinGecko (free). Returns Hinglish line or None."""
    if not BRIEFING_SHOW_CRYPTO:
        return None
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=inr&include_24hr_change=true"
        resp = requests.get(url, timeout=4)
        if resp.status_code != 200:
            return None

        data = resp.json()
        btc = data.get("bitcoin", {})
        change = btc.get("inr_24h_change", 0)

        if change is None:
            return None

        change = round(change, 1)

        if change > 5:
            return f"Bitcoin aaj pump ho gaya yaar, {change}% upar!"
        elif change > 0:
            return f"Bitcoin aaj {change}% upar hai."
        elif change > -5:
            return f"Bitcoin aaj thoda neeche hai, {abs(change)}% gira."
        else:
            return f"Bitcoin aaj crash kar raha hai bhai, {abs(change)}% neeche!"

    except Exception as e:
        logger.debug(f"[Briefing] Crypto failed: {e}")
        return None


def fetch_fun_fact() -> str:
    """Get fun fact from AI or hardcoded pool."""
    # Check if we already have today's fact cached
    try:
        if STATE_FILE.exists():
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if state.get("fact_date") == str(date.today()) and state.get("fact"):
                return state["fact"]
    except Exception:
        pass

    # Try AI (Groq first)
    fact = _fetch_fact_from_ai()
    if fact:
        _save_fact_cache(fact)
        return fact

    # Fallback: hardcoded pool
    return random.choice(HARDCODED_FACTS)


def _fetch_fact_from_ai() -> Optional[str]:
    """Try to get fun fact from Groq/Gemini."""
    prompt = "Give me ONE interesting fun fact in exactly one Hinglish sentence. Start with 'Aur haan —'. Make it genuinely surprising and unique. No markdown. Just the single sentence."

    # Try Groq
    if GROQ_API_KEY:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.9, "max_tokens": 80},
                timeout=5
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip()
                if text and "Aur haan" in text:
                    return text[:150]
        except Exception:
            pass

    # Try Gemini
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite", contents=prompt,
                config=types.GenerateContentConfig(temperature=0.9, max_output_tokens=80)
            )
            text = response.text.strip()
            if text and len(text) > 10:
                if not text.startswith("Aur haan"):
                    text = "Aur haan — " + text
                return text[:150]
        except Exception:
            pass

    return None


def _save_fact_cache(fact: str) -> None:
    """Cache today's fun fact."""
    try:
        state = _load_state()
        state["fact_date"] = str(date.today())
        state["fact"] = fact
        _save_state(state)
    except Exception:
        pass


def fetch_reminders() -> List[Dict]:
    """Get today's reminders/notes from existing system."""
    try:
        from assistant.skills.notes import _load_notes
        notes = _load_notes()
        pending = [n for n in notes if not n.get("done")]
        return pending
    except Exception:
        return []


# ============================================================
# Briefing Script Builder
# ============================================================

def generate_briefing_script() -> str:
    """Generate the full briefing script. Fetches all data and builds natural Hinglish text."""
    user_name = BRIEFING_USER_NAME
    now = datetime.now()

    # Time-based greeting
    hour = now.hour
    if hour < 12:
        greeting = f"Good morning {user_name}!"
    elif hour < 17:
        greeting = f"Good afternoon {user_name}!"
    else:
        greeting = f"Good evening {user_name}!"

    sections = [greeting]

    # Weather
    weather = fetch_weather(BRIEFING_CITY)
    if weather:
        sections.append(weather)
    elif BRIEFING_SHOW_WEATHER:
        sections.append("Weather nahi pata abhi, internet slow hai shayad.")

    # Date & Day
    day_name = HINDI_DAYS[now.weekday()]
    date_line = f"Aaj {day_name} hai, {now.day} {HINDI_MONTHS[now.month]} {now.year}."
    sections.append(date_line)

    # Reminders
    reminders = fetch_reminders()
    if len(reminders) == 0:
        sections.append("Aaj koi pending kaam nahi hai — chill din hai!")
    elif len(reminders) == 1:
        sections.append(f"Tere paas ek pending kaam hai — {reminders[0].get('text', 'kuch hai')}.")
    elif len(reminders) <= 3:
        items = ", ".join(r.get("text", "")[:30] for r in reminders[:3])
        sections.append(f"Tere paas {len(reminders)} pending kaam hain — {items}.")
    else:
        sections.append(f"Aaj tera schedule tight hai bhai — {len(reminders)} kaam pending hain!")

    # Crypto
    crypto = fetch_crypto()
    if crypto:
        sections.append(crypto)

    # Fun fact
    fun_fact = fetch_fun_fact()
    if fun_fact:
        sections.append(fun_fact)

    # Personality closer
    if len(reminders) == 0:
        closer = f"Aaj chill din hai tera {user_name} — enjoy kar!"
    elif len(reminders) <= 2:
        closer = f"Thoda kaam hai aaj — ho jaayega easily! Acha din ho."
    else:
        closer = f"Busy day hai aaj — ek ek karke nipata! All the best."

    sections.append(closer)

    return " ".join(sections)


# ============================================================
# State Management (track if already briefed today)
# ============================================================

def _load_state() -> Dict:
    """Load briefing state from file."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: Dict) -> None:
    """Save briefing state to file."""
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[Briefing] State save failed: {e}")


def should_brief_today() -> bool:
    """Check if we should deliver briefing today (not yet briefed)."""
    state = _load_state()
    last_date = state.get("last_briefed_date", "")
    return last_date != str(date.today())


def mark_briefed_today() -> None:
    """Mark that briefing was delivered today."""
    state = _load_state()
    state["last_briefed_date"] = str(date.today())
    _save_state(state)


def reset_briefing_state() -> None:
    """Reset state (for testing — allows re-triggering briefing)."""
    state = _load_state()
    state.pop("last_briefed_date", None)
    _save_state(state)


def is_briefing_time() -> bool:
    """Check if current time is within briefing window (6AM-10AM)."""
    hour = datetime.now().hour
    return 6 <= hour <= 10


# ============================================================
# Main Briefing Trigger (called from main.py or scheduler)
# ============================================================

class DailyBriefingManager:
    """Manages daily briefing delivery."""

    def __init__(self, speak_fn=None, set_emotion_fn=None, show_bubble_fn=None):
        self._speak = speak_fn
        self._set_emotion = set_emotion_fn
        self._show_bubble = show_bubble_fn
        self._is_delivering = False

    def set_callbacks(self, speak_fn, set_emotion_fn=None, show_bubble_fn=None):
        """Set callback functions (from main.py after init)."""
        self._speak = speak_fn
        self._set_emotion = set_emotion_fn
        self._show_bubble = show_bubble_fn

    def try_auto_briefing(self) -> bool:
        """Try to deliver auto briefing (startup trigger). Returns True if delivered."""
        if not should_brief_today():
            return False
        if not is_briefing_time():
            return False
        self.deliver()
        return True

    def deliver(self) -> None:
        """Generate and deliver the briefing."""
        if self._is_delivering:
            return

        self._is_delivering = True
        logger.info("[Briefing] Generating daily briefing...")

        try:
            script = generate_briefing_script()
            logger.info(f"[Briefing] Script: {script[:100]}...")

            # Set happy emotion
            if self._set_emotion:
                try:
                    self._set_emotion("happy", 0.8)
                except Exception:
                    pass

            # Show in chat bubble
            if self._show_bubble:
                try:
                    self._show_bubble(script[:120], 8.0)
                except Exception:
                    pass

            # Speak it
            if self._speak:
                self._speak(script)

            # Mark as done
            mark_briefed_today()
            logger.info("[Briefing] Delivered successfully.")

        except Exception as e:
            logger.error(f"[Briefing] Delivery failed: {e}")
        finally:
            self._is_delivering = False

    def deliver_on_demand(self) -> Dict[str, str]:
        """Deliver briefing on demand (user asked). Returns result dict."""
        try:
            script = generate_briefing_script()

            if self._set_emotion:
                try:
                    self._set_emotion("happy", 0.8)
                except Exception:
                    pass

            return {"status": "success", "message": script}
        except Exception as e:
            return {"status": "error", "message": f"Briefing generate nahi ho paya: {e}"}
