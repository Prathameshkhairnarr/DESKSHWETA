"""
Sandboxed code execution tool — Python and PowerShell.
Runs in an isolated temp directory with hard timeout.
Never executes in the project directory.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from agent.types import RiskLevel, ToolResult
from agent.tools.registry import tool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15   # seconds
_MAX_OUTPUT_CHARS = 4000


@tool(
    "run_python",
    "Python code run karna (sandboxed temp folder mein, timeout ke saath)",
    risk_level=RiskLevel.HIGH,
    timeout=20,
    needs_confirmation=True,
    category="code",
    param_descriptions={
        "code": "Python code jo run karna hai",
        "timeout": "Max seconds (default 15)",
    },
)
def run_python(code: str, timeout: int = _DEFAULT_TIMEOUT) -> ToolResult:
    """Execute Python code in an isolated temp directory."""
    timeout = min(max(timeout, 1), 60)  # clamp 1–60s

    # Prompt-injection guard: reject if code tries to access secrets
    _danger_patterns = [
        ".env", "GROQ_API_KEY", "AWS_SECRET", "OPENAI_API_KEY",
        "keyring", "winreg", "os.environ",
        "subprocess.Popen", "os.system",
    ]
    for pat in _danger_patterns:
        if pat in code:
            return ToolResult.err(
                f"Code mein suspicious pattern mila: '{pat}'. Execute nahi karuungi.",
                retryable=False,
            )

    with tempfile.TemporaryDirectory(prefix="shweta_py_") as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code, encoding="utf-8")

        try:
            result = subprocess.run(
                [sys.executable, "-I", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,  # always run in temp dir, never project dir
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                    "TEMP": tmpdir,
                    "TMP": tmpdir,
                },
            )
            stdout = result.stdout[:_MAX_OUTPUT_CHARS]
            stderr = result.stderr[:_MAX_OUTPUT_CHARS]

            if result.returncode == 0:
                msg = stdout or "Code chal gaya, koi output nahi."
                return ToolResult.ok(message=msg, data={"returncode": 0, "stderr": stderr})
            else:
                return ToolResult.err(
                    f"Code error (exit {result.returncode}):\n{stderr or stdout}",
                    retryable=False,
                )

        except subprocess.TimeoutExpired:
            return ToolResult.err(
                f"Code {timeout}s mein khatam nahi hua (timeout).", retryable=False
            )
        except Exception as exc:
            return ToolResult.err(f"Execution failed: {exc}", retryable=False)


@tool(
    "run_powershell",
    "PowerShell command ya script run karna (sandboxed, requires confirmation)",
    risk_level=RiskLevel.HIGH,
    timeout=30,
    needs_confirmation=True,
    category="code",
    param_descriptions={
        "command": "PowerShell command ya script",
        "timeout": "Max seconds (default 15)",
    },
)
def run_powershell(command: str, timeout: int = _DEFAULT_TIMEOUT) -> ToolResult:
    """Execute a PowerShell command in a temp working directory."""
    timeout = min(max(timeout, 1), 60)

    _danger_patterns = [
        "Remove-Item", "Format-", "rm -rf", "del /f", "reg delete",
        "net user", "net localgroup", "takeown", "icacls",
        "Invoke-Expression", "iex ", "DownloadString",
    ]
    for pat in _danger_patterns:
        if pat.lower() in command.lower():
            return ToolResult.err(
                f"PowerShell command mein dangerous pattern: '{pat}'. Confirm nahi kar sakti.",
                retryable=False,
            )

    with tempfile.TemporaryDirectory(prefix="shweta_ps_") as tmpdir:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
            stdout = result.stdout[:_MAX_OUTPUT_CHARS]
            stderr = result.stderr[:_MAX_OUTPUT_CHARS]

            if result.returncode == 0:
                msg = stdout or "Command chal gaya."
                return ToolResult.ok(message=msg, data={"returncode": 0})
            else:
                return ToolResult.err(
                    f"PowerShell error:\n{stderr or stdout}", retryable=False
                )

        except subprocess.TimeoutExpired:
            return ToolResult.err(f"Command {timeout}s mein khatam nahi hua.", retryable=False)
        except FileNotFoundError:
            return ToolResult.err("PowerShell nahi mila system pe.", retryable=False)
        except Exception as exc:
            return ToolResult.err(f"Execution failed: {exc}", retryable=False)
