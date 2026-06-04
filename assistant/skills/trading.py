"""
Trading Skill — TradingView Chart Automation via pyautogui.
Draws trend lines, rectangles, horizontal lines on TradingView charts.

Uses:
- pyautogui for mouse/keyboard control
- TradingView keyboard shortcuts (Alt+T=trend, Alt+R=rect, Alt+H=horizontal)
- Gemini Vision to analyze chart and find key levels

Flow:
1. Focus TradingView window
2. Select tool via keyboard shortcut
3. Click + drag to draw
4. AI Vision can suggest where to draw (support/resistance levels)
"""

import logging
import time
from typing import Dict, Optional, Tuple

import pyautogui

logger = logging.getLogger(__name__)

# TradingView keyboard shortcuts
TV_SHORTCUTS = {
    "trend_line": ["alt", "t"],
    "horizontal_line": ["alt", "h"],
    "rectangle": ["alt", "r"],
    "fibonacci": ["alt", "f"],
    "crosshair": ["alt", "c"],
    "undo": ["ctrl", "z"],
    "redo": ["ctrl", "y"],
    "delete_drawing": "delete",
    "deselect": "escape",
}


def _focus_tradingview() -> bool:
    """Bring TradingView window to foreground."""
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            title = win.title.lower()
            if "tradingview" in title or "trading view" in title:
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True
    except Exception:
        pass

    # Fallback: Alt+Tab
    pyautogui.hotkey("alt", "tab")
    time.sleep(0.5)
    return True


def _get_chart_center() -> Tuple[int, int]:
    """Get approximate center of the chart area."""
    screen_w, screen_h = pyautogui.size()
    # TradingView chart is usually center-right (left panel is watchlist)
    chart_x = int(screen_w * 0.55)
    chart_y = int(screen_h * 0.45)
    return chart_x, chart_y


def _select_tool(tool: str) -> bool:
    """Select a drawing tool via keyboard shortcut."""
    shortcut = TV_SHORTCUTS.get(tool)
    if not shortcut:
        return False

    if isinstance(shortcut, list):
        pyautogui.hotkey(*shortcut)
    else:
        pyautogui.press(shortcut)
    time.sleep(0.3)
    return True


def open_tradingview(symbol: str = "") -> Dict[str, str]:
    """Open TradingView in browser with optional symbol."""
    try:
        import subprocess
        import webbrowser

        if symbol:
            url = f"https://www.tradingview.com/chart/?symbol={symbol.upper()}"
        else:
            url = "https://www.tradingview.com/chart/"

        BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
        try:
            subprocess.Popen([BRAVE_PATH, url])
        except Exception:
            webbrowser.open(url)

        time.sleep(3)
        return {"status": "success", "message": f"TradingView khol diya{' — ' + symbol.upper() if symbol else ''}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def draw_trend_line(start_x: int = 0, start_y: int = 0, end_x: int = 0, end_y: int = 0) -> Dict[str, str]:
    """
    Draw a trend line on TradingView chart.
    If coordinates not given, draws from left-center to right-center of chart.
    """
    try:
        _focus_tradingview()
        time.sleep(0.3)

        # Select trend line tool
        _select_tool("trend_line")
        time.sleep(0.3)

        # Calculate positions if not provided
        if not start_x or not end_x:
            screen_w, screen_h = pyautogui.size()
            start_x = int(screen_w * 0.3)
            start_y = int(screen_h * 0.5)
            end_x = int(screen_w * 0.7)
            end_y = int(screen_h * 0.4)

        # Draw: click start, drag to end
        pyautogui.click(start_x, start_y)
        time.sleep(0.2)
        pyautogui.click(end_x, end_y)
        time.sleep(0.2)

        # Deselect tool
        pyautogui.press("escape")

        return {"status": "success", "message": "Trend line draw kar diya chart pe!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def draw_horizontal_line(y_position: int = 0) -> Dict[str, str]:
    """Draw a horizontal line at specified Y position (or center)."""
    try:
        _focus_tradingview()
        time.sleep(0.3)

        _select_tool("horizontal_line")
        time.sleep(0.3)

        if not y_position:
            screen_w, screen_h = pyautogui.size()
            y_position = int(screen_h * 0.45)

        chart_x = int(pyautogui.size()[0] * 0.55)
        pyautogui.click(chart_x, y_position)
        time.sleep(0.2)

        pyautogui.press("escape")

        return {"status": "success", "message": "Horizontal line draw kar diya!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def draw_rectangle(start_x: int = 0, start_y: int = 0, end_x: int = 0, end_y: int = 0) -> Dict[str, str]:
    """Draw a rectangle (zone) on TradingView chart."""
    try:
        _focus_tradingview()
        time.sleep(0.3)

        _select_tool("rectangle")
        time.sleep(0.3)

        if not start_x or not end_x:
            screen_w, screen_h = pyautogui.size()
            start_x = int(screen_w * 0.35)
            start_y = int(screen_h * 0.35)
            end_x = int(screen_w * 0.65)
            end_y = int(screen_h * 0.45)

        # Draw rectangle: click start corner, click end corner
        pyautogui.click(start_x, start_y)
        time.sleep(0.2)
        pyautogui.click(end_x, end_y)
        time.sleep(0.2)

        pyautogui.press("escape")

        return {"status": "success", "message": "Rectangle zone draw kar diya!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def draw_fibonacci(start_x: int = 0, start_y: int = 0, end_x: int = 0, end_y: int = 0) -> Dict[str, str]:
    """Draw Fibonacci retracement on chart."""
    try:
        _focus_tradingview()
        time.sleep(0.3)

        _select_tool("fibonacci")
        time.sleep(0.3)

        if not start_x or not end_x:
            screen_w, screen_h = pyautogui.size()
            start_x = int(screen_w * 0.3)
            start_y = int(screen_h * 0.6)
            end_x = int(screen_w * 0.7)
            end_y = int(screen_h * 0.3)

        pyautogui.click(start_x, start_y)
        time.sleep(0.2)
        pyautogui.click(end_x, end_y)
        time.sleep(0.2)

        pyautogui.press("escape")

        return {"status": "success", "message": "Fibonacci retracement draw kar diya!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def undo_drawing() -> Dict[str, str]:
    """Undo last drawing on TradingView."""
    try:
        _focus_tradingview()
        pyautogui.hotkey("ctrl", "z")
        return {"status": "success", "message": "Last drawing undo kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear_drawings() -> Dict[str, str]:
    """Clear all drawings from TradingView chart."""
    try:
        _focus_tradingview()
        time.sleep(0.3)
        # TradingView: right-click on chart → Remove All Drawing Tools
        # Or use keyboard: Alt+Shift+H to hide/show all
        # Safest: Ctrl+Z multiple times
        for _ in range(10):
            pyautogui.hotkey("ctrl", "z")
            time.sleep(0.1)
        return {"status": "success", "message": "Saari drawings hata di chart se."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def mark_support_resistance() -> Dict[str, str]:
    """
    Use AI Vision to analyze chart and mark support/resistance levels.
    If Vision unavailable, draws lines at common chart positions.
    """
    try:
        _focus_tradingview()
        time.sleep(0.5)

        # Try AI Vision first
        try:
            from assistant.skills.vision import read_screen
            result = read_screen(
                "This is a TradingView chart. Identify the 2 most important support levels "
                "and 2 resistance levels. Tell me their approximate Y position as percentage "
                "from top (0%=top, 100%=bottom). Format: support1:XX%, support2:XX%, resistance1:XX%, resistance2:XX%"
            )

            if result.get("status") == "success":
                import re
                response_text = result.get("message", "")
                percentages = re.findall(r'(\d+)%', response_text)

                if len(percentages) >= 2:
                    screen_w, screen_h = pyautogui.size()
                    _select_tool("horizontal_line")
                    time.sleep(0.3)

                    chart_x = int(screen_w * 0.55)
                    for pct_str in percentages[:4]:
                        pct = int(pct_str)
                        y = int(screen_h * (pct / 100.0))
                        pyautogui.click(chart_x, y)
                        time.sleep(0.3)

                    pyautogui.press("escape")
                    return {"status": "success", "message": f"AI ne {len(percentages[:4])} levels mark kar diye!"}
        except Exception:
            pass

        # Fallback: Draw at standard positions (30%, 45%, 55%, 70% of screen height)
        screen_w, screen_h = pyautogui.size()
        _select_tool("horizontal_line")
        time.sleep(0.3)

        chart_x = int(screen_w * 0.55)
        levels = [0.30, 0.42, 0.58, 0.70]  # resistance, resistance, support, support
        for level in levels:
            y = int(screen_h * level)
            pyautogui.click(chart_x, y)
            time.sleep(0.3)

        pyautogui.press("escape")
        return {"status": "success", "message": "4 levels mark kar diye (approximate). Adjust kar le manually."}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def change_symbol(symbol: str) -> Dict[str, str]:
    """Change chart symbol in TradingView."""
    try:
        _focus_tradingview()
        time.sleep(0.3)

        # TradingView: click on symbol search or press /
        pyautogui.press("/")  # Opens symbol search
        time.sleep(0.5)

        # Type symbol
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.typewrite(symbol.upper(), interval=0.03)
        time.sleep(0.5)

        # Press Enter to select first result
        pyautogui.press("enter")
        time.sleep(1)

        return {"status": "success", "message": f"Chart change kar diya — {symbol.upper()}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def change_timeframe(timeframe: str) -> Dict[str, str]:
    """Change chart timeframe. Supports: 1m, 5m, 15m, 1h, 4h, 1d, 1w."""
    try:
        _focus_tradingview()
        time.sleep(0.3)

        # TradingView timeframe shortcuts
        tf_map = {
            "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "2h": "120", "4h": "240",
            "1d": "D", "1w": "W", "1M": "M",
            # Common aliases
            "1min": "1", "5min": "5", "15min": "15",
            "1hour": "60", "4hour": "240",
            "daily": "D", "weekly": "W", "monthly": "M",
        }

        tf_key = tf_map.get(timeframe.lower(), timeframe)

        # Type timeframe directly (TradingView accepts number input for timeframe)
        pyautogui.typewrite(tf_key, interval=0.05)
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)

        return {"status": "success", "message": f"Timeframe change kar diya — {timeframe}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
