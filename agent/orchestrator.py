"""
Agent Orchestrator — the new brain entry point.

Replaces the old MultiAgentBrain.think() for action/multi-step intents while
keeping the old fast-path for pure small-talk (latency < 1s to first audio).

Flow:
  1. Screen for prompt injection (safety)
  2. Intent classify: smalltalk | single_action | multi_step | control
  3. smalltalk → chat_reply (direct, no agent loop, < 1s)
  4. single_action / multi_step → create AgentTask → start AgentLoop
  5. Control commands ("ruk ja", "cancel") → task control
  6. All results come back via event callback (voice narration + UI update)

Compatible return shape for main.py:
  {"reply": str, "emotion": str, "action": "none"|"agent_task",
   "task_id": str|None, "agent": str}
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from agent.audit import audit_log
from agent.loop import AgentLoop
from agent.safety import safety_gate
from agent.task_manager import task_manager
from agent.tools.registry import all_tools
from agent.types import AgentEvent, AgentTask, EventType, TaskState

logger = logging.getLogger(__name__)

EventCallback = Callable[[AgentEvent], None]


# ── Intent classifier ─────────────────────────────────────────────────────

_SMALLTALK_PATTERNS = [
    "kya haal", "kaisa hoon", "kya kar rahi", "baat karo",
    "joke", "kahani", "batao kuch", "hi ", "hello", "hey shweta",
    "kya lag raha", "aaj kaisa", "how are you", "what's up",
    "mera nam", "mera naam", "acha chal",
]

_CONTROL_PATTERNS = {
    "pause": ["ruk ja", "ruko", "pause karo", "wait"],
    "resume": ["chalu karo", "resume", "aage badho"],
    "cancel": ["cancel", "band kar", "chhod de", "mat kar"],
    "stop_all": ["sab kuch rok", "stop everything", "sab band"],
    "task_status": ["task status", "kya chal raha", "kya ho raha"],
    "what_did": ["kya kiya", "kya hua", "summary do"],
}

_MULTI_STEP_SIGNALS = [
    # Hindi conjunctions / sequencing
    "aur phir", "uske baad", "then", "aur bhi", "saath mein",
    "pehle", "baad mein", "step by step", "ek ek karke",
    # English "and" + action combos — most common multi-step pattern
    " and ", " and then ", "open and", "and write", "and type",
    "and send", "and save", "and search", "and find", "and play",
    "and close", "and delete", "and move", "and copy", "and rename",
    # Hindi equivalents
    "aur likho", "aur type", "aur bhejo", "aur save", "aur kholo",
    "aur band", "aur dhundho", " aur ", "likho", "type karo",
    # Task keywords implying multiple steps
    "compare", "dhundh ke", "rename karke", "organize",
    "kal ki flight", "3 laptops", "fibonacci", "support resistance",
    "zip bana", "pdfs ko", "research", "summarize",
]


def classify_intent(text: str) -> str:
    """
    Fast heuristic intent classifier.
    Returns: "smalltalk" | "single_action" | "multi_step" | "control"
    """
    lower = text.lower().strip()

    # Control commands
    for ctype, patterns in _CONTROL_PATTERNS.items():
        if any(p in lower for p in patterns):
            return f"control_{ctype}"

    # Smalltalk — no tool needed
    if any(p in lower for p in _SMALLTALK_PATTERNS):
        # Only if no action words present
        action_words = ["kholo", "open", "play", "search", "dhundh", "bana", "delete",
                        "file", "folder", "weather", "mausam", "gaana", "music",
                        "screenshot", "volume", "timer", "note", "send", "email"]
        if not any(w in lower for w in action_words):
            return "smalltalk"

    # Multi-step signals
    if any(p in lower for p in _MULTI_STEP_SIGNALS) or len(lower.split()) > 20:
        return "multi_step"

    return "single_action"


class AgentOrchestrator:
    """
    Main entry point for all user input.

    Instantiate once in main.py and call process(text) for every user utterance.
    """

    def __init__(
        self,
        multi_agent_brain=None,       # Legacy MultiAgentBrain — used for smalltalk
        desktop_controller=None,       # DesktopController — registered as tools
        event_callback: Optional[EventCallback] = None,
    ) -> None:
        self._brain = multi_agent_brain
        self._dc = desktop_controller
        self._event_cb = event_callback or (lambda e: None)
        self._loop = AgentLoop(event_callback=self._on_loop_event)
        self._registered = False

        # Register all desktop tools when dc is available
        if desktop_controller:
            self._register_tools()

        # Also register power tools (research, file_ops, code_exec, computer_use)
        self._register_power_tools()

        logger.info("[Orchestrator] Ready. Tools registered: %d", len(all_tools()))

    def _register_tools(self) -> None:
        """Register desktop tools from DesktopController."""
        if self._registered:
            return
        try:
            from agent.tools.desktop import register_desktop_tools
            register_desktop_tools(self._dc)
            self._registered = True
        except Exception as exc:
            logger.error("[Orchestrator] register_desktop_tools failed: %s", exc)

    def _register_power_tools(self) -> None:
        """Import power tool modules so their @tool decorators run."""
        for module_path in [
            "agent.tools.research",
            "agent.tools.file_ops",
            "agent.tools.code_exec",
            "agent.tools.computer_use",
        ]:
            try:
                __import__(module_path)
            except Exception as exc:
                logger.debug("Power tool module %s import warning: %s", module_path, exc)

    # ── Main entry point ──────────────────────────────────────────────────

    def process(self, text: str, language_manager=None) -> Dict[str, Any]:
        """
        Process one user utterance.

        Returns a dict compatible with what main.py previously expected from
        MultiAgentBrain.think():
          {"reply": str, "emotion": str, "action": "none"|"agent_task",
           "task_id": str|None, "params": {}, "agent": str}
        """
        text = (text or "").strip()
        if not text:
            return self._reply("Kuch sunai nahi diya, phir se bol.", "sad")

        # Safety: prompt injection check
        from agent.safety import SafetyGate
        if SafetyGate.screen_for_injection(text):
            logger.warning("[Orchestrator] Potential prompt injection: %s", text[:80])
            return self._reply(
                "Ye command kisi bahari source se lag raha hai, main execute nahi karuungi.",
                "angry",
            )

        # Log voice command
        audit_log.log_voice_command(text)

        # Classify intent
        intent = classify_intent(text)
        logger.info("[Orchestrator] intent=%s text='%s'", intent, text[:60])

        # ── Control commands ───────────────────────────────────────────────
        if intent.startswith("control_"):
            return self._handle_control(intent, text)

        # ── Smalltalk — route to old brain (fast path, < 1s) ──────────────
        if intent == "smalltalk" and self._brain:
            try:
                result = self._brain.think(text, language_manager)
                result["agent"] = "friend"
                return result
            except Exception as exc:
                logger.warning("[Orchestrator] brain.think failed: %s", exc)

        # ── Single action or multi-step — agent loop ───────────────────────
        # For simple single-action tasks we still try the old brain first
        # (it's faster and already well-tuned). We fall back to the loop if
        # the brain returns action="none" but the intent isn't smalltalk.
        if intent == "single_action" and self._brain:
            try:
                result = self._brain.think(text, language_manager)
                action = result.get("action", "none")
                if action != "none":
                    # Old brain handled it — return directly (fast path)
                    result["agent"] = "desktop"
                    return result
                # Brain gave no action for a non-smalltalk intent → agent loop
            except Exception as exc:
                logger.warning("[Orchestrator] brain.think failed: %s", exc)

        # Agent loop path (single_action with no brain result, or multi_step)
        return self._start_agent_task(text, intent=intent)

    def _start_agent_task(self, goal: str, intent: str = "") -> Dict[str, Any]:
        """Create a task and start the ReAct loop in background."""
        task = task_manager.create(goal)

        if not intent:
            intent = classify_intent(goal)

        # For multi-step tasks run async; for single-step try sync first
        if intent == "single_action":
            # Run synchronously with a short timeout (5 steps max)
            task.max_steps = 5
            self._loop.run_sync(task)
            updated = task_manager.get(task.task_id)
            if updated and updated.state == TaskState.DONE:
                return self._reply(
                    updated.final_reply or "Ho gaya!",
                    updated.emotion or "happy",
                    task_id=task.task_id,
                    action="agent_task",
                )
            # Fallback reply even if failed
            final = (updated.final_reply if updated else None) or "Kuch gadbad ho gayi."
            return self._reply(final, "sad", task_id=task.task_id)
        else:
            # Multi-step: start async, give immediate spoken update
            self._loop.run(task)
            return self._reply(
                "Theek hai, kaam shuru kar rahi hoon. Thodi der mein bataungi.",
                "think",
                task_id=task.task_id,
                action="agent_task",
            )

    def _handle_control(self, intent: str, text: str) -> Dict[str, Any]:
        """Handle task control voice commands."""
        active = task_manager.list_active()

        if intent == "control_pause":
            for t in active:
                if task_manager.pause(t.task_id):
                    return self._reply("Ruk gayi, jab kahogi tab aage badhungi.", "relaxed")
            return self._reply("Koi active task nahi hai rokne ke liye.", "neutral")

        if intent == "control_resume":
            for t in active:
                if task_manager.resume(t.task_id):
                    return self._reply("Chal rahi hoon!", "happy")
            return self._reply("Koi paused task nahi hai.", "neutral")

        if intent == "control_cancel":
            # Try to find which task from text
            cancelled = []
            for t in active:
                if any(kw in text.lower() for kw in t.goal.lower().split()[:3]):
                    task_manager.cancel(t.task_id)
                    cancelled.append(t.task_id)
            if not cancelled and active:
                # Cancel most recent
                task_manager.cancel(active[-1].task_id)
                cancelled.append(active[-1].task_id)
            if cancelled:
                return self._reply("Cancel kar diya.", "neutral")
            return self._reply("Koi active task nahi tha.", "neutral")

        if intent == "control_stop_all":
            for t in active:
                task_manager.cancel(t.task_id)
            return self._reply("Sab kuch rok diya.", "neutral")

        if intent == "control_task_status":
            summary = task_manager.status_summary()
            return self._reply(summary, "neutral")

        if intent == "control_what_did":
            summary = audit_log.recent_summary(5)
            return self._reply(summary, "neutral")

        return self._reply("Control command samajh nahi aayi.", "neutral")

    def set_event_callback(self, cb: EventCallback) -> None:
        """Register callback for agent events (called from main.py)."""
        self._event_cb = cb
        self._loop._callback = self._on_loop_event

    def _on_loop_event(self, event: AgentEvent) -> None:
        """Forward loop events to the registered callback."""
        try:
            self._event_cb(event)
        except Exception as exc:
            logger.debug("Orchestrator event forward error: %s", exc)

    def resolve_confirmation(self, task_id: str, confirmed: bool) -> None:
        """Called by main.py when user answers a HIGH-risk confirmation."""
        safety_gate.resolve(task_id, confirmed)

    @staticmethod
    def _reply(
        text: str,
        emotion: str = "neutral",
        task_id: Optional[str] = None,
        action: str = "none",
    ) -> Dict[str, Any]:
        return {
            "reply": text,
            "emotion": emotion,
            "action": action,
            "params": {},
            "task_id": task_id,
            "agent": "orchestrator",
        }
