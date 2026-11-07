"""
Computer-use tool — screenshot + vision + click/type/scroll.
Prefers Windows UI Automation (pywinauto) for reliable element targeting;
falls back to coordinate-based pyautogui when UIA not available.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from agent.types import RiskLevel, ToolResult
from agent.tools.registry import tool

logger = logging.getLogger(__name__)


@tool(
    "screen_read",
    "Screen ka screenshot lekar AI se samajhna — kya dikh raha hai",
    risk_level=RiskLevel.LOW,
    timeout=20,
    category="vision",
    param_descriptions={"question": "Screen ke baare mein kya jaanna hai"},
)
def screen_read(question: str = "Screen pe kya dikh raha hai?") -> ToolResult:
    """Take a screenshot and answer a question about it using vision AI."""
    try:
        from assistant.skills import vision
        result = vision.read_screen(question)
        return ToolResult.from_dc_result(result)
    except Exception as exc:
        return ToolResult.err(f"Screen read failed: {exc}", retryable=True)


@tool(
    "click_element",
    "Screen pe kisi element ko text se dhundh ke click karna (UI Automation)",
    risk_level=RiskLevel.MEDIUM,
    timeout=15,
    category="vision",
    param_descriptions={
        "app_title": "Window title jisme click karna hai",
        "element_text": "Element ka text ya label",
    },
)
def click_element(app_title: str, element_text: str) -> ToolResult:
    """Click a UI element by text using Windows UI Automation (pywinauto)."""
    try:
        from pywinauto import Application, Desktop  # type: ignore
        try:
            app = Application(backend="uia").connect(title_re=f".*{app_title}.*", timeout=5)
            win = app.top_window()
            ctrl = win.child_window(title=element_text, found_index=0)
            ctrl.set_focus()
            ctrl.click_input()
            return ToolResult.ok(message=f"'{element_text}' pe click kar diya '{app_title}' mein.")
        except Exception as uia_err:
            logger.debug("UIA click failed (%s), trying pyautogui locate", uia_err)
            # Fallback: pyautogui image-less click via screenshot + vision
            return _pyautogui_click_by_text(element_text)
    except ImportError:
        return _pyautogui_click_by_text(element_text)


def _pyautogui_click_by_text(element_text: str) -> ToolResult:
    """Fallback: use pyautogui + PIL to find text on screen and click it."""
    try:
        import pyautogui
        import pytesseract  # type: ignore
        from PIL import Image

        screenshot = pyautogui.screenshot()
        # Try to find the text bounding box
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
        for i, word in enumerate(data["text"]):
            if element_text.lower() in word.lower():
                x = data["left"][i] + data["width"][i] // 2
                y = data["top"][i] + data["height"][i] // 2
                pyautogui.click(x, y)
                return ToolResult.ok(message=f"'{element_text}' pe click kar diya ({x},{y})")
        return ToolResult.err(f"'{element_text}' screen pe nahi mila.")
    except ImportError:
        return ToolResult.err("pywinauto aur pytesseract dono nahi milé. UI automation available nahi.")
    except Exception as exc:
        return ToolResult.err(f"Click failed: {exc}", retryable=True)


@tool(
    "click_coords",
    "Screen pe specific coordinates pe click karna",
    risk_level=RiskLevel.MEDIUM,
    timeout=5,
    category="vision",
    param_descriptions={"x": "X coordinate (pixels from left)", "y": "Y coordinate (pixels from top)"},
)
def click_coords(x: int, y: int) -> ToolResult:
    """Click at specific screen coordinates."""
    try:
        import pyautogui
        pyautogui.click(x, y)
        return ToolResult.ok(message=f"Click kar diya ({x}, {y}) pe.")
    except Exception as exc:
        return ToolResult.err(f"Click failed: {exc}", retryable=True)


@tool(
    "type_text_at_cursor",
    "Cursor jahan hai wahan text type karna",
    risk_level=RiskLevel.MEDIUM,
    timeout=10,
    category="vision",
    param_descriptions={"text": "Jo type karna hai", "press_enter": "Baad mein Enter press karna hai?"},
)
def type_text_at_cursor(text: str, press_enter: bool = False) -> ToolResult:
    """Type text at the current cursor position."""
    try:
        import pyautogui
        pyautogui.write(text, interval=0.02)
        if press_enter:
            pyautogui.press("enter")
        return ToolResult.ok(message=f"Type kar diya: '{text[:40]}{'...' if len(text) > 40 else ''}'")
    except Exception as exc:
        return ToolResult.err(f"Type failed: {exc}", retryable=True)


@tool(
    "scroll_at",
    "Screen ke kisi location pe scroll karna",
    risk_level=RiskLevel.LOW,
    timeout=5,
    category="vision",
    param_descriptions={
        "x": "X coordinate", "y": "Y coordinate",
        "clicks": "Scroll wheel clicks (negative = down, positive = up)",
    },
)
def scroll_at(x: int, y: int, clicks: int = -3) -> ToolResult:
    """Scroll at specific screen coordinates."""
    try:
        import pyautogui
        pyautogui.scroll(clicks, x=x, y=y)
        direction = "upar" if clicks > 0 else "neeche"
        return ToolResult.ok(message=f"Scroll kar diya {direction} ({x},{y})")
    except Exception as exc:
        return ToolResult.err(f"Scroll failed: {exc}", retryable=True)


@tool(
    "hotkey",
    "Keyboard shortcut / hotkey press karna",
    risk_level=RiskLevel.MEDIUM,
    timeout=5,
    category="vision",
    param_descriptions={"keys": "Keys ka combination e.g. 'ctrl+c', 'alt+f4', 'win+d'"},
)
def hotkey(keys: str) -> ToolResult:
    """Press a keyboard hotkey combination."""
    try:
        import pyautogui
        pyautogui.hotkey(*keys.split("+"))
        return ToolResult.ok(message=f"Hotkey press kar diya: {keys}")
    except Exception as exc:
        return ToolResult.err(f"Hotkey failed: {exc}", retryable=True)


@tool(
    "find_window",
    "Khuli hui windows list karna ya kisi specific window ko dhundna",
    risk_level=RiskLevel.LOW,
    timeout=5,
    category="vision",
    param_descriptions={"title_contains": "Window title ka part (empty = saari windows)"},
)
def find_window(title_contains: str = "") -> ToolResult:
    """List open windows or find one by title."""
    try:
        import pygetwindow as gw  # type: ignore
        windows = gw.getAllTitles()
        windows = [w for w in windows if w.strip()]
        if title_contains:
            windows = [w for w in windows if title_contains.lower() in w.lower()]
        if not windows:
            return ToolResult.ok(message="Koi matching window nahi mili.", data={"windows": []})
        summary = "\n".join(f"  • {w}" for w in windows[:20])
        return ToolResult.ok(message=f"Open windows:\n{summary}", data={"windows": windows})
    except ImportError:
        return ToolResult.err("pygetwindow install nahi hai.")
    except Exception as exc:
        return ToolResult.err(f"Window list failed: {exc}", retryable=True)
