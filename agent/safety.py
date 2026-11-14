"""
Safety gate for the agent system.

Risk tiers:
  LOW    → auto-execute silently
  MEDIUM → auto-execute but narrate what's happening
  HIGH   → always pause and require voice/button confirmation

Confirmation flow:
  1. Loop emits AgentEvent(CONFIRM_NEEDED) with question
  2. main.py speaks the question and shows a UI button
  3. User says "haan" / "nahi" or clicks button
  4. Orchestrator calls safety_gate.resolve(task_id, confirmed=True/False)
  5. Loop proceeds or aborts
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

from agent.types import RiskLevel

logger = logging.getLogger(__name__)

# Hard limits
MAX_LOOP_STEPS = 20
MAX_TASK_WALL_CLOCK_S = 300   # 5 minutes per task
MAX_RAM_PERCENT = 90          # skip heavy tools when RAM is tight


class SafetyGate:
    """Thread-safe confirmation queue and hard-limit checks."""

    def __init__(self) -> None:
        self._pending: Dict[str, threading.Event] = {}
        self._decisions: Dict[str, bool] = {}
        self._lock = threading.Lock()

    # ── Confirmation management ────────────────────────────────────────────

    def request_confirmation(self, task_id: str, timeout: float = 60.0) -> bool:
        """Block until user confirms or denies (or timeout expires → deny)."""
        event = threading.Event()
        with self._lock:
            self._pending[task_id] = event
            self._decisions.pop(task_id, None)

        logger.info("[Safety] Waiting for confirmation: task=%s (timeout=%.0fs)", task_id, timeout)
        granted = event.wait(timeout=timeout)

        with self._lock:
            decision = self._decisions.pop(task_id, False)
            self._pending.pop(task_id, None)

        if not granted:
            logger.warning("[Safety] Confirmation timeout for task=%s → denied", task_id)
            return False

        logger.info("[Safety] Confirmation resolved: task=%s → %s", task_id, decision)
        return decision

    def resolve(self, task_id: str, confirmed: bool) -> None:
        """Called by main.py when user answers the confirmation question."""
        with self._lock:
            self._decisions[task_id] = confirmed
            event = self._pending.get(task_id)
        if event:
            event.set()
        else:
            logger.warning("[Safety] resolve() called but no pending event for task=%s", task_id)

    def has_pending(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._pending

    # ── Resource checks ───────────────────────────────────────────────────

    @staticmethod
    def check_ram(action: str) -> bool:
        """Return True if it's safe to run a heavy action (RAM not critical)."""
        try:
            import psutil
            ram = psutil.virtual_memory()
            if ram.percent > MAX_RAM_PERCENT:
                logger.warning(
                    "[Safety] RAM at %.0f%% — skipping heavy action '%s'", ram.percent, action
                )
                return False
        except Exception:
            pass
        return True

    # ── Prompt-injection defence ──────────────────────────────────────────

    _INJECTION_PATTERNS = [
        "ignore previous instructions",
        "new instructions:",
        "you are now",
        "disregard all",
        "pretend you are",
        "act as if",
        "system prompt",
        "jailbreak",
    ]

    @classmethod
    def screen_for_injection(cls, text: str) -> bool:
        """Return True (suspicious) if text looks like a prompt injection attempt."""
        lower = text.lower()
        return any(pat in lower for pat in cls._INJECTION_PATTERNS)


# Module-level singleton
safety_gate = SafetyGate()


def is_safe_to_auto_run(risk: RiskLevel, action: str) -> bool:
    """Return True when the tool can run without explicit confirmation."""
    if risk == RiskLevel.LOW:
        return True
    if risk == RiskLevel.MEDIUM:
        # Medium: auto-run but narrate — always safe to auto-run
        return True
    # HIGH → always requires confirmation
    return False


def build_confirm_question(action: str, params: dict) -> str:
    """Generate a short Hindi confirmation question for a HIGH risk tool."""
    action_descriptions: Dict[str, str] = {
        "shutdown_pc": "PC band karna chahti hoon",
        "restart_pc": "PC restart karna chahti hoon",
        "empty_recycle_bin": "Recycle bin khaali karna chahti hoon",
        "delete_file": f"File delete karna chahti hoon: {params.get('filename', '?')}",
        "clear_notes": "Saare notes delete karna chahti hoon",
        "send_email": f"Email bhejna chahti hoon: {params.get('to', '?')}",
        "send_whatsapp": f"WhatsApp bhejna chahti hoon: {params.get('phone', '?')}",
        "send_whatsapp_by_name": f"WhatsApp bhejna chahti hoon: {params.get('name', '?')}",
        "run_command": f"Ye command run karna chahti hoon: {params.get('command', '?')[:60]}",
        "run_python": "Python code run karna chahti hoon",
        "run_powershell": "PowerShell command run karna chahti hoon",
        "send_social_message": f"Message bhejna chahti hoon {params.get('app_name', '?')} pe",
    }
    desc = action_descriptions.get(action, f"'{action}' karna chahti hoon")
    return f"{desc}. Haan ya nahi?"
