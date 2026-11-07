"""Shared Pydantic types for the Shweta agent system."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"       # auto-execute silently
    MEDIUM = "medium" # auto-execute but narrate to user
    HIGH = "high"     # always pause for voice/button confirmation


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    PLAN_CREATED = "plan_created"
    STEP_START = "step_start"
    STEP_DONE = "step_done"
    STEP_FAILED = "step_failed"
    CONFIRM_NEEDED = "confirm_needed"
    TASK_DONE = "task_done"
    TASK_FAILED = "task_failed"
    VOICE_UPDATE = "voice_update"    # short spoken status narration
    SCREEN_UPDATE = "screen_update"  # update dock/task panel


class ToolResult(BaseModel):
    """Standard envelope returned by every tool call."""
    status: str = "success"           # "success" | "error" | "confirm_needed"
    message: str = ""
    data: Any = None
    artifacts: List[str] = Field(default_factory=list)
    retryable: bool = False

    @classmethod
    def ok(cls, message: str = "", data: Any = None,
           artifacts: Optional[List[str]] = None) -> "ToolResult":
        return cls(status="success", message=message,
                   data=data, artifacts=artifacts or [])

    @classmethod
    def err(cls, message: str, retryable: bool = False) -> "ToolResult":
        return cls(status="error", message=message, retryable=retryable)

    @classmethod
    def confirm(cls, message: str, data: Any = None) -> "ToolResult":
        return cls(status="confirm_needed", message=message, data=data)

    @classmethod
    def from_dc_result(cls, dc_result: Dict[str, Any]) -> "ToolResult":
        """Convert legacy DesktopController result dict to ToolResult."""
        if not isinstance(dc_result, dict):
            return cls.ok(str(dc_result))
        status = dc_result.get("status", "success")
        msg = dc_result.get("message", "")
        data = {k: v for k, v in dc_result.items() if k not in ("status", "message")}
        return cls(status=status, message=msg, data=data or None)


class AgentEvent(BaseModel):
    """Event emitted by the agent loop for UI / voice narration."""
    event_type: EventType
    task_id: Optional[str] = None
    step_index: Optional[int] = None
    tool_name: Optional[str] = None
    message: str = ""
    spoken: str = ""          # Hinglish text to speak aloud (empty = no TTS)
    emotion: str = "neutral"
    data: Any = None
    timestamp: float = Field(default_factory=time.time)


class SubTask(BaseModel):
    """One step inside an AgentTask plan."""
    index: int
    description: str
    tool_hint: Optional[str] = None
    status: str = "pending"   # pending | running | done | failed | skipped
    result: Optional[ToolResult] = None
    retries: int = 0


class AgentTask(BaseModel):
    """Full lifecycle of one autonomous task."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str
    subtasks: List[SubTask] = Field(default_factory=list)
    state: TaskState = TaskState.QUEUED
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    steps_taken: int = 0
    max_steps: int = 20
    final_reply: Optional[str] = None
    emotion: str = "neutral"
    scratchpad: Dict[str, Any] = Field(default_factory=dict)
