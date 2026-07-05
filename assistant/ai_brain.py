"""
AI Brain Module for Shweta AI Desktop Assistant.
Multi-provider support with ProviderHealthCache for smart failover.
Groq (primary) → Gemini (fallback 1) → GitHub Models (fallback 2).

OPTIMIZED v2.0:
- Retry logic with exponential backoff (failure path only, no delays on success)
- Robust JSON parsing with regex fallback
- Provider health cache with usage counters + rate limit awareness
- Response quality validation (length, language, action validation)
- Structured logging with latency tracking
- Conversation history with proper trimming + export
- Offline fallback when all providers down
"""

import copy
import json
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

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
# KNOWN ACTIONS — for validation
# ============================================================
KNOWN_ACTIONS = {
    "none", "open_youtube", "open_google", "open_website", "play_youtube",
    "media_play_pause", "media_fullscreen", "media_exit_fullscreen",
    "media_next", "media_previous", "media_forward", "media_rewind",
    "media_mute", "media_volume_up", "media_volume_down", "media_set_volume",
    "media_captions", "browser_new_tab", "browser_close_tab", "close_tab",
    "browser_switch_tab", "browser_back", "browser_refresh", "close_window",
    "take_screenshot", "get_time", "get_date", "volume_up", "volume_down",
    "volume_mute", "lock_screen", "open_file_manager", "type_text",
    "copy_to_clipboard", "empty_recycle_bin", "run_command",
    "shutdown_pc", "restart_pc", "sleep_pc",
    "open_notepad", "open_calculator", "open_terminal", "open_vscode",
    "open_spotify", "close_app", "open_app", "get_weather",
    "set_timer", "set_reminder", "list_timers", "cancel_timer",
    "create_file", "create_folder", "delete_file", "rename_file",
    "move_file", "copy_file", "list_files", "open_file",
    "search_file", "search_and_open",
    "get_battery", "get_ram_usage", "get_storage", "get_cpu_usage",
    "get_wifi_status", "get_system_info",
    "add_note", "list_notes", "delete_note", "complete_note", "clear_notes",
    "snap_left", "snap_right", "maximize_window", "minimize_window",
    "minimize_all", "switch_window", "task_view",
    "daily_briefing", "send_whatsapp", "send_whatsapp_by_name",
    "read_screen", "start_gesture", "stop_gesture",
    "browser_agent_task", "browser_agent_history", "multi_browser_task",
    "set_mode", "remember", "get_memory",
    "health_reminders_on", "health_reminders_off",
    "set_language", "get_usage_stats", "clear_history",
    "spotify_play_pause", "spotify_next", "spotify_previous",
    "spotify_now_playing", "spotify_play_song", "spotify_play_playlist",
    "spotify_mood", "spotify_volume", "spotify_shuffle",
    "send_email", "get_crypto_price", "get_stock_market", "get_news",
    "get_gold_price",
    "morning_briefing",
    "open_tradingview", "draw_trend_line", "draw_horizontal_line",
    "draw_rectangle", "draw_fibonacci", "mark_support_resistance",
    "undo_drawing", "clear_drawings", "change_symbol", "change_timeframe",
    "auto_search_and_play", "auto_youtube_search", "auto_play_first",
    "auto_google_search", "auto_open_url", "auto_click", "auto_type",
    "auto_scroll_down", "auto_scroll_up", "auto_go_back", "auto_close_browser",
    "change_style", "start_game", "play_turn",
}


# ============================================================
# ProviderHealthCache — Smart provider failover + usage tracking
# ============================================================

class ProviderHealthCache:
    """
    Tracks provider health, usage counters, and rate limit awareness.

    Cooldown rules:
    - 429 Rate Limit → skip for 5 minutes
    - Connection/timeout error → skip for 30 seconds
    - Other errors → skip for 10 seconds

    Rate limit awareness (free tiers):
    - Groq: 14400 req/day = 600/hour
    - Gemini: 1500 req/day = ~62/hour
    - GitHub: 150 req/day = ~6/hour
    """

    COOLDOWNS = {
        "rate_limit": 300,    # 5 minutes
        "connection": 30,     # 30 seconds
        "other": 10,          # 10 seconds
    }

    # Free tier hourly limits (80% threshold for proactive switching)
    HOURLY_LIMITS = {
        "groq": 600,
        "gemini": 62,
        "github": 6,
    }
    WARN_THRESHOLD = 0.80  # Warn at 80% usage

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: Dict[str, Dict] = {}
        self._last_success: Dict[str, float] = {}
        # Usage counters: {provider: {hour_key: count}}
        self._usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Daily totals
        self._daily_usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _hour_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d-%H")

    def _day_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def record_request(self, provider_name: str) -> None:
        """Record a request to a provider."""
        with self._lock:
            self._usage[provider_name][self._hour_key()] += 1
            self._daily_usage[provider_name][self._day_key()] += 1

    def get_hourly_usage(self, provider_name: str) -> int:
        """Get requests made this hour."""
        with self._lock:
            return self._usage[provider_name].get(self._hour_key(), 0)

    def get_daily_usage(self, provider_name: str) -> int:
        """Get requests made today."""
        with self._lock:
            return self._daily_usage[provider_name].get(self._day_key(), 0)

    def is_approaching_limit(self, provider_name: str) -> bool:
        """Check if provider is approaching hourly rate limit."""
        limit = self.HOURLY_LIMITS.get(provider_name, 999)
        usage = self.get_hourly_usage(provider_name)
        return usage >= (limit * self.WARN_THRESHOLD)

    def is_at_limit(self, provider_name: str) -> bool:
        """Check if provider has hit hourly limit."""
        limit = self.HOURLY_LIMITS.get(provider_name, 999)
        usage = self.get_hourly_usage(provider_name)
        return usage >= limit

    def mark_failed(self, provider_name: str, error_type: str) -> None:
        """Record a provider failure with appropriate cooldown."""
        cooldown = self.COOLDOWNS.get(error_type, self.COOLDOWNS["other"])
        with self._lock:
            self._failures[provider_name] = {
                "error_type": error_type,
                "failed_at": time.time(),
                "cooldown": cooldown,
            }
        logger.warning(f"[Health] {provider_name} marked {error_type} → cooldown {cooldown}s")

    def mark_success(self, provider_name: str) -> None:
        """Reset failure state on success."""
        with self._lock:
            self._failures.pop(provider_name, None)
            self._last_success[provider_name] = time.time()

    def is_available(self, provider_name: str) -> bool:
        """Check if provider is available (not in cooldown AND not at limit)."""
        # Check rate limit first
        if self.is_at_limit(provider_name):
            return False
        with self._lock:
            failure = self._failures.get(provider_name)
            if failure is None:
                return True
            elapsed = time.time() - failure["failed_at"]
            if elapsed >= failure["cooldown"]:
                del self._failures[provider_name]
                return True
            return False

    def get_ordered_providers(self, provider_names: List[str]) -> List[str]:
        """Return providers sorted: available first, then by last success time."""
        with self._lock:
            available = []
            unavailable = []
            for name in provider_names:
                # Check rate limit
                limit = self.HOURLY_LIMITS.get(name, 999)
                usage = self._usage[name].get(self._hour_key(), 0)
                if usage >= limit:
                    unavailable.append(name)
                    continue
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
            available.sort(key=lambda n: self._last_success.get(n, 0), reverse=True)
            return available + unavailable

    def get_remaining_cooldown(self, provider_name: str) -> int:
        """Get remaining cooldown seconds."""
        with self._lock:
            failure = self._failures.get(provider_name)
            if failure is None:
                return 0
            remaining = failure["cooldown"] - (time.time() - failure["failed_at"])
            return max(0, int(remaining))

    def get_status(self) -> Dict[str, Any]:
        """Get full health status for debugging."""
        status = {}
        for name in ["groq", "gemini", "github"]:
            status[name] = {
                "available": self.is_available(name),
                "hourly_usage": self.get_hourly_usage(name),
                "daily_usage": self.get_daily_usage(name),
                "cooldown_remaining": self.get_remaining_cooldown(name),
                "approaching_limit": self.is_approaching_limit(name),
            }
        return status


# Module-level singleton
_provider_cache = ProviderHealthCache()


# ============================================================
# Robust JSON Parser — handles all malformed AI responses
# ============================================================

def parse_ai_response(text: str) -> Dict[str, Any]:
    """
    Robust AI response parser. Handles:
    - Valid JSON
    - JSON wrapped in markdown code blocks
    - JSON with extra text before/after
    - Action names with embedded params: "get_weather{city=\"Delhi\"}"
    - Missing fields (action, params, reply, emotion)
    - params as string instead of dict
    - Completely missing JSON (plain text reply)
    - Empty response

    Returns: {"action": str, "params": dict, "reply": str, "emotion": str}
    """
    if not text or not text.strip():
        return {"action": "none", "params": {}, "reply": "Samajh nahi aaya, phir se bol.", "emotion": "neutral"}

    cleaned = text.strip()

    # Strip markdown code blocks
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Find JSON object boundaries
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    data = None
    if start != -1 and end != -1 and end > start:
        json_str = cleaned[start:end + 1]
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try fixing common issues: single quotes, trailing commas
            try:
                fixed = json_str.replace("'", '"')
                fixed = re.sub(r',\s*}', '}', fixed)
                fixed = re.sub(r',\s*]', ']', fixed)
                data = json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # If JSON parse failed entirely, try regex extraction
    if data is None or not isinstance(data, dict):
        return _regex_extract(text)

    # Extract fields with type safety
    action = data.get("action", "none") or "none"
    params = data.get("params", {})
    reply = data.get("reply", "")
    emotion = data.get("emotion", "")

    # Type coercion
    if not isinstance(action, str):
        action = str(action) if action else "none"
    if not isinstance(reply, str):
        reply = str(reply) if reply else ""
    if not isinstance(emotion, str):
        emotion = ""

    # Handle params as string (AI sometimes returns "params": "query")
    if isinstance(params, str):
        # Try to parse as JSON
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, ValueError):
            params = {"value": params}
    if not isinstance(params, dict):
        params = {}

    # FIX: Handle AI embedding params in action name like "get_weather{city=\"Delhi\"}"
    if "{" in action:
        clean_action = action[:action.index("{")].strip()
        embedded_str = action[action.index("{"):]
        try:
            normalized = re.sub(r'(\w+)\s*=\s*"([^"]*)"', r'"\1":"\2"', embedded_str)
            normalized = re.sub(r"(\w+)\s*=\s*'([^']*)'", r'"\1":"\2"', normalized)
            normalized = re.sub(r'\{(\w+):', r'{"\1":', normalized)
            embedded_params = json.loads(normalized)
            if isinstance(embedded_params, dict):
                for k, v in embedded_params.items():
                    if k not in params or not params[k]:
                        params[k] = v
        except (json.JSONDecodeError, ValueError):
            pass
        action = clean_action
        logger.debug(f"Fixed embedded action: → '{action}' params: {params}")

    # Handle GitHub Models format: params at top level
    if not params:
        extra_keys = {k: v for k, v in data.items() if k not in ("action", "reply", "params", "emotion")}
        if extra_keys:
            params = extra_keys

    # Validate action against known actions
    if action != "none" and action not in KNOWN_ACTIONS:
        # Try fuzzy match (common AI mistakes)
        close_match = _fuzzy_action_match(action)
        if close_match:
            logger.info(f"[Parse] Fuzzy action fix: '{action}' → '{close_match}'")
            action = close_match
        else:
            logger.warning(f"[Parse] Unknown action '{action}' → defaulting to 'none'")
            # Keep the reply, just don't execute unknown action
            action = "none"

    # Validate emotion
    valid_emotions = {"happy", "sad", "angry", "surprised", "relaxed", "neutral"}
    if emotion not in valid_emotions:
        emotion = _detect_emotion(reply) if reply else "neutral"

    return {"action": action, "params": params, "reply": reply, "emotion": emotion}


def _regex_extract(text: str) -> Dict[str, Any]:
    """Fallback: extract fields from malformed JSON using regex."""
    reply = text
    action = "none"
    params = {}

    # Try to find "reply": "..."
    match = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if match:
        reply = match.group(1).replace('\\"', '"').replace('\\n', '\n')

    # Try to find "action": "..."
    match = re.search(r'"action"\s*:\s*"([^"]*)"', text)
    if match:
        action = match.group(1)
        if "{" in action:
            action = action[:action.index("{")].strip()

    # Try to find "params": {...}
    match = re.search(r'"params"\s*:\s*(\{[^}]*\})', text)
    if match:
        try:
            params = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    emotion = _detect_emotion(reply)
    return {"action": action, "params": params, "reply": reply, "emotion": emotion}


def _fuzzy_action_match(action: str) -> Optional[str]:
    """Try to match a misspelled/close action name."""
    action_lower = action.lower().strip()
    # Direct lowercase match
    for known in KNOWN_ACTIONS:
        if known == action_lower:
            return known
    # Partial match (action contains known or vice versa)
    for known in KNOWN_ACTIONS:
        if known in action_lower or action_lower in known:
            return known
    return None


def _detect_emotion(text: str) -> str:
    """Detect emotion from reply text using keyword matching."""
    if not text:
        return "neutral"
    text_lower = text.lower()

    happy_words = [
        "haha", "maza", "khushi", "great", "awesome", "bilkul", "zaroor",
        "done", "ho gaya", "kar diya", "enjoy", "badhai", "yay", "accha",
        "shandaar", "mast", "badhiya", "kamaal", "fantastic", "perfect",
        "chalo", "ready", "set hai",
    ]
    angry_words = [
        "error", "problem", "gadbad", "kharab", "fail", "nahi kar sakta",
        "not possible", "restricted", "blocked", "band karo", "gussa",
        "permission denied", "access denied",
    ]
    sad_words = [
        "sorry", "maaf", "dukh", "sad", "nahi mila", "unsuccessful",
        "unable", "afsos", "galti", "unfortunately", "udaas",
        "nahi ho paya", "fail ho gaya", "mushkil", "pareshan",
    ]
    surprised_words = [
        "wow", "arrey", "kya baat", "amazing", "unbelievable",
        "seriously", "sach mein", "really", "whoa", "OMG", "interesting",
    ]
    relaxed_words = [
        "chill", "relax", "aaram", "theek", "sab theek", "no worries",
        "koi baat nahi", "tension mat", "shanti", "calm", "easy",
    ]

    scores = {
        "happy": sum(1.5 if len(w) > 5 else 1 for w in happy_words if w in text_lower),
        "angry": sum(1.5 if len(w) > 5 else 1 for w in angry_words if w in text_lower),
        "sad": sum(1.5 if len(w) > 5 else 1 for w in sad_words if w in text_lower),
        "surprised": sum(1.5 if len(w) > 5 else 1 for w in surprised_words if w in text_lower),
        "relaxed": sum(1.5 if len(w) > 5 else 1 for w in relaxed_words if w in text_lower),
    }

    max_emotion = max(scores, key=scores.get)
    return max_emotion if scores[max_emotion] >= 1 else "neutral"


# ============================================================
# Offline fallback responses
# ============================================================

_OFFLINE_RESPONSES = [
    "Yaar abhi AI providers down hain, thodi der mein try kar.",
    "Internet ya API mein issue hai, ek minute ruk.",
    "Abhi kuch gadbad hai connection mein, phir se try kariyo.",
]
_offline_idx = 0


def _last_resort_response() -> Dict[str, Any]:
    """Offline fallback when ALL providers are down."""
    global _offline_idx
    reply = _OFFLINE_RESPONSES[_offline_idx % len(_OFFLINE_RESPONSES)]
    _offline_idx += 1
    return {"action": "none", "params": {}, "reply": reply, "emotion": "sad"}


# ============================================================
# AIBrain — Main class
# ============================================================

class AIBrain:
    """Multi-provider AI brain with smart health-based failover and retry logic."""

    def __init__(self) -> None:
        """Initialize AI providers."""
        self.conversation_history: List[Dict[str, str]] = []
        self._groq_client = None
        self._gemini_client = None
        self._github_available = False
        self._providers_available: List[str] = []
        self._user_context: str = ""

        self._init_groq()
        self._init_gemini()
        self._init_github()

        if self._providers_available:
            logger.info(f"[AI] Providers ready: {', '.join(self._providers_available)}")
        else:
            logger.error("[AI] No providers available!")

    def _init_groq(self) -> None:
        """Initialize Groq client (primary — fast, 14400 req/day)."""
        if not GROQ_API_KEY:
            return
        try:
            from groq import Groq
            self._groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
            self._providers_available.append("groq")
            logger.info("[AI] Groq initialized (primary).")
        except Exception as e:
            logger.warning(f"[AI] Groq init failed: {e}")

    def _init_gemini(self) -> None:
        """Initialize Gemini client (fallback 1)."""
        if not GEMINI_API_KEY:
            return
        try:
            from google import genai
            self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            self._providers_available.append("gemini")
            logger.info("[AI] Gemini initialized (fallback 1).")
        except Exception as e:
            logger.warning(f"[AI] Gemini init failed: {e}")

    def _init_github(self) -> None:
        """Initialize GitHub Models (fallback 2)."""
        if not GITHUB_TOKEN:
            return
        try:
            self._github_available = True
            self._providers_available.append("github")
            logger.info("[AI] GitHub Models initialized (fallback 2).")
        except Exception as e:
            logger.warning(f"[AI] GitHub Models init failed: {e}")

    def think(self, user_input: str, language_manager=None) -> Dict[str, Any]:
        """
        Send user input to AI and get structured response.
        Uses ProviderHealthCache for smart provider selection with retry.
        NO artificial delays on success path.
        """
        if not self._providers_available:
            return _last_resort_response()

        # Auto-detect language
        lang_instruction = ""
        if language_manager:
            language_manager.detect_and_set(user_input)
            lang_instruction = language_manager.get_ai_prompt()

        # Get user context
        self._user_context = getattr(self, '_user_context', "")

        # Add to conversation history (use deepcopy to avoid mutation)
        self.conversation_history.append({"role": "user", "content": user_input})
        self._trim_history()

        # Get providers in health-sorted order
        ordered = _provider_cache.get_ordered_providers(self._providers_available)

        # Rate limit awareness: warn if approaching
        for p in self._providers_available:
            if _provider_cache.is_approaching_limit(p):
                hourly = _provider_cache.get_hourly_usage(p)
                limit = _provider_cache.HOURLY_LIMITS.get(p, 999)
                logger.warning(f"[AI] {p} approaching limit: {hourly}/{limit} this hour")

        # Check if ALL providers are unavailable
        all_unavailable = all(
            not _provider_cache.is_available(p) for p in self._providers_available
        )

        response_text = None
        used_provider = None

        for provider in ordered:
            # Skip unavailable (unless all down)
            if not all_unavailable and not _provider_cache.is_available(provider):
                remaining = _provider_cache.get_remaining_cooldown(provider)
                logger.info(f"[AI] Skipping {provider} — cooldown {remaining}s remaining")
                continue

            # Try provider with retry logic
            response_text = self._call_with_retry(provider, lang_instruction)

            if response_text is not None:
                _provider_cache.mark_success(provider)
                _provider_cache.record_request(provider)
                used_provider = provider
                break

        if response_text is None:
            logger.error("[AI] All providers failed.")
            return _last_resort_response()

        # Add to history
        self.conversation_history.append({"role": "assistant", "content": response_text})

        # Parse response
        result = parse_ai_response(response_text)

        # Response quality validation
        result = self._validate_response(result, user_input, lang_instruction)

        # Log
        self._log_conversation(user_input, result, used_provider)
        return result

    def _call_with_retry(self, provider: str, lang_instruction: str) -> Optional[str]:
        """
        Call provider with retry logic. Exponential backoff on FAILURE only.
        - 429 → skip immediately (no retry, mark in health cache)
        - Timeout → retry once after 1s, then skip
        - Bad response → retry once, then skip
        - Success → return immediately (no delays)
        """
        max_attempts = 2  # 1 initial + 1 retry (only on timeout/transient)
        backoff = 1.0  # seconds between retries

        for attempt in range(max_attempts):
            start_time = time.time()

            try:
                if provider == "groq" and self._groq_client:
                    text = self._call_groq(lang_instruction)
                elif provider == "gemini" and self._gemini_client:
                    text = self._call_gemini(lang_instruction)
                elif provider == "github" and self._github_available:
                    text = self._call_github(lang_instruction)
                else:
                    return None

                latency = time.time() - start_time

                if text is not None:
                    logger.info(f"[AI] {provider} responded in {latency:.2f}s (attempt {attempt+1})")
                    return text

                # text is None means provider returned error
                # Check if it was rate limit (don't retry)
                if not _provider_cache.is_available(provider):
                    logger.info(f"[AI] {provider} rate limited, not retrying.")
                    return None

                # Transient error — retry with backoff (only if not last attempt)
                if attempt < max_attempts - 1:
                    logger.info(f"[AI] {provider} failed (attempt {attempt+1}), retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff

            except Exception as e:
                latency = time.time() - start_time
                logger.error(f"[AI] {provider} exception (attempt {attempt+1}, {latency:.2f}s): {e}")
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2

        return None

    def _build_dynamic_prompt(self, lang_instruction: str) -> str:
        """Build the full system prompt with context injections."""
        prompt = SYSTEM_PROMPT
        if self._user_context:
            prompt += f"\n\nUSER CONTEXT (use this to personalize):\n{self._user_context}"
        if lang_instruction:
            prompt += f"\n\nLANGUAGE FOR THIS RESPONSE (MUST FOLLOW): {lang_instruction}"
        return prompt

    def _call_groq(self, lang_instruction: str = "") -> Optional[str]:
        """Call Groq API with llama model."""
        try:
            dynamic_prompt = self._build_dynamic_prompt(lang_instruction)
            messages = [{"role": "system", "content": dynamic_prompt}]
            messages.extend(self.conversation_history[-4:])

            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.6,
                max_tokens=200,
            )

            text = response.choices[0].message.content.strip()
            if not text:
                logger.warning("[AI] Groq returned empty response")
                return None
            return text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                _provider_cache.mark_failed("groq", "rate_limit")
            elif "timeout" in error_str.lower() or "connection" in error_str.lower():
                _provider_cache.mark_failed("groq", "connection")
            else:
                _provider_cache.mark_failed("groq", "other")
                logger.error(f"[AI] Groq error: {e}")
            return None

    def _call_gemini(self, lang_instruction: str = "") -> Optional[str]:
        """Call Gemini API."""
        try:
            from google.genai import types

            dynamic_prompt = self._build_dynamic_prompt(lang_instruction)

            gemini_history = []
            for msg in self.conversation_history[-4:]:
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
                    max_output_tokens=300,
                )
            )

            text = response.text.strip()
            if not text:
                logger.warning("[AI] Gemini returned empty response")
                return None
            return text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                _provider_cache.mark_failed("gemini", "rate_limit")
            elif "timeout" in error_str.lower() or "connection" in error_str.lower():
                _provider_cache.mark_failed("gemini", "connection")
            else:
                _provider_cache.mark_failed("gemini", "other")
                logger.error(f"[AI] Gemini error: {e}")
            return None

    def _call_github(self, lang_instruction: str = "") -> Optional[str]:
        """Call GitHub Models API (OpenAI-compatible endpoint)."""
        try:
            import requests

            dynamic_prompt = self._build_dynamic_prompt(lang_instruction)
            messages = [{"role": "system", "content": dynamic_prompt}]
            messages.extend(self.conversation_history[-6:])

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
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                if not text:
                    logger.warning("[AI] GitHub returned empty response")
                    return None
                return text
            elif response.status_code == 429:
                _provider_cache.mark_failed("github", "rate_limit")
                return None
            else:
                _provider_cache.mark_failed("github", "other")
                logger.warning(f"[AI] GitHub HTTP {response.status_code}")
                return None

        except Exception as e:
            if "timeout" in str(e).lower() or "Timeout" in type(e).__name__:
                _provider_cache.mark_failed("github", "connection")
            else:
                _provider_cache.mark_failed("github", "other")
                logger.error(f"[AI] GitHub error: {e}")
            return None

    # ============================================================
    # Response Quality Validation
    # ============================================================

    def _validate_response(self, result: Dict[str, Any], user_input: str, lang_instruction: str) -> Dict[str, Any]:
        """
        Validate and fix response quality:
        - Truncate overly long replies (>200 chars for voice)
        - Validate action is known
        - Ensure reply is not empty
        """
        reply = result.get("reply", "")

        # Empty reply fallback
        if not reply or not reply.strip():
            result["reply"] = "Hmm, kuch samajh nahi aaya."
            result["emotion"] = "neutral"

        # Truncate long replies for voice (keep full for display)
        if len(reply) > 250:
            # Find a natural break point
            truncated = reply[:250]
            last_period = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
            if last_period > 100:
                result["reply"] = truncated[:last_period + 1]
            else:
                result["reply"] = truncated.rstrip() + "..."

        return result

    # ============================================================
    # Conversation History Management
    # ============================================================

    def _trim_history(self) -> None:
        """Trim conversation history to prevent memory bloat. Uses deepcopy for safety."""
        max_entries = CONVERSATION_HISTORY_LIMIT * 2  # 20 messages (10 exchanges)
        if len(self.conversation_history) > max_entries:
            # Keep most recent entries
            self.conversation_history = copy.deepcopy(
                self.conversation_history[-max_entries:]
            )

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
        logger.info("[AI] Conversation history cleared.")

    def export_history(self, filepath: Optional[str] = None) -> str:
        """Export conversation history to a dated text file."""
        if not filepath:
            today = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            filepath = str(LOGS_DIR / f"conversation_export_{today}.txt")

        try:
            lines = []
            lines.append(f"=== Shweta Conversation Export ===")
            lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"Messages: {len(self.conversation_history)}")
            lines.append("=" * 50)

            for msg in self.conversation_history:
                role = "User" if msg["role"] == "user" else "Shweta"
                lines.append(f"\n[{role}]: {msg['content']}")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            logger.info(f"[AI] History exported to: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"[AI] Export failed: {e}")
            return ""

    def get_provider_status(self) -> Dict[str, Any]:
        """Get current provider health status (for debugging/display)."""
        return _provider_cache.get_status()

    # ============================================================
    # Logging
    # ============================================================

    def _log_conversation(self, user_input: str, response: Dict[str, Any], provider: Optional[str] = None) -> None:
        """Log conversation to daily file with provider info."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = LOGS_DIR / f"chat_{today}.txt"
            timestamp = datetime.now().strftime("%H:%M:%S")

            provider_str = f" [{provider}]" if provider else ""
            log_entry = (
                f"[{timestamp}]{provider_str} User: {user_input}\n"
                f"[{timestamp}]{provider_str} Shweta: {response.get('reply', '')}\n"
                f"[{timestamp}]{provider_str} Action: {response.get('action', 'none')}"
            )
            params = response.get("params", {})
            if params:
                log_entry += f" | Params: {json.dumps(params, ensure_ascii=False)}"
            log_entry += f"\n{'=' * 50}\n"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"[AI] Log failed: {e}")
