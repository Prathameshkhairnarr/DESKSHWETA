"""
Provider-agnostic LLM client for the agent system.

Wraps the same providers as MultiAgentBrain (Groq / OpenAI / GitHub Models / Gemini)
but with native tool-calling, streaming support, and Pydantic structured output.

Provider priority: Groq (fastest, free) → OpenAI/GitHub → Gemini.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ── Models ─────────────────────────────────────────────────────────────────

_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
_GITHUB_MODEL = os.getenv("GITHUB_MODEL", "gpt-4o-mini")
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class LLMResponse(BaseModel):
    """Normalised response from any provider."""
    content: str = ""
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = {}
    provider: str = "unknown"
    latency_ms: int = 0
    finish_reason: str = "stop"


class LLMClient:
    """
    Provider-agnostic LLM client.

    Usage:
        client = LLMClient()
        resp = client.chat(messages, tools=tool_schemas)
        if resp.tool_name:
            # execute tool resp.tool_name(**resp.tool_args)
        else:
            print(resp.content)
    """

    def __init__(self) -> None:
        self._providers: List[tuple[str, Any, str]] = []
        self._build_providers()

    def _build_providers(self) -> None:
        # Gemini first — most reliable, no strict TPM cap
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            self._providers.append(("gemini", gemini_key, _GEMINI_MODEL))
            logger.debug("[LLM] Gemini ready")

        # Groq — fast but 8000 TPM cap
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                from groq import Groq
                self._providers.append(("groq", Groq(api_key=groq_key, max_retries=0), _GROQ_MODEL))
                logger.debug("[LLM] Groq ready")
            except Exception as e:
                logger.warning("[LLM] Groq init failed: %s", e)

        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key:
            try:
                from openai import OpenAI
                self._providers.append(("openai", OpenAI(api_key=openai_key), _OPENAI_MODEL))
                logger.debug("[LLM] OpenAI ready")
            except Exception as e:
                logger.warning("[LLM] OpenAI init failed: %s", e)

        # GitHub Models (OpenAI-compatible)
        github_key = os.getenv("GITHUB_TOKEN", "").strip()
        if github_key:
            try:
                from openai import OpenAI
                self._providers.append((
                    "github",
                    OpenAI(base_url="https://models.inference.ai.azure.com", api_key=github_key),
                    _GITHUB_MODEL,
                ))
                logger.debug("[LLM] GitHub Models ready")
            except Exception as e:
                logger.warning("[LLM] GitHub init failed: %s", e)

        if self._providers:
            logger.info("[LLM] Providers: %s", ", ".join(n for n, _, _ in self._providers))
        else:
            logger.error("[LLM] No providers configured!")

    @property
    def available(self) -> bool:
        return bool(self._providers)

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 600,
    ) -> LLMResponse:
        """
        Send a chat completion request with optional tool schemas.
        Returns the first successful provider response.
        """
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        for provider_name, client, model in self._providers:
            start = time.time()
            try:
                result = self._call_provider(
                    provider_name, client, model,
                    full_messages, tools, temperature, max_tokens,
                )
                if result:
                    result.latency_ms = int((time.time() - start) * 1000)
                    result.provider = provider_name
                    logger.debug("[LLM] %s responded in %dms", provider_name, result.latency_ms)
                    return result
            except Exception as exc:
                exc_str = str(exc)
                # 503 = server overloaded — skip immediately, no retry
                if "503" in exc_str:
                    logger.warning("[LLM] %s overloaded (503), skipping", provider_name)
                    continue
                # On 429 rate-limit: parse retry-after and wait if <= 15s
                if "429" in exc_str and "try again in" in exc_str.lower():
                    import re as _re
                    m = _re.search(r"try again in ([\d.]+)", exc_str, _re.IGNORECASE)
                    wait = float(m.group(1)) if m else 3.0
                    if wait <= 15.0:
                        logger.info("[LLM] %s rate-limited, waiting %.1fs...", provider_name, wait)
                        time.sleep(wait + 0.5)
                        try:
                            result = self._call_provider(
                                provider_name, client, model,
                                full_messages, tools, temperature, max_tokens,
                            )
                            if result:
                                result.latency_ms = int((time.time() - start) * 1000)
                                result.provider = provider_name
                                return result
                        except Exception as exc2:
                            logger.warning("[LLM] %s retry failed: %s", provider_name, exc2)
                logger.warning("[LLM] %s failed: %s", provider_name, exc_str[:120])

        return LLMResponse(content="Abhi AI unavailable hai, thodi der mein try karo.")

    def _call_provider(
        self,
        name: str, client: Any, model: str,
        messages: List[Dict], tools: Optional[List[Dict]],
        temperature: float, max_tokens: int,
    ) -> Optional[LLMResponse]:
        if name == "gemini":
            return self._call_gemini(client, model, messages, temperature, max_tokens)

        # OpenAI-compatible providers (Groq, OpenAI, GitHub)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Groq supports tools but not response_format with tools together
        if tools and name != "groq":
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        elif tools and name == "groq":
            # Groq: use tools without response_format
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        if msg.tool_calls:
            call = msg.tool_calls[0]
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            return LLMResponse(
                tool_name=call.function.name,
                tool_args=args,
                content=msg.content or "",
                finish_reason="tool_calls",
            )

        return LLMResponse(content=msg.content or "", finish_reason=resp.choices[0].finish_reason)

    def _call_gemini(
        self, api_key: str, model: str, messages: List[Dict],
        temperature: float, max_tokens: int,
    ) -> Optional[LLMResponse]:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            # Convert messages to Gemini format
            gemini_msgs = []
            for m in messages:
                if m["role"] == "system":
                    continue  # handled as system_instruction
                role = "user" if m["role"] == "user" else "model"
                gemini_msgs.append({"role": role, "parts": [{"text": m["content"]}]})

            system_text = next((m["content"] for m in messages if m["role"] == "system"), "")

            resp = client.models.generate_content(
                model=model,
                contents=gemini_msgs,
                config=types.GenerateContentConfig(
                    system_instruction=system_text,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return LLMResponse(content=resp.text.strip())
        except Exception as exc:
            logger.warning("[LLM] Gemini failed: %s", exc)
            return None

    def structured_output(
        self,
        messages: List[Dict[str, str]],
        output_model: type,
        system: str = "",
        temperature: float = 0.2,
    ) -> Optional[Any]:
        """
        Request structured output (Pydantic model).
        Falls back to JSON extraction from plain text if provider doesn't support structured output.
        """
        schema_desc = f"\nReturn ONLY valid JSON matching this schema:\n{output_model.model_json_schema()}\n"
        resp = self.chat(
            messages,
            system=system + schema_desc,
            temperature=temperature,
            max_tokens=800,
        )
        text = resp.content.strip()

        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:] if lines[-1] == "```" else lines[1:-1])

        # Find JSON
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            try:
                data = json.loads(json_str)
                return output_model(**data)
            except (json.JSONDecodeError, ValidationError, TypeError):
                pass

        # Try the full text
        try:
            return output_model.model_validate_json(text)
        except Exception:
            logger.warning("[LLM] structured_output parse failed for %s", output_model.__name__)
            return None


# Module-level singleton
llm_client = LLMClient()
