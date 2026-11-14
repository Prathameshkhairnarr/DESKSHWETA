"""
Shweta Agent System — autonomous multi-step task execution.

Entry point: AgentOrchestrator (agent.orchestrator)
  - Intent classify → simple chat OR agent loop
  - AgentLoop runs ReAct (Plan→Act→Observe→Reflect)
  - All tools registered in agent.tools.registry
  - Tasks persisted in SQLite via agent.task_manager
  - Full audit trail in agent.audit
"""

from agent.types import RiskLevel, TaskState, ToolResult, AgentEvent, EventType  # noqa: F401
