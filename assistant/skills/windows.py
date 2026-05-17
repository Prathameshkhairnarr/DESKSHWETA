"""
Window Management Skill — Snap windows, minimize all, switch apps.
"""

import logging
import time
from typing import Dict

import pyautogui

logger = logging.getLogger(__name__)


def snap_left() -> Dict[str, str]:
    """Snap current window to left half of screen."""
    try:
        pyautogui.hotkey("win", "left")
        return {"status": "success", "message": "Window left mein snap kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def snap_right() -> Dict[str, str]:
    """Snap current window to right half of screen."""
    try:
        pyautogui.hotkey("win", "right")
        return {"status": "success", "message": "Window right mein snap kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def maximize_window() -> Dict[str, str]:
    """Maximize current window."""
    try:
        pyautogui.hotkey("win", "up")
        return {"status": "success", "message": "Window maximize kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def minimize_window() -> Dict[str, str]:
    """Minimize current window."""
    try:
        pyautogui.hotkey("win", "down")
        return {"status": "success", "message": "Window minimize kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def minimize_all() -> Dict[str, str]:
    """Minimize all windows (show desktop)."""
    try:
        pyautogui.hotkey("win", "d")
        return {"status": "success", "message": "Sab windows minimize kar diye — desktop dikh raha hai."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def switch_window() -> Dict[str, str]:
    """Switch to next window (Alt+Tab)."""
    try:
        pyautogui.hotkey("alt", "tab")
        return {"status": "success", "message": "Window switch kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def close_window() -> Dict[str, str]:
    """Close current window (NOT Shweta's window — focuses browser first)."""
    try:
        import time
        import pygetwindow as gw

        # Find browser window and close it (not Shweta's window)
        for win in gw.getAllWindows():
            title = win.title.lower()
            if any(b in title for b in ["brave", "chrome", "firefox", "edge", "youtube"]):
                if win.title:
                    try:
                        win.close()
                        return {"status": "success", "message": "Window band kar diya."}
                    except Exception:
                        continue

        # If no browser found, use Alt+F4 on non-Shweta window
        pyautogui.hotkey("alt", "tab")
        time.sleep(0.4)
        pyautogui.hotkey("alt", "F4")
        return {"status": "success", "message": "Window band kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def task_view() -> Dict[str, str]:
    """Open Task View (all open windows)."""
    try:
        pyautogui.hotkey("win", "tab")
        return {"status": "success", "message": "Task View khol diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
