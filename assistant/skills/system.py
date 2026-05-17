"""
System Skills for Shweta AI Desktop Assistant.
Handles system-level actions like screenshots, volume, time, clipboard, etc.
"""

import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict

import pyautogui
import pyperclip

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Detect operating system
OS_NAME = platform.system()


def take_screenshot() -> Dict[str, str]:
    """
    Take a screenshot and save it with a timestamp.

    Returns:
        Result dictionary with status, message, and file path.
    """
    try:
        screenshots_dir = PROJECT_ROOT / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = screenshots_dir / filename

        screenshot = pyautogui.screenshot()
        screenshot.save(str(filepath))

        logger.info(f"Screenshot saved: {filepath}")
        return {
            "status": "success",
            "message": f"Screenshot saved: {filename}",
            "path": str(filepath)
        }
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return {"status": "error", "message": str(e)}


def get_time() -> Dict[str, str]:
    """
    Get the current time in Hindi-friendly format.

    Returns:
        Result dictionary with current time.
    """
    now = datetime.now()
    hour = now.hour
    minute = now.minute

    # Hindi period of day
    if 5 <= hour < 12:
        period = "subah"
    elif 12 <= hour < 17:
        period = "dopahar"
    elif 17 <= hour < 21:
        period = "shaam"
    else:
        period = "raat"

    # Convert to 12-hour format
    display_hour = hour % 12 or 12
    time_str = f"{period} ke {display_hour} bajke {minute} minute"
    time_formal = now.strftime("%I:%M %p")

    return {
        "status": "success",
        "message": f"Abhi {time_str} ({time_formal})",
        "time": time_formal
    }


def get_date() -> Dict[str, str]:
    """
    Get the current date.

    Returns:
        Result dictionary with current date.
    """
    now = datetime.now()
    date_str = now.strftime("%d %B %Y, %A")
    return {
        "status": "success",
        "message": f"Aaj ki date hai: {date_str}",
        "date": date_str
    }


def volume_up(steps: int = 5) -> Dict[str, str]:
    """
    Increase system volume.

    Args:
        steps: Number of volume up key presses.

    Returns:
        Result dictionary.
    """
    try:
        for _ in range(steps):
            pyautogui.press("volumeup")
        logger.info(f"Volume increased by {steps} steps.")
        return {"status": "success", "message": f"Volume {steps} steps badha diya."}
    except Exception as e:
        logger.error(f"Volume up failed: {e}")
        return {"status": "error", "message": str(e)}


def volume_down(steps: int = 5) -> Dict[str, str]:
    """
    Decrease system volume.

    Args:
        steps: Number of volume down key presses.

    Returns:
        Result dictionary.
    """
    try:
        for _ in range(steps):
            pyautogui.press("volumedown")
        logger.info(f"Volume decreased by {steps} steps.")
        return {"status": "success", "message": f"Volume {steps} steps kam kar diya."}
    except Exception as e:
        logger.error(f"Volume down failed: {e}")
        return {"status": "error", "message": str(e)}


def volume_mute() -> Dict[str, str]:
    """
    Toggle mute on system volume.

    Returns:
        Result dictionary.
    """
    try:
        pyautogui.press("volumemute")
        logger.info("Volume muted/unmuted.")
        return {"status": "success", "message": "Volume mute toggle kar diya."}
    except Exception as e:
        logger.error(f"Volume mute failed: {e}")
        return {"status": "error", "message": str(e)}


def lock_screen() -> Dict[str, str]:
    """
    Lock the computer screen (OS-specific).

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
        elif OS_NAME == "Linux":
            subprocess.run(["loginctl", "lock-session"])
        else:
            return {"status": "error", "message": "OS not supported for lock."}

        logger.info("Screen locked.")
        return {"status": "success", "message": "Screen lock kar diya."}
    except Exception as e:
        logger.error(f"Lock screen failed: {e}")
        return {"status": "error", "message": str(e)}


def open_file_manager() -> Dict[str, str]:
    """
    Open the system file manager.

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.Popen("explorer")
        elif OS_NAME == "Linux":
            subprocess.Popen(["xdg-open", os.path.expanduser("~")])

        logger.info("File manager opened.")
        return {"status": "success", "message": "File manager khol diya."}
    except Exception as e:
        logger.error(f"File manager failed: {e}")
        return {"status": "error", "message": str(e)}


def type_text(text: str) -> Dict[str, str]:
    """
    Type text using keyboard simulation.

    Args:
        text: Text to type.

    Returns:
        Result dictionary.
    """
    try:
        import time
        time.sleep(0.5)  # Small delay to let user focus on target window
        pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
        logger.info(f"Typed text: {text[:50]}...")
        return {"status": "success", "message": "Text type kar diya."}
    except Exception as e:
        logger.error(f"Type text failed: {e}")
        return {"status": "error", "message": str(e)}


def copy_to_clipboard(text: str) -> Dict[str, str]:
    """
    Copy text to system clipboard.

    Args:
        text: Text to copy.

    Returns:
        Result dictionary.
    """
    try:
        pyperclip.copy(text)
        logger.info(f"Copied to clipboard: {text[:50]}...")
        return {"status": "success", "message": "Clipboard mein copy kar diya."}
    except Exception as e:
        logger.error(f"Clipboard copy failed: {e}")
        return {"status": "error", "message": str(e)}


def empty_recycle_bin() -> Dict[str, str]:
    """Empty the Recycle Bin (Windows)."""
    try:
        if OS_NAME == "Windows":
            # PowerShell command to empty recycle bin
            result = subprocess.run(
                ["powershell", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                capture_output=True, text=True, timeout=15
            )
            return {"status": "success", "message": "Recycle Bin khaali kar diya."}
        else:
            # Linux
            import shutil
            trash_path = os.path.expanduser("~/.local/share/Trash/files")
            if os.path.exists(trash_path):
                shutil.rmtree(trash_path)
                os.makedirs(trash_path)
            return {"status": "success", "message": "Trash khaali kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def run_command(command: str) -> Dict[str, str]:
    """
    Run ONLY whitelisted safe system commands.

    Args:
        command: Shell command to execute.
    """
    # Allowlist of safe commands
    ALLOWED_COMMANDS = [
        "dir", "cls", "echo", "hostname", "whoami",
        "ipconfig", "ping", "systeminfo", "tasklist",
        "date /t", "time /t", "ver",
        "netstat -an", "wmic cpu get name",
        "wmic memorychip get capacity",
    ]

    # Blocked dangerous patterns
    BLOCKED_PATTERNS = [
        "del ", "rm ", "format", "shutdown", "restart",
        "reg ", "regedit", "net user", "net localgroup",
        "powershell", "cmd /c", "taskkill",
        "rmdir", "rd ", "attrib", "icacls",
        "takeown", "cipher", "diskpart",
        "bcdedit", "sfc", "dism",
    ]

    command_lower = command.lower().strip()

    # Check blocked patterns
    for blocked in BLOCKED_PATTERNS:
        if blocked in command_lower:
            return {"status": "error", "message": f"Ye command allowed nahi hai (blocked: '{blocked}')."}

    # Check if command starts with an allowed command
    is_allowed = any(command_lower.startswith(allowed) for allowed in ALLOWED_COMMANDS)
    if not is_allowed:
        return {"status": "error", "message": f"Ye command safe list mein nahi hai. Sirf basic info commands allowed hain."}

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        output = result.stdout.strip() or result.stderr.strip() or "Command executed."
        if len(output) > 200:
            output = output[:200] + "..."
        return {"status": "success", "message": output}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timed out."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def shutdown_pc() -> Dict[str, str]:
    """Shutdown the computer."""
    try:
        if OS_NAME == "Windows":
            subprocess.run("shutdown /s /t 5", shell=True)
        else:
            subprocess.run(["shutdown", "-h", "now"])
        return {"status": "success", "message": "PC 5 second mein band ho jayega."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def restart_pc() -> Dict[str, str]:
    """Restart the computer."""
    try:
        if OS_NAME == "Windows":
            subprocess.run("shutdown /r /t 5", shell=True)
        else:
            subprocess.run(["shutdown", "-r", "now"])
        return {"status": "success", "message": "PC 5 second mein restart hoga."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def sleep_pc() -> Dict[str, str]:
    """Put PC to sleep."""
    try:
        if OS_NAME == "Windows":
            subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return {"status": "success", "message": "PC sleep mode mein ja raha hai."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
