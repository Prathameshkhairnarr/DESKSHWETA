"""Multi-agent brain for Shweta.

The assistant has one coordinator and several focused agents.  Agents share the
same short conversation context and persistent user memory, but each one gets a
small role-specific instruction set.  The coordinator always returns the
response shape consumed by ``main.py``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI
from groq import Groq

from config import DEFAULT_CITY, SYSTEM_PROMPT
from assistant.ai_brain import KNOWN_ACTIONS
from assistant.skills.personality import MemoryStore

logger = logging.getLogger(__name__)


AGENT_INSTRUCTIONS = {
    "friend": (
        "Tu Shweta hai, ek warm aur professional AI assistant. Dhyan se sun, "
        "context yaad rakh, short natural Hinglish me reply kar — polite aur helpful. "
        "No slang (yaar/bhai). User ko judge mat kar. Sirf baat ho to action mat lo."
    ),
    "desktop": (
        "Tu desktop operator hai. User ki intent ko exact action me badal. "
        "Action execute karne ke liye dispatch_action use karna compulsory hai. "
        "Params ko sahi keys ke saath bhej aur reply chhota rakho."
    ),
    "researcher": (
        "Tu research agent hai. Online search, comparison, shopping ya current "
        "information ke liye browser_agent_task use kar. Goal me user ki poori "
        "request likh aur result ko simple Hindi me summarize kar."
    ),
    "memory": (
        "Tu memory agent hai. Jab user apna naam, preference, routine, goal ya "
        "important fact bataye to remember_user_info action use kar. Sirf tab "
        "save kar jab user clearly yaad rakhne ko kahe ya fact durable ho."
    ),
    "planner": (
        "Tu planning agent hai. Multi-part request ko samajh kar safest useful "
        "next action choose kar. Multiple browser tasks ke liye multi_browser_task "
        "use kar; destructive action kabhi silently execute mat kar."
    ),
}


def _tool_schema(actions: List[str]) -> List[Dict[str, Any]]:
    """Build provider-neutral tools for all actions exposed by DesktopController."""
    return [
        {
            "type": "function",
            "function": {
                "name": "dispatch_action",
                "description": (
                    "Execute one desktop skill. Use exact action name from the "
                    "allowed list and put arguments in params."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": actions},
                        "params": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "Arguments required by the action.",
                        },
                        "spoken_reply": {"type": "string"},
                        "emotion": {
                            "type": "string",
                            "enum": [
                                "happy", "sad", "angry", "surprised", "relaxed",
                                "neutral", "joy", "fun", "sorrow", "bored",
                                "sleepy", "think", "wink", "pout", "curious",
                                "playful",
                            ],
                        },
                    },
                    "required": ["action", "params", "spoken_reply", "emotion"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "chat_reply",
                "description": "Reply conversationally without executing a desktop action.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "response_text": {"type": "string"},
                        "emotion": {"type": "string"},
                    },
                    "required": ["response_text", "emotion"],
                },
            },
        },
    ]


class MultiAgentBrain:
    """Coordinator for Shweta's friend, skill, research, memory and planning agents."""

    def __init__(self) -> None:
        self.conversation_history: List[Dict[str, str]] = []
        self._user_context = ""
        self.memory = MemoryStore()
        self._providers: List[tuple[str, Any, str]] = []
        self._build_providers()
        self._actions = sorted(set(KNOWN_ACTIONS) | {
            "remember_user_info", "react_to_screen", "brightness_up",
            "brightness_down", "set_brightness", "media_exit_fullscreen",
            "media_set_volume", "browser_agent_task", "multi_browser_task",
        })
        self.agent_stats: Dict[str, int] = {name: 0 for name in AGENT_INSTRUCTIONS}

    def _build_providers(self) -> None:
        """Create only configured clients; empty API keys must never be used.
        Priority: Gemini (reliable) → Groq (fast but rate-limited) → GitHub/OpenAI."""
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        github_key = os.getenv("GITHUB_TOKEN", "").strip()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        freemodel_key = os.getenv("FREEMODEL_API_KEY", "").strip()

        # Gemini first — most reliable, no strict TPM cap
        if gemini_key:
            self._providers.append(("gemini_hub", gemini_key, os.getenv("GEMINI_MODEL", "gemini-2.5-flash")))

        # freemodel.in (OpenAI-compatible) — placed right after Gemini so it becomes
        # the effective primary brain whenever Gemini is rate-limited, giving full
        # replies instead of Groq's terse fallback. Base URL + model come from env so
        # the exact endpoint can be set without code changes.
        if freemodel_key:
            self._providers.append((
                "freemodel", OpenAI(
                    base_url=os.getenv("FREEMODEL_BASE_URL", "https://freemodel.in/v1"),
                    api_key=freemodel_key,
                ), os.getenv("FREEMODEL_MODEL", "gpt-4o-mini")
            ))

        if openai_key:
            self._providers.append((
                "openai", OpenAI(api_key=openai_key), "gpt-4o-mini"
            ))
        # Groq last — fast but 8000 TPM cap causes frequent rate limits
        if groq_key:
            self._providers.append((
                "groq", Groq(api_key=groq_key, max_retries=0),
                os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
            ))
        if github_key:
            self._providers.append((
                "github", OpenAI(
                    base_url="https://models.inference.ai.azure.com",
                    api_key=github_key,
                ), "gpt-4o-mini"
            ))

        if self._providers:
            logger.info(
                "[Agent Hub] Agents ready: %s",
                ", ".join(name for name, _, _ in self._providers),
            )
        else:
            logger.warning("[Agent Hub] No AI provider configured; offline routing enabled.")

    @property
    def status_label(self) -> str:
        if not self._providers:
            return "Offline intent router"
        return "Multi-agent: " + "/".join(name.title() for name, _, _ in self._providers)

    def clear_history(self) -> None:
        self.conversation_history.clear()

    def _select_agent(self, text: str) -> str:
        value = text.lower().strip()
        if any(word in value for word in (
            "yaad rakh", "remember", "bhoolna mat", "mera naam", "meri pasand",
            "my name", "my favorite", "mujhe pasand",
        )):
            return "memory"
        if any(word in value for word in (
            "search", "dhundh", "research", "compare", "comparison", "price",
            "review", "recommend", "amazon", "online", "latest news",
        )):
            return "researcher"
        if any(word in value for word in (
            "aur phir", "then", "saath me", "and also", "multiple", "tabs",
            "ek saath", "plan", "steps",
        )):
            return "planner"
        if any(word in value for word in (
            "order", "swiggy", "zomato", "khana order", "food order",
            "flight", "flights", "ticket book", "flight book",
            # Devanagari + common STT mis-hearings so "फ्लाइट/फ्लाइड बुक करो"
            # and "बिरयानी ऑर्डर करो" still route to the browser action.
            "फ्लाइट", "फ्लाइड", "फ्लाईट", "उड़ान", "विमान", "टिकट बुक",
            "ऑर्डर", "ओर्डर", "स्विगी", "स्विग्गी", "ज़ोमैटो", "जोमैटो",
            "खाना ऑर्डर", "खाना मंगा", "बिरयानी",
        )):
            return "desktop"
        if any(word in value for word in (
            "kholo", "open", "play", "bajao", "lagao", "volume", "file", "folder",
            "screenshot", "weather", "mausam", "timer", "note", "send", "band",
            "close", "lock", "brightness", "youtube", "gana", "music", "time",
            "time kya", "date", "tarikh", "kitna baj",
        )):
            return "desktop"
        return "friend"

    def _context(self, agent: str) -> str:
        memory_context = self.memory.get_prompt_context()
        pieces = [
            f"Current specialist: {agent}",
            AGENT_INSTRUCTIONS[agent],
            "Allowed actions: " + ", ".join(self._actions),
        ]
        if memory_context:
            pieces.append("User memory:\n" + memory_context)
        if self._user_context:
            # Trimmed 2500→800: usage context is background colour, not essential
            # per reply — a smaller slice saves ~400-500 tokens on every brain call.
            pieces.append("Usage context:\n" + self._user_context[-800:])
        return "\n\n".join(pieces)

    def _fast_path(self, text: str, agent: str) -> Optional[Dict[str, Any]]:
        """Handle trivial, unambiguous commands LOCALLY — no LLM call at all.

        This is the biggest credit/latency saver: the most common quick commands
        (time, date, weather, screenshot) are deterministic, so routing them here
        skips the whole brain round-trip (≈7-8k tokens + several seconds on
        freemodel). Returns a result dict on a confident match, else None so the
        message falls through to the full brain. Kept tight on purpose — only
        fires on clear single-intent phrases, never on open-ended conversation."""
        v = text.lower().strip()
        words = v.split()
        # Markers cover BOTH romanized Hinglish AND Devanagari — STT now returns
        # Devanagari (e.g. "टाइम बताओ"), so roman-only markers would never match.
        if any(w in v for w in (
            "time kya", "time batao", "kitne baje", "kitna baj", "samay kya",
            "what time", "what's the time", "kya time",
            "टाइम", "समय", "कितने बजे", "कितना बज", "बजे है", "बजे हैं",
        )):
            return self._result("get_time", {}, "Abhi ka time dekhti hoon.", "neutral", agent)
        if any(w in v for w in (
            "aaj ki date", "aaj ki tarikh", "kaunsi tarikh", "what date",
            "what's the date", "date kya", "aaj kaunsa din", "konsa din",
            "तारीख", "तारिख", "आज की डेट", "आज कौन सा दिन", "कौन सा दिन", "डेट बता",
        )):
            return self._result("get_date", {}, "Date dekhti hoon.", "neutral", agent)
        if (("mausam" in v or "weather" in v or "मौसम" in v) and len(words) <= 5):
            return self._result("get_weather", {"city": DEFAULT_CITY}, "Mausam check karti hoon.", "think", agent)
        if "screenshot" in v or "screen shot" in v or "स्क्रीनशॉट" in v or "स्क्रीन शॉट" in v:
            return self._result("take_screenshot", {}, "Screenshot le rahi hoon.", "neutral", agent)
        return None

    def _offline(self, text: str, agent: str) -> Dict[str, Any]:
        """Useful local behavior when every remote model is unavailable."""
        value = text.lower().strip()
        if any(word in value for word in ("time", "kitna baj", "samay")):
            return self._result("get_time", {}, "Time check karti hoon.", "neutral", agent)
        if any(word in value for word in ("date", "tarikh", "aaj ki date")):
            return self._result("get_date", {}, "Aaj ki date dekhti hoon.", "neutral", agent)
        if "mausam" in value or "weather" in value:
            return self._result("get_weather", {"city": DEFAULT_CITY}, "Mausam check karti hoon.", "think", agent)
        if "screenshot" in value or "screen shot" in value:
            return self._result("take_screenshot", {}, "Screenshot le rahi hoon.", "neutral", agent)
        if any(word in value for word in ("gana", "song", "music", "youtube")):
            query = re.sub(r"\b(play|bajao|lagao|gana|song|music|youtube|par)\b", "", value).strip()
            return self._result("play_youtube", {"query": query or "Hindi music"}, "Music laga rahi hoon.", "happy", agent)
        if "yaad rakh" in value or "remember" in value:
            return self._result("remember_user_info", {"info": text}, "Haan, yaad rakh liya.", "happy", "memory")
        return self._result("none", {}, "Haan bol, main sun rahi hoon.", "relaxed", "friend")

    @staticmethod
    def _result(action: str, params: Dict[str, Any], reply: str, emotion: str, agent: str) -> Dict[str, Any]:
        return {
            "action": action,
            "params": params,
            "reply": reply,
            "emotion": emotion,
            "agent": agent,
        }

    def _from_tool(self, name: str, args: Dict[str, Any], agent: str) -> Dict[str, Any]:
        if name == "chat_reply":
            return self._result(
                "none", {}, str(args.get("response_text", "Haan bol.")),
                str(args.get("emotion", "neutral")), agent,
            )

        action = str(args.get("action", "none"))
        if action not in self._actions:
            logger.warning("[Agent Hub] Rejected unknown action: %s", action)
            return self._result("none", {}, "Ye kaam abhi samajh nahi aaya, dobara bol.", "sad", agent)

        params = args.get("params", {})
        if not isinstance(params, dict):
            params = {}
        # Older prompts describe memory as key/value while the persistent
        # fact store accepts free-form text. Keep both formats compatible.
        if action == "remember_user_info" and "info" not in params:
            key = params.get("key", "")
            value = params.get("value", "")
            if key or value:
                params = {"info": f"{key}: {value}".strip(": ")}
        return self._result(
            action,
            params,
            str(args.get("spoken_reply", "Theek hai, kar rahi hoon.")),
            str(args.get("emotion", "neutral")),
            agent,
        )

    def _from_content(self, content: str, agent: str) -> Dict[str, Any]:
        """Normalize strict-JSON responses from models that do not use tools.

        Hardened so Shweta NEVER speaks raw JSON out loud: strips code fences, and
        when the JSON can't be parsed (most often because max_tokens truncated it
        mid-string), it still salvages just the 'reply' sentence — closed OR cut
        off — instead of reading the braces/keys aloud."""
        text = (content or "").strip()

        # Strip ```json ... ``` / ``` ... ``` fences some models wrap JSON in.
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()

        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None

        if not isinstance(parsed, dict):
            # Un-parseable. If it LOOKS like JSON, pull out the reply text so we
            # speak the sentence, never the raw JSON. Otherwise speak it as-is.
            if "{" in text or '"reply"' in text or '"action"' in text:
                # 1) properly-closed "reply":"..." → JSON-unescape it
                m = re.search(r'"(?:reply|spoken_reply)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
                if m:
                    try:
                        spoken = json.loads('"' + m.group(1) + '"')
                    except Exception:
                        spoken = m.group(1).replace('\\"', '"').replace('\\n', ' ')
                    return self._result("none", {}, spoken.strip() or "Haan bol.", "neutral", agent)
                # 2) truncated mid-reply (no closing quote) → salvage to end
                m2 = re.search(r'"(?:reply|spoken_reply)"\s*:\s*"(.*)$', text, flags=re.DOTALL)
                if m2:
                    spoken = m2.group(1).rstrip('"').replace('\\"', '"').replace('\\n', ' ').strip()
                    if spoken:
                        return self._result("none", {}, spoken, "neutral", agent)
                # 3) JSON-ish but nothing usable → safe generic, never raw braces
                return self._result("none", {}, "Haan bol, phir se bata.", "neutral", agent)
            return self._result("none", {}, text or "Haan bol.", "neutral", agent)

        if "action" not in parsed and "name" in parsed:
            parsed["action"] = parsed.get("name")
        return self._from_tool(
            "dispatch_action",
            {
                "action": parsed.get("action", "none"),
                "params": parsed.get("params", {}),
                "spoken_reply": parsed.get("reply", parsed.get("spoken_reply", "Haan bol.")),
                "emotion": parsed.get("emotion", "neutral"),
            },
            agent,
        )

    @staticmethod
    def _call_gemini_hub(api_key: str, model: str, system: str, history: list) -> str:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            msgs = []
            for m in history:
                role = "user" if m["role"] == "user" else "model"
                msgs.append({"role": role, "parts": [{"text": m["content"]}]})
            resp = client.models.generate_content(
                model=model,
                contents=msgs or [{"role": "user", "parts": [{"text": "hello"}]}],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.7,
                    max_output_tokens=420,
                ),
            )
            return resp.text.strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini hub failed: {exc}") from exc

    def think(self, user_input: str, language_manager=None) -> Dict[str, Any]:
        """Route one user message through a specialist agent and normalize its result."""
        text = (user_input or "").strip()
        if not text:
            return self._result("none", {}, "Kuch sunai nahi diya, phir se bol.", "sad", "friend")

        agent = self._select_agent(text)
        self.agent_stats[agent] = self.agent_stats.get(agent, 0) + 1
        self.conversation_history.append({"role": "user", "content": text})
        self.conversation_history = self.conversation_history[-8:]

        # FAST-PATH: trivial commands (time/date/weather/screenshot) answered
        # locally with ZERO LLM tokens — biggest credit + latency saver.
        fp = self._fast_path(text, agent)
        if fp is not None:
            self.conversation_history.append({"role": "assistant", "content": fp["reply"]})
            self.conversation_history = self.conversation_history[-8:]
            logger.info("[Agent Hub] fast-path (no LLM) → action=%s", fp["action"])
            return fp

        if not self._providers:
            response = self._offline(text, agent)
            self.conversation_history.append({"role": "assistant", "content": response["reply"]})
            return response

        system = (
            SYSTEM_PROMPT
            + "\n\n"
            + self._context(agent)
        )
        started = time.time()
        last_error: Optional[Exception] = None

        for provider_name, client, model in self._providers:
            try:
                strict_messages = [{"role": "system", "content": system}] + self.conversation_history

                # Gemini uses native SDK, not OpenAI-compatible
                if provider_name == "gemini_hub":
                    content = self._call_gemini_hub(client, model, system, self.conversation_history)
                    result = self._from_content(content, agent)
                else:
                    response = client.chat.completions.create(
                        model=model,
                        messages=strict_messages,
                        response_format={"type": "json_object"},
                        temperature=0.7,
                        max_tokens=420,
                    )
                    message = response.choices[0].message
                    if message.tool_calls:
                        call = message.tool_calls[0]
                        try:
                            args = json.loads(call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        result = self._from_tool(call.function.name, args, agent)
                    else:
                        result = self._from_content(message.content or "", agent)

                self.conversation_history.append({"role": "assistant", "content": result["reply"]})
                self.conversation_history = self.conversation_history[-8:]
                logger.info(
                    "[Agent Hub] %s/%s completed in %.2fs",
                    agent, provider_name, time.time() - started,
                )
                return result
            except Exception as exc:
                last_error = exc
                exc_str = str(exc)
                if "503" in exc_str:
                    logger.warning("[Agent Hub] %s overloaded (503), skipping", provider_name)
                else:
                    logger.warning("[Agent Hub] %s failed: %s", provider_name, exc)

        logger.error("[Agent Hub] All providers failed: %s", last_error)
        response = self._offline(text, agent)
        self.conversation_history.append({"role": "assistant", "content": response["reply"]})
        return response
