"""
Tool registry — single source of truth for all agent-callable tools.

Usage:
    from agent.tools.registry import tool, get_tool, all_tools, tool_schemas_for_llm

    @tool("open_youtube", "YouTube open karna", risk_level=RiskLevel.LOW, timeout=15)
    def open_youtube() -> ToolResult:
        ...
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

from agent.types import RiskLevel, ToolResult

logger = logging.getLogger(__name__)

# Global registry: name → ToolSpec
_REGISTRY: Dict[str, "ToolSpec"] = {}


class ToolSpec:
    """Metadata + callable for one registered tool."""

    def __init__(
        self,
        name: str,
        fn: Callable,
        description: str,
        risk_level: RiskLevel,
        timeout: int,
        needs_confirmation: bool,
        json_schema: Dict[str, Any],
        category: str = "general",
    ) -> None:
        self.name = name
        self.fn = fn
        self.description = description
        self.risk_level = risk_level
        self.timeout = timeout
        self.needs_confirmation = needs_confirmation or (risk_level == RiskLevel.HIGH)
        self.json_schema = json_schema
        self.category = category

    def execute(self, **kwargs: Any) -> ToolResult:
        """Call the tool function and normalise its return value."""
        try:
            result = self.fn(**kwargs)
            if isinstance(result, ToolResult):
                return result
            if isinstance(result, dict):
                return ToolResult.from_dc_result(result)
            return ToolResult.ok(str(result) if result else "")
        except Exception as exc:
            logger.error("Tool %s raised: %s", self.name, exc, exc_info=True)
            return ToolResult.err(str(exc), retryable=True)


def _py_type_to_json(ann: Any) -> str:
    mapping = {int: "integer", float: "number", bool: "boolean",
               str: "string", list: "array", dict: "object"}
    return mapping.get(ann, "string")


def _build_schema(fn: Callable, param_descriptions: Dict[str, str]) -> Dict[str, Any]:
    """Auto-build an OpenAI-compatible JSON schema from type annotations."""
    sig = inspect.signature(fn)
    props: Dict[str, Any] = {}
    required: List[str] = []

    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            ann = str
        # Handle Optional[X] → X
        origin = getattr(ann, "__origin__", None)
        if origin is type(None):
            ann = str
        json_type = _py_type_to_json(ann)
        props[pname] = {
            "type": json_type,
            "description": param_descriptions.get(pname, pname.replace("_", " ")),
        }
        if param.default is inspect.Parameter.empty:
            required.append(pname)

    return {"type": "object", "properties": props, "required": required}


def tool(
    name: str,
    description: str,
    *,
    risk_level: RiskLevel = RiskLevel.LOW,
    timeout: int = 30,
    needs_confirmation: bool = False,
    param_descriptions: Optional[Dict[str, str]] = None,
    category: str = "general",
    json_schema: Optional[Dict[str, Any]] = None,
) -> Callable:
    """Decorator: registers the function as a named agent tool."""
    def decorator(fn: Callable) -> Callable:
        schema = json_schema or _build_schema(fn, param_descriptions or {})
        spec = ToolSpec(
            name=name, fn=fn, description=description,
            risk_level=risk_level, timeout=timeout,
            needs_confirmation=needs_confirmation,
            json_schema=schema, category=category,
        )
        _REGISTRY[name] = spec
        logger.debug("Registered tool: %s [%s/%s]", name, category, risk_level.value)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def register_function(
    fn: Callable,
    name: str,
    description: str,
    risk_level: RiskLevel = RiskLevel.LOW,
    timeout: int = 30,
    needs_confirmation: bool = False,
    json_schema: Optional[Dict[str, Any]] = None,
    category: str = "general",
) -> ToolSpec:
    """Register an arbitrary callable as a tool (no decorator needed)."""
    schema = json_schema or {"type": "object", "properties": {}, "required": []}
    spec = ToolSpec(
        name=name, fn=fn, description=description,
        risk_level=risk_level, timeout=timeout,
        needs_confirmation=needs_confirmation,
        json_schema=schema, category=category,
    )
    _REGISTRY[name] = spec
    return spec


def get_tool(name: str) -> Optional[ToolSpec]:
    return _REGISTRY.get(name)


def all_tools() -> Dict[str, ToolSpec]:
    return dict(_REGISTRY)


def tool_schemas_for_llm(names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Return OpenAI function-call schemas for the given tools (all if names=None)."""
    items = (
        list(_REGISTRY.items()) if names is None
        else [(n, _REGISTRY[n]) for n in names if n in _REGISTRY]
    )
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.json_schema,
            },
        }
        for _, spec in items
    ]


def tool_catalog_markdown() -> str:
    """Auto-generate a markdown table of all registered tools."""
    lines = [
        "| Tool | Category | Risk | Description |",
        "|------|----------|------|-------------|",
    ]
    for spec in sorted(_REGISTRY.values(), key=lambda s: (s.category, s.name)):
        lines.append(
            f"| `{spec.name}` | {spec.category} | {spec.risk_level.value} | {spec.description} |"
        )
    return "\n".join(lines)
