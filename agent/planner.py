"""
Goal planner — converts a user goal into an ordered list of sub-tasks.

Uses LLM to generate a plan; validates that suggested tool names exist in
the registry. Falls back to a single-step "figure it out" plan if LLM fails.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from agent.llm import llm_client
from agent.types import SubTask

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """\
Tu ek expert AI agent planner hai. User ka goal suno aur usse chote, executable steps mein todo karo.

Rules:
1. Max 6 steps. Har step ek clear action hai.
2. Har step ke liye ek tool_hint do — registry mein jo available hai.
3. Steps logical order mein hone chahiye.
4. Agar simple 1-step kaam hai, sirf 1 step do.
5. Reply ONLY valid JSON — {"steps": [{"description": "...", "tool_hint": "..."}]}
6. tool_hint must be a real tool name from the available tools list.

Available tool categories: browser, files, system, apps, comms, trading, music, vision, research, code, productivity, memory.
"""


class _PlanStep(BaseModel):
    description: str
    tool_hint: Optional[str] = None


class _Plan(BaseModel):
    steps: List[_PlanStep] = Field(default_factory=list)


def plan_goal(goal: str, available_tools: Optional[List[str]] = None) -> List[SubTask]:
    """
    Convert a natural language goal into a list of SubTask objects.

    Args:
        goal: User's raw goal text (Hindi/English/Hinglish).
        available_tools: Optional list of tool names to include in the prompt.

    Returns:
        Ordered list of SubTask objects.
    """
    if not llm_client.available:
        return [_single_step(goal)]

    tools_hint = ""
    if available_tools:
        tools_hint = f"\nAvailable tools: {', '.join(available_tools[:40])}"

    messages = [{"role": "user", "content": f"Goal: {goal}"}]
    plan_obj = llm_client.structured_output(
        messages,
        output_model=_Plan,
        system=_PLANNER_SYSTEM + tools_hint,
        temperature=0.2,
    )

    if not plan_obj or not plan_obj.steps:
        logger.warning("[Planner] LLM returned empty plan, using single step")
        return [_single_step(goal)]

    subtasks: List[SubTask] = []
    for i, step in enumerate(plan_obj.steps):
        subtasks.append(SubTask(
            index=i,
            description=step.description,
            tool_hint=_validate_tool_hint(step.tool_hint, available_tools),
        ))

    logger.info("[Planner] Goal '%s' → %d steps: %s",
                goal[:50], len(subtasks),
                " → ".join(s.description[:30] for s in subtasks))
    return subtasks


def _single_step(goal: str) -> SubTask:
    """Fallback: treat the whole goal as one step."""
    return SubTask(index=0, description=goal, tool_hint=None)


def _validate_tool_hint(hint: Optional[str], available: Optional[List[str]]) -> Optional[str]:
    """Return the hint only if it's a known tool name."""
    if not hint:
        return None
    if available and hint in available:
        return hint
    # Try to get it from the registry
    from agent.tools.registry import get_tool
    if get_tool(hint):
        return hint
    return None
