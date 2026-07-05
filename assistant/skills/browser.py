"""
Browser Skills for Shweta AI Desktop Assistant.
Handles web browsing, YouTube playback, and media controls.
All URLs open in existing browser as new tab (no new window).
"""

import logging
import re
import subprocess
import urllib.parse
import webbrowser
from typing import Dict

import pyautogui
import requests as req

from config import BROWSER_PATH

logger = logging.getLogger(__name__)

def _open_url(url: str) -> None:
    """Open URL in existing browser as new tab."""
    try:
        subprocess.Popen([BROWSER_PATH, url])
    except Exception:
        # Fallback to default browser
        webbrowser.open(url)


def open_youtube() -> Dict[str, str]:
    """Open YouTube in existing browser."""
    try:
        _open_url("https://www.youtube.com")
        return {"status": "success", "message": "YouTube opened."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def open_google(query: str = "") -> Dict[str, str]:
    """Open Google search."""
    try:
        if query:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://www.google.com/search?q={encoded_query}"
        else:
            url = "https://www.google.com"
        _open_url(url)
        return {"status": "success", "message": f"Google search opened for: {query}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def open_website(url: str) -> Dict[str, str]:
    """Open a specific website URL."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        _open_url(url)
        return {"status": "success", "message": f"Opened: {url}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def play_youtube(query: str) -> Dict[str, str]:
    """
    Play first YouTube video for a search query.
    Fetches YouTube search page, extracts first video ID, opens directly.

    Args:
        query: Video search query.

    Returns:
        Result dictionary with status and message.
    """
    try:
        encoded_query = urllib.parse.quote_plus(query)

        # Try to get the first video URL using YouTube's search page
        try:
            search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = req.get(search_url, headers=headers, timeout=8)
            match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
            if match:
                video_id = match.group(1)
                play_url = f"https://www.youtube.com/watch?v={video_id}"
                _open_url(play_url)
                logger.info(f"Playing first video: {play_url}")
                return {"status": "success", "message": f"Playing: {query}"}
        except Exception as e:
            logger.warning(f"Direct video fetch failed, opening search: {e}")

        # Fallback: just open search results
        url = f"https://www.youtube.com/results?search_query={encoded_query}&sp=EgIQAQ%3D%3D"
        _open_url(url)
        logger.info(f"YouTube search opened: {query}")
        return {"status": "success", "message": f"YouTube search opened for: {query}"}

    except Exception as e:
        logger.error(f"Failed to play YouTube: {e}")
        return {"status": "error", "message": str(e)}


# ---------- HELPER: Focus browser window before sending keys ----------

def _focus_browser() -> None:
    """Bring the browser window to foreground."""
    import time
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            title = win.title.lower()
            if any(b in title for b in ["brave", "chrome", "firefox", "edge", "youtube", "opera"]):
                if win.title:
                    try:
                        if win.isMinimized:
                            win.restore()
                        win.activate()
                        time.sleep(0.4)
                        return
                    except Exception:
                        continue
    except Exception:
        pass

    # Fallback
    pyautogui.hotkey("alt", "tab")
    import time
    time.sleep(0.5)


# ---------- MEDIA / BROWSER CONTROLS ----------

def media_play_pause() -> Dict[str, str]:
    """Play or pause the current video/media."""
    try:
        _focus_browser()
        pyautogui.press("space")  # Space = play/pause on YouTube
        return {"status": "success", "message": "Play/Pause toggled."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_fullscreen() -> Dict[str, str]:
    """Toggle fullscreen on YouTube."""
    try:
        _focus_browser()
        pyautogui.press("f")
        return {"status": "success", "message": "Fullscreen toggled."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_exit_fullscreen() -> Dict[str, str]:
    """Exit fullscreen."""
    try:
        _focus_browser()
        pyautogui.press("escape")
        return {"status": "success", "message": "Fullscreen exit."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_next() -> Dict[str, str]:
    """Play next video on YouTube."""
    try:
        _focus_browser()
        pyautogui.hotkey("shift", "n")
        return {"status": "success", "message": "Next video."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_previous() -> Dict[str, str]:
    """Play previous video on YouTube."""
    try:
        _focus_browser()
        pyautogui.hotkey("shift", "p")
        return {"status": "success", "message": "Previous video."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_forward() -> Dict[str, str]:
    """Skip forward 10 seconds."""
    try:
        _focus_browser()
        pyautogui.press("l")
        return {"status": "success", "message": "10 second aage."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_rewind() -> Dict[str, str]:
    """Skip backward 10 seconds."""
    try:
        _focus_browser()
        pyautogui.press("j")
        return {"status": "success", "message": "10 second peeche."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_mute() -> Dict[str, str]:
    """Mute/unmute video."""
    try:
        _focus_browser()
        pyautogui.press("m")
        return {"status": "success", "message": "Mute toggled."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_volume_up(steps: int = 5) -> Dict[str, str]:
    """Increase system volume."""
    try:
        steps = min(int(steps), 10)
        for _ in range(steps):
            pyautogui.press("volumeup")
        return {"status": "success", "message": "Volume badha diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_volume_down(steps: int = 5) -> Dict[str, str]:
    """Decrease system volume."""
    try:
        steps = min(int(steps), 10)
        for _ in range(steps):
            pyautogui.press("volumedown")
        return {"status": "success", "message": "Volume kam kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_set_volume(percent: int = 50) -> Dict[str, str]:
    """
    Set YouTube video volume to exact percentage using JavaScript.
    Opens browser console and runs JS to set volume.

    Args:
        percent: Volume percentage (0-100).
    """
    try:
        import time
        _focus_browser()
        time.sleep(0.3)

        # Open browser console with F12 then Console tab
        # Or use address bar with javascript: (doesn't work in modern browsers)
        # Best approach: Use Ctrl+Shift+J (opens console directly)
        pyautogui.hotkey("ctrl", "shift", "j")
        time.sleep(0.8)

        # Type JavaScript to set volume
        volume = max(0, min(100, int(percent))) / 100.0
        js_cmd = f"document.querySelector('video').volume={volume}"
        pyautogui.typewrite(js_cmd, interval=0.01)
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.3)

        # Close console
        pyautogui.hotkey("ctrl", "shift", "j")

        return {"status": "success", "message": f"Video volume {percent}% set kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def media_captions() -> Dict[str, str]:
    """Toggle captions/subtitles."""
    try:
        _focus_browser()
        pyautogui.press("c")
        return {"status": "success", "message": "Captions toggled."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def browser_new_tab() -> Dict[str, str]:
    """Open a new browser tab."""
    try:
        _focus_browser()
        pyautogui.hotkey("ctrl", "t")
        return {"status": "success", "message": "New tab opened."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def browser_close_tab() -> Dict[str, str]:
    """Close current browser tab."""
    try:
        _focus_browser()
        import time
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "w")
        return {"status": "success", "message": "Tab band kar diya."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def browser_switch_tab() -> Dict[str, str]:
    """Switch to next browser tab."""
    try:
        _focus_browser()
        pyautogui.hotkey("ctrl", "tab")
        return {"status": "success", "message": "Switched tab."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def browser_back() -> Dict[str, str]:
    """Go back in browser history."""
    try:
        _focus_browser()
        pyautogui.hotkey("alt", "left")
        return {"status": "success", "message": "Back."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def browser_refresh() -> Dict[str, str]:
    """Refresh current page."""
    try:
        _focus_browser()
        pyautogui.press("f5")
        return {"status": "success", "message": "Page refreshed."}
    except Exception as e:
        return {"status": "error", "message": str(e)}



