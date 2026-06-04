"""
Personality Modes + Conversation Memory + Health Reminders for Shweta.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

MEMORY_FILE = PROJECT_ROOT / "user_memory.json"

# --- PERSONALITY MODES ---

MODES = {
    "fun": {
        "name": "Fun Mode",
        "prompt": "You are playful, cheerful, use jokes, casual Hinglish, emojis in text. Sound like a fun young friend."
    },
    "professional": {
        "name": "Professional Mode",
        "prompt": "You are formal, concise, task-focused. No jokes, no slang. Give direct answers only. Sound like a professional assistant."
    },
    "study": {
        "name": "Study Mode",
        "prompt": "You are focused and minimal. Keep responses very short. No casual chat. Help user stay productive. Encourage focus."
    },
}


class PersonalityManager:
    """Manages personality modes for Shweta."""

    def __init__(self, memory_store: Optional["MemoryStore"] = None) -> None:
        self._memory_store = memory_store
        self.current_mode: str = "fun"

        # Restore persisted mode from MemoryStore if available
        if self._memory_store is not None:
            persisted_mode = self._memory_store.get("personality_mode", "")
            if persisted_mode and persisted_mode in MODES:
                self.current_mode = persisted_mode
                logger.info(f"Personality mode restored from memory: {self.current_mode}")

    def set_mode(self, mode: str) -> Dict[str, str]:
        mode = mode.lower().strip()
        if mode in MODES:
            self.current_mode = mode
            # Persist mode to MemoryStore
            if self._memory_store is not None:
                self._memory_store.set("personality_mode", mode)
            return {"status": "success", "message": f"{MODES[mode]['name']} activate ho gaya!"}
        return {"status": "error", "message": f"Mode '{mode}' nahi mila. Options: fun, professional, study"}

    def get_prompt(self) -> str:
        return MODES.get(self.current_mode, MODES["fun"])["prompt"]

    def get_mode_name(self) -> str:
        return MODES.get(self.current_mode, MODES["fun"])["name"]


# --- CONVERSATION MEMORY ---

class MemoryStore:
    """Persistent user preference storage."""

    def __init__(self) -> None:
        self.data: Dict[str, any] = {
            "name": "",
            "city": "",
            "favorite_songs": [],
            "preferred_language": "hinglish",
        }
        self._load()

    def _load(self) -> None:
        if MEMORY_FILE.exists():
            try:
                self.data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                logger.info(f"Memory loaded: {self.data}")
            except Exception:
                pass

    def _save(self) -> None:
        try:
            MEMORY_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Memory save failed: {e}")

    def set(self, key: str, value) -> Dict[str, str]:
        if key == "favorite_songs":
            if isinstance(self.data.get("favorite_songs"), list):
                if value not in self.data["favorite_songs"]:
                    self.data["favorite_songs"].append(value)
            else:
                self.data["favorite_songs"] = [value]
        else:
            self.data[key] = value
        self._save()
        return {"status": "success", "message": f"Yaad rakh liya: {key} = {value}"}

    def get(self, key: str, default=""):
        return self.data.get(key, default)

    def get_prompt_context(self) -> str:
        """Get memory as context string for AI prompt."""
        parts = []
        if self.data.get("name"):
            parts.append(f"User ka naam: {self.data['name']}")
        if self.data.get("city"):
            parts.append(f"User ki city: {self.data['city']}")
        if self.data.get("favorite_songs"):
            songs = ", ".join(self.data["favorite_songs"][:5])
            parts.append(f"Favorite songs: {songs}")
        if self.data.get("preferred_language"):
            parts.append(f"Preferred language: {self.data['preferred_language']}")
        return "\n".join(parts) if parts else ""

    def remember(self, key: str, value: str) -> Dict[str, str]:
        return self.set(key, value)

    def get_all(self) -> Dict[str, str]:
        return {"status": "success", "message": json.dumps(self.data, ensure_ascii=False)}


# --- HEALTH REMINDERS ---

class HealthReminders:
    """Automatic health reminders — water, eye rest, breaks."""

    def __init__(self, speak_fn: Optional[Callable] = None) -> None:
        self.speak = speak_fn
        self.enabled: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> Dict[str, str]:
        if self.enabled:
            return {"status": "success", "message": "Health reminders already on hain."}
        self.enabled = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self._thread.start()
        logger.info("Health reminders started.")
        return {"status": "success", "message": "Health reminders on! Paani, eye rest, break yaad dilaaungi."}

    def stop(self) -> Dict[str, str]:
        self.enabled = False
        self._stop_event.set()
        logger.info("Health reminders stopped.")
        return {"status": "success", "message": "Health reminders off kar diye."}

    def _reminder_loop(self) -> None:
        """Background loop — checks every minute."""
        water_interval = 30 * 60      # 30 min
        eye_interval = 20 * 60        # 20 min
        break_interval = 60 * 60      # 60 min

        last_water = time.time()
        last_eye = time.time()
        last_break = time.time()

        while not self._stop_event.is_set():
            self._stop_event.wait(60)  # Check every 60 seconds
            if not self.enabled:
                break

            now = time.time()

            if now - last_eye >= eye_interval:
                self._remind("20-20-20 rule! 20 second ke liye door dekho, aankho ko rest do.")
                last_eye = now

            if now - last_water >= water_interval:
                self._remind("Paani pi lo! Hydrated raho.")
                last_water = now

            if now - last_break >= break_interval:
                self._remind("Ek chhota break le lo! Uthke stretch karo, thoda walk karo.")
                last_break = now

    def _remind(self, message: str) -> None:
        """Speak reminder if TTS is not busy."""
        if self.speak:
            try:
                self.speak(message)
                logger.info(f"Health reminder: {message}")
            except Exception:
                pass
