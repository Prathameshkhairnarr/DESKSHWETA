"""
AI Brain Module for Shweta AI Desktop Assistant.
Multi-provider support: Groq (primary, fast, 14400/day) + Gemini (fallback).
Automatically rotates if one provider hits rate limit.
"""

import json
import logging
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


class AIBrain:
    """Multi-provider AI brain — Groq (primary) + Gemini (fallback)."""

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
        """Initialize Gemini client (fallback)."""
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
        """Initialize GitHub Models (fallback 2 — uses OpenAI-compatible API)."""
        if not GITHUB_TOKEN:
            return
        try:
            self._github_available = True
            self._providers_available.append("github")
            logger.info("GitHub Models initialized (fallback 2).")
        except Exception as e:
            logger.warning(f"GitHub Models init failed: {e}")

    def think(self, user_input: str) -> Dict[str, Any]:
        """
        Send user input to AI and get structured response.
        Tries Groq first (faster), falls back to Gemini.

        Args:
            user_input: The user's spoken text.

        Returns:
            Dictionary with 'action', 'params', and 'reply' keys.
        """
        if not self._providers_available:
            return {
                "action": "none",
                "reply": "AI brain available nahi hai. API keys check karein."
            }

        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": user_input})

        # Trim history
        if len(self.conversation_history) > CONVERSATION_HISTORY_LIMIT * 2:
            self.conversation_history = self.conversation_history[-(CONVERSATION_HISTORY_LIMIT * 2):]

        # Try providers in order
        response_text = None

        # Try Groq first (fast, high limit)
        if self._groq_client:
            response_text = self._call_groq()

        # Fallback to Gemini
        if response_text is None and self._gemini_client:
            response_text = self._call_gemini()

        # Fallback to GitHub Models
        if response_text is None and self._github_available:
            response_text = self._call_github()

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

    def _call_groq(self) -> Optional[str]:
        """Call Groq API with llama model."""
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            # Only send last 6 messages (less tokens = faster)
            messages.extend(self.conversation_history[-6:])

            response = self._groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=256,  # Shorter replies = faster
            )

            text = response.choices[0].message.content.strip()
            logger.info(f"Groq response: {text[:100]}...")
            return text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                logger.warning("Groq rate limited, trying fallback...")
            else:
                logger.error(f"Groq error: {e}")
            return None

    def _call_gemini(self) -> Optional[str]:
        """Call Gemini API."""
        try:
            from google.genai import types

            # Convert history to Gemini format
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
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )

            text = response.text.strip()
            logger.info(f"Gemini response: {text[:100]}...")
            return text

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning("Gemini rate limited.")
            else:
                logger.error(f"Gemini error: {e}")
            return None

    def _call_github(self) -> Optional[str]:
        """Call GitHub Models API (OpenAI-compatible endpoint)."""
        try:
            import requests

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
            else:
                logger.warning(f"GitHub Models HTTP {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"GitHub Models error: {e}")
            return None

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse AI JSON response — handles different formats from different providers."""
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])

            data = json.loads(cleaned)

            # Standard format: {"action": "x", "params": {...}, "reply": "..."}
            action = data.get("action", "none")
            params = data.get("params", {})
            reply = data.get("reply", "")

            # Handle GitHub Models format where params are at top level
            # e.g., {"action": "play_youtube", "query": "song name", "reply": "..."}
            if not params:
                # Collect all keys that aren't action/reply/params as params
                extra_keys = {k: v for k, v in data.items() if k not in ("action", "reply", "params")}
                if extra_keys:
                    params = extra_keys

            return {"action": action, "params": params, "reply": reply}

        except json.JSONDecodeError:
            logger.warning(f"JSON parse failed: {text[:80]}")
            return {"action": "none", "params": {}, "reply": text}

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
