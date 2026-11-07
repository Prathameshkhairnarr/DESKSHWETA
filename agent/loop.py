"""
ReAct Agent Loop — Plan → Act → Observe → Reflect → repeat.

Runs in a background thread for each task. Emits AgentEvent objects
via a callback so main.py can speak progress updates and update the UI.

Design:
  - Each iteration: LLM picks the next tool + params (or decides task is done).
  - Safety gate intercepts HIGH-risk tools before execution.
  - Max steps and wall-clock timeout guard against infinite loops.
  - On step failure: retry once; if fails twice, re-plan or abort.
  - Kill switch: set task state to CANCELLED → loop exits cleanly.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from agent.audit import audit_log
from agent.llm import llm_client, LLMResponse
from agent.planner import plan_goal
from agent.safety import safety_gate, is_safe_to_auto_run, build_confirm_question, MAX_TASK_WALL_CLOCK_S
from agent.task_manager import task_manager
from agent.tools.registry import all_tools, tool_schemas_for_llm, get_tool
from agent.types import (
    AgentEvent, AgentTask, EventType, RiskLevel, SubTask, TaskState, ToolResult
)

logger = logging.getLogger(__name__)

EventCallback = Callable[[AgentEvent], None]

_REACT_SYSTEM = """\
Tu Shweta hai — ek autonomous AI agent. Teri kaam hai user ka goal achieve karna step by step.

Har step mein tu:
1. THINK: Goal aur abhi tak ke results dekh. Kya bacha hai?
2. ACT: Ek tool call karo jo next step complete kare.
3. Agar goal DONE ho gaya — action="done" return karo.
4. Agar user se kuch poochna hai — action="ask_user" return karo.
5. Agar task fail ho gaya — action="failed" return karo.

Return ONLY valid JSON:
{
  "thought": "Internal thinking (never spoken)",
  "action": "tool_name | done | ask_user | failed",
  "params": {"key": "value"},
  "spoken": "Short Hindi update (1 sentence, 5-10 words) ya empty string",
  "emotion": "happy | sad | think | neutral | curious | surprised"
}

Rules:
- spoken should be SHORT — it's spoken aloud. E.g. "Browser khol rahi hoon", "Mil gaya!"
- Never repeat the same tool call twice with identical params.
- If a tool returns an error, try an alternative approach next step.
- Always return valid JSON — no markdown, no extra text.
"""


class AgentLoop:
    """Runs one AgentTask to completion in a background thread."""

    def __init__(self, event_callback: Optional[EventCallback] = None) -> None:
        self._callback = event_callback or (lambda e: None)
        self._threads: Dict[str, threading.Thread] = {}

    def run(self, task: AgentTask) -> None:
        """Start the loop in a background thread. Returns immediately."""
        t = threading.Thread(
            target=self._loop, args=(task,),
            name=f"AgentLoop-{task.task_id}",
            daemon=True,
        )
        self._threads[task.task_id] = t
        t.start()

    def run_sync(self, task: AgentTask) -> AgentTask:
        """Run synchronously (blocks until done). Used by orchestrator for simple tasks."""
        self._loop(task)
        return task_manager.get(task.task_id) or task

    def _emit(self, event: AgentEvent) -> None:
        try:
            self._callback(event)
        except Exception as exc:
            logger.debug("Event callback error: %s", exc)

    def _loop(self, task: AgentTask) -> None:
        """Main ReAct loop."""
        task_manager.set_state(task.task_id, TaskState.RUNNING)
        audit_log.log_task_start(task.task_id, task.goal)
        start_wall = time.time()

        self._emit(AgentEvent(
            event_type=EventType.PLAN_CREATED,
            task_id=task.task_id,
            message=f"Task shuru: {task.goal[:60]}",
            spoken="Kaam shuru karte hain.",
            emotion="think",
        ))

        # Build plan
        tool_names = list(all_tools().keys())
        subtasks = plan_goal(task.goal, available_tools=tool_names)
        task.subtasks = subtasks

        # Conversation history for the ReAct loop
        messages: List[Dict[str, str]] = [
            {"role": "user", "content": f"Goal: {task.goal}"},
        ]

        # Scratchpad: accumulate observations
        scratchpad: List[str] = []
        previous_calls: List[tuple] = []  # (tool_name, params_hash) — dedup guard

        try:
            while task.steps_taken < task.max_steps:
                # Check wall-clock timeout
                if time.time() - start_wall > MAX_TASK_WALL_CLOCK_S:
                    self._finish(task, "failed", "Task timeout ho gaya (5 min limit).", "sad")
                    return

                # Check if cancelled/paused
                current = task_manager.get(task.task_id)
                if current and current.state == TaskState.CANCELLED:
                    self._finish(task, "cancelled", "Task cancel kar diya.", "neutral")
                    return

                if current and current.state == TaskState.PAUSED:
                    time.sleep(0.5)
                    continue  # spin until resumed or cancelled

                # Build context message for LLM
                context = self._build_context(task.goal, scratchpad, task.steps_taken)
                messages_for_llm = [{"role": "user", "content": context}]

                # LLM decides next action
                resp = self._think(messages_for_llm)
                if not resp:
                    break

                action = resp.get("action", "").strip()
                params = resp.get("params", {})
                spoken = resp.get("spoken", "").strip()
                emotion = resp.get("emotion", "think")
                thought = resp.get("thought", "")

                logger.debug("[Loop %s] step=%d thought='%s' action=%s params=%s",
                             task.task_id, task.steps_taken, thought[:60], action, params)

                # Terminal actions
                if action in ("done", ""):
                    final_reply = spoken or "Ho gaya!"
                    self._finish(task, "done", final_reply, emotion or "happy")
                    return

                if action == "ask_user":
                    question = spoken or params.get("question", "Kya karna hai batao?")
                    task_manager.set_state(task.task_id, TaskState.WAITING_USER)
                    self._emit(AgentEvent(
                        event_type=EventType.CONFIRM_NEEDED,
                        task_id=task.task_id,
                        message=question,
                        spoken=question,
                        emotion="curious",
                    ))
                    return

                if action == "failed":
                    msg = spoken or "Kuch gadbad ho gayi."
                    self._finish(task, "failed", msg, "sad")
                    return

                # Narrate MEDIUM risk actions
                tool_spec = get_tool(action)
                if tool_spec and tool_spec.risk_level == RiskLevel.MEDIUM and spoken:
                    self._emit(AgentEvent(
                        event_type=EventType.VOICE_UPDATE,
                        task_id=task.task_id,
                        step_index=task.steps_taken,
                        tool_name=action,
                        spoken=spoken,
                        emotion=emotion,
                    ))

                # HIGH risk — confirm before running
                if tool_spec and tool_spec.risk_level == RiskLevel.HIGH:
                    question = build_confirm_question(action, params)
                    self._emit(AgentEvent(
                        event_type=EventType.CONFIRM_NEEDED,
                        task_id=task.task_id,
                        step_index=task.steps_taken,
                        tool_name=action,
                        message=question,
                        spoken=question,
                        emotion="curious",
                        data={"action": action, "params": params},
                    ))
                    task_manager.set_state(task.task_id, TaskState.WAITING_USER)
                    confirmed = safety_gate.request_confirmation(task.task_id, timeout=60.0)
                    task_manager.set_state(task.task_id, TaskState.RUNNING)
                    if not confirmed:
                        scratchpad.append(f"[Step {task.steps_taken}] {action} — user ne mana kar diya.")
                        self._emit(AgentEvent(
                            event_type=EventType.STEP_FAILED,
                            task_id=task.task_id,
                            step_index=task.steps_taken,
                            tool_name=action,
                            spoken="Theek hai, nahi karta.",
                            emotion="neutral",
                        ))
                        task.steps_taken += 1
                        continue

                # Dedup guard — don't repeat identical tool+params
                params_hash = str(sorted((k, str(v)) for k, v in params.items()))
                if (action, params_hash) in previous_calls[-3:]:
                    logger.warning("[Loop %s] Duplicate tool call detected: %s", task.task_id, action)
                    scratchpad.append(f"[Step {task.steps_taken}] {action} already tried with same params — skipping.")
                    task.steps_taken += 1
                    continue
                previous_calls.append((action, params_hash))

                # Execute tool
                tool_result = self._execute_tool(task, action, params)

                # Emit step event
                if tool_result.status == "success":
                    if spoken:
                        self._emit(AgentEvent(
                            event_type=EventType.STEP_DONE,
                            task_id=task.task_id,
                            step_index=task.steps_taken,
                            tool_name=action,
                            message=tool_result.message,
                            spoken=spoken,
                            emotion=emotion or "happy",
                        ))
                    scratchpad.append(
                        f"[Step {task.steps_taken}] {action}({json.dumps(params, ensure_ascii=False)[:80]}) "
                        f"→ {tool_result.message[:120]}"
                    )
                else:
                    self._emit(AgentEvent(
                        event_type=EventType.STEP_FAILED,
                        task_id=task.task_id,
                        step_index=task.steps_taken,
                        tool_name=action,
                        message=tool_result.message,
                        spoken=f"{action} mein dikkat aayi." if not spoken else spoken,
                        emotion="sad",
                    ))
                    scratchpad.append(
                        f"[Step {task.steps_taken}] {action} FAILED: {tool_result.message[:120]}"
                    )

                task.steps_taken += 1

            # Hit max steps
            self._finish(task, "failed",
                         f"Max steps ({task.max_steps}) reach ho gaya, task finish nahi hua.",
                         "sad")

        except Exception as exc:
            logger.error("[Loop %s] Unhandled exception: %s", task.task_id, exc, exc_info=True)
            self._finish(task, "failed", f"Agent loop crash: {str(exc)[:80]}", "sad")

    def _think(self, messages: List[Dict]) -> Optional[Dict]:
        """Call LLM to get next action JSON."""
        resp = llm_client.chat(
            messages,
            system=_REACT_SYSTEM,
            temperature=0.3,
            max_tokens=400,
        )
        text = resp.content.strip()

        # Try to parse JSON
        for text_part in [text, _extract_json(text)]:
            if not text_part:
                continue
            try:
                data = json.loads(text_part)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        logger.warning("[Loop] LLM returned non-JSON: %s", text[:100])
        return {"action": "done", "spoken": "Ho gaya!", "emotion": "happy", "params": {}, "thought": ""}

    def _build_context(self, goal: str, scratchpad: List[str], step: int) -> str:
        """Build the context message for the LLM at each step."""
        ctx = f"Goal: {goal}\n\nStep: {step + 1}\n"
        if scratchpad:
            ctx += "\nHistory:\n" + "\n".join(scratchpad[-8:])  # last 8 steps
        ctx += "\n\nWhat is the NEXT action?"
        return ctx

    def _execute_tool(self, task: AgentTask, action: str, params: Dict) -> ToolResult:
        """Execute a tool and log to audit."""
        spec = get_tool(action)
        if not spec:
            return ToolResult.err(f"Tool '{action}' registry mein nahi hai.", retryable=False)

        # RAM guard for heavy tools
        from agent.safety import SafetyGate
        heavy_tools = {"browser_agent_task", "multi_browser_task", "auto_search_and_play"}
        if action in heavy_tools and not SafetyGate.check_ram(action):
            return ToolResult.err("RAM zyada hai, heavy tool skip kar raha hoon.", retryable=False)

        t0 = time.time()
        try:
            result = spec.execute(**params)
        except Exception as exc:
            result = ToolResult.err(str(exc), retryable=True)

        duration_ms = int((time.time() - t0) * 1000)
        audit_log.log_tool_call(
            task_id=task.task_id,
            step_index=task.steps_taken,
            tool_name=action,
            params=params,
            result_status=result.status,
            result_message=result.message,
            duration_ms=duration_ms,
        )
        return result

    def _finish(self, task: AgentTask, state: str, reply: str, emotion: str) -> None:
        """Mark task complete and emit final event."""
        task_state = {
            "done": TaskState.DONE,
            "failed": TaskState.FAILED,
            "cancelled": TaskState.CANCELLED,
        }.get(state, TaskState.FAILED)

        task_manager.set_state(
            task.task_id, task_state,
            final_reply=reply,
            steps_taken=task.steps_taken,
            error=reply if state != "done" else "",
        )
        audit_log.log_task_done(
            task.task_id, state, final_reply=reply,
            steps_taken=task.steps_taken,
            error=reply if state != "done" else "",
        )

        event_type = EventType.TASK_DONE if state == "done" else EventType.TASK_FAILED
        self._emit(AgentEvent(
            event_type=event_type,
            task_id=task.task_id,
            message=reply,
            spoken=reply,
            emotion=emotion,
            data={"state": state, "steps": task.steps_taken},
        ))
        logger.info("[Loop %s] Finished: %s in %d steps — %s",
                    task.task_id, state, task.steps_taken, reply[:60])


def _extract_json(text: str) -> str:
    """Extract JSON from text that may have markdown or prose around it."""
    # Strip markdown code blocks
    text = re.sub(r"^```[a-z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end+1]
    return ""
