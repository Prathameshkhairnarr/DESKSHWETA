"""
AI Brain Module for Shweta AI Desktop Assistant.
Multi-provider support with ProviderHealthCache for smart failover.
Groq (primary) → Gemini (fallback 1) → GitHub Models (fallback 2).
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    GITHUB_TOKEN,
    CONVERSATION_HISTORY_LIMIT,
    SYSTEM_PROMPT,
    LOGS_DIR,
)

logger = logging.getLogger(__name__)


# ============================================================
# NEW: ProviderHealthCache — Smart provider failover
# ============================================================

class ProviderHealthCache:
    """
    Tracks provider health to avoid wasting time on rate-limited providers.
    
    Cooldown rules:
    - 429 Rate Limit → skip for 5 minutes
    - Connection/timeout error → skip for 30 seconds
    - Other errors → skip for 10 seconds
    """

    # Cooldown durations in seconds
    COOLDOWNS = {
        "rate_limit": 300,    # 5 minutes
        "connection": 30,     # 30 seconds
        "other": 10,          # 10 seconds
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: Dict[str, Dict] = {}
        # {provider_name: {"error_type": str, "failed_at": float, "cooldown": int}}
        self._last_success: Dict[str, float] = {}

    def mark_failed(self, provider_name: str, error_type: str) -> None:
        """Record a provider failure with appropriate cooldown."""
        cooldown = self.COOLDOWNS.get(error_type, self.COOLDOWNS["other"])
        with self._lock:
            self._failures[provider_name] = {
                "error_type": error_type,
                "failed_at": time.time(),
                "cooldown": cooldown,
            }

    def mark_success(self, provider_name: str) -> None:
        """Reset failure state on success."""
        with self._lock:
            self._failures.pop(provider_name, None)
            self._last_success[provider_name] = time.time()

    def is_available(self, provider_name: str) -> bool:
        """Check if provider is available (not in cooldown)."""
        with self._lock:
            failure = self._failures.get(provider_name)
            if failure is None:
                return True
            elapsed = time.time() - failure["failed_at"]
            if elapsed >= failure["cooldown"]:
                # Cooldown expired — provider is available again
                del self._failures[provider_name]
                return True
            return False

    def get_ordered_providers(self, provider_names: List[str]) -> List[str]:
        """
        Return providers sorted: available first, then by last success time.
        Unavailable providers go to the end.
        """
        with self._lock:
            available = []
            unavailable = []

            for name in provider_names:
                failure = self._failures.get(name)
                if failure is None:
                    available.append(name)
                else:
                    elapsed = time.time() - failure["failed_at"]
                    if elapsed >= failure["cooldown"]:
                        del self._failures[name]
                        available.append(name)
                    else:
                        unavailable.append(name)

            # Sort available by last success (most recent first)
            available.sort(
                key=lambda n: self._last_success.get(n, 0),
                reverse=True
            )

            return available + unavailable

    def get_remaining_cooldown(self, provider_name: str) -> int:
        """Get remaining cooldown seconds for a provider."""
        with self._lock:
            failure = self._failures.get(provider_name)
            if failure is None:
                return 0
            remaining = failure["cooldown"] - (time.time() - failure["failed_at"])
            return max(0, int(remaining))

    def get_status(self) -> Dict[str, Any]:
        """Get current health status of all providers (for debugging)."""
        with self._lock:
            status = {}
            for name, failure in self._failures.items():
                elapsed = time.time() - failure["failed_at"]
                remaining = failure["cooldown"] - elapsed
                status[name] = {
                    "available": remaining <= 0,
                    "error_type": failure["error_type"],
                    "retry_in_sec": max(0, int(remaining)),
                }
            return status


# Module-level singleton
_provider_cache = ProviderHealthCache()

# ============================================================
# END NEW
# ============================================================


class AIBrain:
    """Multi-provider AI brain with smart health-based failover."""

    def __init__(self) -> None:
        """Initialize AI providers."""
        self.conversation_history: List[Dict[str, str]] = []
        self._groq_client = None
        self._gemini_client = None
        self._github_available = False
        self._providers_available: List[str] = []

        self._init_groq()
        self._init_gemini()
        self._init_github()

        if self._providers_available:
            logger.info(f"AI providers ready: {', '.join(self._providers_available)}")
        else:
            logger.error("No AI providers available!")

    def _init_groq(self) -> None:
        """Initialize Groq client (primary — fast, 14400 req/day)."""
        if not GROQ_API_KEY:
            return
        try:
            from groq import Groq
            self._groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
            self._providers_available.append("groq")
            logger.info("Groq AI initialized (primary).")
        except Exception as e:
            logger.warning(f"Groq init failed: {e}")

    def _init_gemini(self) -> None:
        """Initialize Gemini client (fallback 1)."""
        if not GEMINI_API_KEY:
            return
        try:
            from google import genai
            self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            self._providers_available.append("gemini")
            logger.info("Gemini AI initialized (fallback 1).")
        except Exception as e:
            logger.warning(f"Gemini init failed: {e}")

    def _init_github(self) -> None:
        """Initialize GitHub Models (fallback 2)."""
        if not GITHUB_TOKEN:
            return
        try:
            self._github_available = True
            self._providers_available.append("github")
            logger.info("GitHub Models initialized (fallback 2).")
        except Exception as e:
            logger.warning(f"GitHub Models init failed: {e}")

    def think(self, user_input: str, language_manager=None) -> Dict[str, Any]:
        """
        Send user input to AI and get structured response.
        Uses ProviderHealthCache for smart provider selection.
        """
        if not self._providers_available:
            return {
                "action": "none",
                "reply": "AI brain available nahi hai. API keys check karein."
            }

        # Auto-detect language from user input
        lang_instruction = ""
        if language_manager:
            language_manager.detect_and_set(user_input)
            lang_instruction = language_manager.get_ai_prompt()

        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})

        # Trim history
        if len(self.conversation_history) > CONVERSATION_HISTORY_LIMIT * 2:
            self.conversation_history = self.conversation_history[-(CONVERSATION_HISTORY_LIMIT * 2):]

        # === NEW: Get providers in health-sorted order ===
        ordered = _provider_cache.get_ordered_providers(self._providers_available)

        # Check if ALL providers are unavailable — if so, try them all anyway
        all_unavailable = all(
            not _provider_cache.is_available(p) for p in self._providers_available
        )

        response_text = None

        for provider in ordered:
            # Skip unavailable providers (unless all are down)
            if not all_unavailable and not _provider_cache.is_available(provider):
                remaining = _provider_cache.get_remaining_cooldown(provider)
                mins = remaining // 60
                secs = remaining % 60
                logger.info(f"[AI] Skipping {provider} — rate limited, retry in {mins}m {secs}s")
                continue

            # Try this provider
            if provider == "groq" and self._groq_client:
                response_text = self._call_groq(lang_instruction)
            elif provider == "gemini" and self._gemini_client:
                response_text = self._call_gemini(lang_instruction)
            elif provider == "github" and self._github_available:
                response_text = self._call_github(lang_instruction)

            if response_text is not None:
                # === NEW: Mark success ===
                _provider_cache.mark_success(provider)
                break

        if response_text is None:
            return {
                "action": "none",
                "reply": "Kuch gadbad hui, thodi der mein try karein."
            }

        # Add to history
        self.conversation_history.append({"role": "assistant", "content": response_text})

        # Parse response
        result = self._parse_response(response_text)
        self._log_conversation(user_input, result)
        return result

    def _call_groq(self, lang_instruction: str = "") -> Optional[str]:
        """Call Groq API with llama model."""
        try:
            # Build dynamic system prompt with language instruction
            dynamic_prompt = SYSTEM_PROMPT
            if lang_instruction:
                dynamic_prompt += f"\n\nLANGUAGE FOR THIS RESPONSE (MUST FOLLOW): {lang_instruction}"

            messages = [{"role": "system", "content": dynamic_prompt}]
            messages.extend(self.conversation_history[-6:])

            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=256,
            )

            text = response.choices[0].message.content.strip()
            logger.info(f"Groq response: {text[:100]}...")
            return text

        except Exception as e:
            error_str = str(e)
            # === NEW: Classify error and mark in cache ===
            if "429" in error_str or "rate_limit" in error_str.lower():
                _provider_cache.mark_failed("groq", "rate_limit")
                logger.warning("Groq rate limited → cached for 5 min.")
            elif "timeout" in error_str.lower() or "connection" in error_str.lower():
                _provider_cache.mark_failed("groq", "connection")
                logger.warning("Groq connection error → cached for 30s.")
            else:
                _provider_cache.mark_failed("groq", "other")
                logger.error(f"Groq error: {e}")
            return None

    def _call_gemini(self, lang_instruction: str = "") -> Optional[str]:
        """Call Gemini API."""
        try:
            from google.genai import types

            dynamic_prompt = SYSTEM_PROMPT
            if lang_instruction:
                dynamic_prompt += f"\n\nLANGUAGE FOR THIS RESPONSE (MUST FOLLOW): {lang_instruction}"

            gemini_history = []
            for msg in self.conversation_history:
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })

            response = self._gemini_client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=gemini_history,
                config=types.GenerateContentConfig(
                    system_instruction=dynamic_prompt,
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )

            text = response.text.strip()
            logger.info(f"Gemini response: {text[:100]}...")
            return text

        except Exception as e:
            error_str = str(e)
            # === NEW: Classify error and mark in cache ===
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                _provider_cache.mark_failed("gemini", "rate_limit")
                logger.warning("Gemini rate limited → cached for 5 min.")
            elif "timeout" in error_str.lower() or "connection" in error_str.lower():
                _provider_cache.mark_failed("gemini", "connection")
            else:
                _provider_cache.mark_failed("gemini", "other")
                logger.error(f"Gemini error: {e}")
            return None

    def _call_github(self, lang_instruction: str = "") -> Optional[str]:
        """Call GitHub Models API (OpenAI-compatible endpoint)."""
        try:
            import requests

            dynamic_prompt = SYSTEM_PROMPT
            if lang_instruction:
                dynamic_prompt += f"\n\nLANGUAGE FOR THIS RESPONSE (MUST FOLLOW): {lang_instruction}"

            messages = [{"role": "system", "content": dynamic_prompt}]
            messages.extend(self.conversation_history)

            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
            }

            response = requests.post(
                "https://models.inference.ai.azure.com/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                logger.info(f"GitHub Models response: {text[:100]}...")
                return text
            elif response.status_code == 429:
                # === NEW: Mark rate limit ===
                _provider_cache.mark_failed("github", "rate_limit")
                logger.warning("GitHub Models rate limited → cached for 5 min.")
                return None
            else:
                _provider_cache.mark_failed("github", "other")
                logger.warning(f"GitHub Models HTTP {response.status_code}")
                return None

        except requests.Timeout:
            _provider_cache.mark_failed("github", "connection")
            logger.error("GitHub Models timeout.")
            return None
        except Exception as e:
            _provider_cache.mark_failed("github", "other")
            logger.error(f"GitHub Models error: {e}")
            return None

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse AI JSON response — handles different formats from different providers."""
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])

            # Handle case where AI wraps JSON in extra text
            # Find first { and last }
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end + 1]

            data = json.loads(cleaned)

            # Ensure data is a dict
            if not isinstance(data, dict):
                return {"action": "none", "params": {}, "reply": text, "emotion": "neutral"}

            action = data.get("action", "none") or "none"
            params = data.get("params", {})
            reply = data.get("reply", "")

            # Ensure types are correct
            if not isinstance(action, str):
                action = "none"
            if not isinstance(params, dict):
                params = {}
            if not isinstance(reply, str):
                reply = str(reply) if reply else ""

            # Handle GitHub Models format where params are at top level
            if not params:
                extra_keys = {k: v for k, v in data.items() if k not in ("action", "reply", "params", "emotion")}
                if extra_keys:
                    params = extra_keys

            # Detect emotion from reply text (or use AI-provided emotion if present)
            emotion = data.get("emotion", None)
            if not emotion or not isinstance(emotion, str):
                emotion = self._detect_emotion(reply)

            return {"action": action, "params": params, "reply": reply, "emotion": emotion}

        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning(f"JSON parse failed: {text[:80]}")
            emotion = self._detect_emotion(text)
            return {"action": "none", "params": {}, "reply": text, "emotion": emotion}
        except Exception as e:
            logger.error(f"Parse response unexpected error: {e}")
            return {"action": "none", "params": {}, "reply": text, "emotion": "neutral"}

    def _detect_emotion(self, text: str) -> str:
        """
        Detect emotion from reply text using keyword matching.
        Returns: happy, angry, sad, surprised, relaxed, neutral
        """
        text_lower = text.lower()

        # Happy indicators
        happy_words = [
            "haha", "😄", "😊", "🎉", "maza", "khushi", "great", "awesome",
            "bilkul", "zaroor", "done", "ho gaya", "kar diya", "enjoy",
            "badhai", "congratulations", "yay", "woohoo", "accha", "shandaar",
            "mast", "badhiya", "kamaal", "fantastic", "wonderful", "perfect",
            "chalo", "ready", "lag gaya", "set hai"
        ]
        
        # Angry indicators
        angry_words = [
            "error", "problem", "gadbad", "kharab", "fail",
            "nahi kar sakta", "not possible", "restricted", "blocked",
            "band karo", "hatao", "chup", "gussa", "allowed nahi",
            "permission denied", "access denied"
        ]
        
        # Sad indicators — expanded significantly
        sad_words = [
            "sorry", "maaf", "dukh", "sad", "nahi mila", "nahi mil",
            "unsuccessful", "couldn't", "unable", "afsos", "galti",
            "khed", "unfortunately", "udaas", "dukhi", "miss", "bura laga",
            "nahi ho paya", "nahi hua", "fail ho gaya", "kho gaya",
            "nahi kar payi", "nahi kar paya", "mushkil", "pareshan",
            "takleef", "dard", "rona", "cry", "feeling low", "upset",
            "disappointed", "regret", "lost", "alone", "akela"
        ]
        
        # Surprised indicators
        surprised_words = [
            "wow", "arrey", "oh", "kya baat", "amazing", "unbelievable",
            "seriously", "sach mein", "really", "whoa", "damn", "OMG",
            "are wah", "arre", "oho", "interesting"
        ]
        
        # Relaxed indicators
        relaxed_words = [
            "chill", "relax", "aaram", "theek", "sab theek", "no worries",
            "koi baat nahi", "tension mat", "shanti", "calm", "easy",
            "dhire dhire", "koi nahi"
        ]

        # Count matches (weighted — longer phrases get more weight)
        scores = {
            "happy": sum(1.5 if len(w) > 5 else 1 for w in happy_words if w in text_lower),
            "angry": sum(1.5 if len(w) > 5 else 1 for w in angry_words if w in text_lower),
            "sad": sum(1.5 if len(w) > 5 else 1 for w in sad_words if w in text_lower),
            "surprised": sum(1.5 if len(w) > 5 else 1 for w in surprised_words if w in text_lower),
            "relaxed": sum(1.5 if len(w) > 5 else 1 for w in relaxed_words if w in text_lower),
        }

        # Get highest scoring emotion
        max_emotion = max(scores, key=scores.get)
        if scores[max_emotion] >= 1:
            return max_emotion
        
        return "neutral"

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
        logger.info("Conversation history cleared.")

    def _log_conversation(self, user_input: str, response: Dict[str, Any]) -> None:
        """Log conversation to daily file."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = LOGS_DIR / f"chat_{today}.txt"
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = (
                f"[{timestamp}] User: {user_input}\n"
                f"[{timestamp}] Shweta: {response.get('reply', '')}\n"
                f"[{timestamp}] Action: {response.get('action', 'none')}\n"
                f"{'=' * 50}\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Log failed: {e}")
