"""
App Skills for Shweta AI Desktop Assistant.
Handles opening and closing desktop applications.
"""

import logging
import os
import platform
import subprocess
from typing import Dict

logger = logging.getLogger(__name__)

# Detect operating system
OS_NAME = platform.system()


def open_notepad() -> Dict[str, str]:
    """
    Open a text editor (Notepad on Windows, gedit on Linux).

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.Popen("notepad.exe")
        elif OS_NAME == "Linux":
            subprocess.Popen(["gedit"])

        logger.info("Notepad/text editor opened.")
        return {"status": "success", "message": "Notepad khol diya."}
    except Exception as e:
        logger.error(f"Failed to open notepad: {e}")
        return {"status": "error", "message": str(e)}


def open_calculator() -> Dict[str, str]:
    """
    Open the system calculator.

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.Popen("calc.exe")
        elif OS_NAME == "Linux":
            subprocess.Popen(["gnome-calculator"])

        logger.info("Calculator opened.")
        return {"status": "success", "message": "Calculator khol diya."}
    except Exception as e:
        logger.error(f"Failed to open calculator: {e}")
        return {"status": "error", "message": str(e)}


def open_terminal() -> Dict[str, str]:
    """
    Open a terminal/command prompt.

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.Popen("cmd.exe", creationflags=subprocess.CREATE_NEW_CONSOLE)
        elif OS_NAME == "Linux":
            # Try common terminal emulators
            terminals = ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"]
            for term in terminals:
                try:
                    subprocess.Popen([term])
                    break
                except FileNotFoundError:
                    continue

        logger.info("Terminal opened.")
        return {"status": "success", "message": "Terminal khol diya."}
    except Exception as e:
        logger.error(f"Failed to open terminal: {e}")
        return {"status": "error", "message": str(e)}


def open_vscode() -> Dict[str, str]:
    """
    Open Visual Studio Code.

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            subprocess.Popen(["code"], shell=True)
        elif OS_NAME == "Linux":
            subprocess.Popen(["code"])

        logger.info("VS Code opened.")
        return {"status": "success", "message": "VS Code khol diya."}
    except Exception as e:
        logger.error(f"Failed to open VS Code: {e}")
        return {"status": "error", "message": str(e)}


def open_spotify() -> Dict[str, str]:
    """
    Open Spotify (desktop app or web).

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            # Try desktop app first
            try:
                subprocess.Popen(["spotify.exe"], shell=True)
            except FileNotFoundError:
                import webbrowser
                webbrowser.open("https://open.spotify.com")
        elif OS_NAME == "Linux":
            try:
                subprocess.Popen(["spotify"])
            except FileNotFoundError:
                import webbrowser
                webbrowser.open("https://open.spotify.com")

        logger.info("Spotify opened.")
        return {"status": "success", "message": "Spotify khol diya."}
    except Exception as e:
        logger.error(f"Failed to open Spotify: {e}")
        return {"status": "error", "message": str(e)}


def close_app(app_name: str) -> Dict[str, str]:
    """
    Close an application by name.

    Args:
        app_name: Name of the application to close.

    Returns:
        Result dictionary.
    """
    try:
        if OS_NAME == "Windows":
            # Use taskkill to close the app
            result = subprocess.run(
                ["taskkill", "/IM", f"{app_name}.exe", "/F"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                msg = f"{app_name} band kar diya."
            else:
                # Try with partial name match
                result = subprocess.run(
                    f'taskkill /FI "WINDOWTITLE eq {app_name}*" /F',
                    capture_output=True,
                    text=True,
                    shell=True
                )
                msg = f"{app_name} band karne ki koshish ki."
        elif OS_NAME == "Linux":
            subprocess.run(["pkill", "-f", app_name])
            msg = f"{app_name} band kar diya."
        else:
            return {"status": "error", "message": "OS not supported."}

        logger.info(f"Closed app: {app_name}")
        return {"status": "success", "message": msg}
    except Exception as e:
        logger.error(f"Failed to close {app_name}: {e}")
        return {"status": "error", "message": str(e)}


def open_app(app_name: str) -> Dict[str, str]:
    """
    Open any application by name. Tries multiple methods.

    Args:
        app_name: Name of the application to open.

    Returns:
        Result dictionary.
    """
    try:
        # Common app name mappings for Windows
        app_map = {
            "file explorer": "explorer",
            "file manager": "explorer",
            "explorer": "explorer",
            "this pc": "explorer",
            "my computer": "explorer",
            "settings": "ms-settings:",
            "control panel": "control",
            "task manager": "taskmgr",
            "paint": "mspaint",
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt",
            "chrome": "chrome",
            "brave": "brave",
            "firefox": "firefox",
            "edge": "msedge",
            "recycle bin": "shell:RecycleBinFolder",
            "downloads": "shell:Downloads",
            "documents": "shell:Documents",
            "desktop": "shell:Desktop",
            "snipping tool": "snippingtool",
            "camera": "microsoft.windows.camera:",
            "photos": "ms-photos:",
            "store": "ms-windows-store:",
            "clock": "ms-clock:",
            "maps": "bingmaps:",
            "mail": "outlookmail:",
            "calendar": "outlookcal:",
        }

        # Check if we have a known mapping
        app_lower = app_name.lower().strip()
        command = app_map.get(app_lower, None)

        if OS_NAME == "Windows":
            if command:
                try:
                    os.startfile(command)
                except Exception:
                    subprocess.Popen(command, shell=True)
            else:
                subprocess.Popen(f'start "" "{app_name}"', shell=True)

            logger.info(f"Opened app: {app_name}")
            return {"status": "success", "message": f"{app_name} khol diya."}

        elif OS_NAME == "Linux":
            subprocess.Popen([app_name.lower()])
            return {"status": "success", "message": f"{app_name} khol diya."}

        return {"status": "error", "message": f"{app_name} nahi khul paya."}
    except Exception as e:
        logger.error(f"Failed to open {app_name}: {e}")
        return {"status": "error", "message": str(e)}
