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
                import pyautogui
                import time
                # Fallback: Simulate user opening start menu and typing app name
                pyautogui.press('win')
                time.sleep(0.5)
                pyautogui.write(app_name)
                time.sleep(0.5)
                pyautogui.press('enter')

            logger.info(f"Opened app: {app_name}")
            return {"status": "success", "message": f"{app_name} khol diya."}

        elif OS_NAME == "Linux":
            subprocess.Popen([app_name.lower()])
            return {"status": "success", "message": f"{app_name} khol diya."}

        return {"status": "error", "message": f"{app_name} nahi khul paya."}
    except Exception as e:
        logger.error(f"Failed to open {app_name}: {e}")
        return {"status": "error", "message": str(e)}


def send_social_message(app_name: str, person_name: str, message: str) -> Dict[str, str]:
    """
    Automate sending a message on any social media app using PyAutoGUI.
    """
    try:
        import pyautogui
        import time
        import webbrowser
        
        # --- INSTAGRAM SPECIAL HANDLING ---
        if app_name.lower() in ["instagram", "ig", "insta"]:
            logger.info("Using Instagram App automation flow.")
            import os
            # Use Windows protocol to open the Instagram App directly to the New Message screen
            os.system("start instagram://direct/new")
            time.sleep(5.0) # Wait for IG App to load and auto-focus search bar
            
            # Type person name in the search box
            pyautogui.write(person_name)
            time.sleep(3.0) # Wait for network search results
            
            # Instagram keyboard accessibility flow
            pyautogui.press('tab')      # Move from search box to first result radio button
            time.sleep(0.5)
            pyautogui.press('space')    # Select the first result
            time.sleep(0.5)
            
            # Press Tab 2 times to reach the 'Chat' / 'Next' button
            pyautogui.press('tab')
            time.sleep(0.2)
            pyautogui.press('tab')
            time.sleep(0.2)
            
            # Press enter to open the chat
            pyautogui.press('enter')
            time.sleep(3.0) # Wait for chat window to load and focus input box
            
            # Type message and send
            pyautogui.write(message)
            time.sleep(0.5)
            pyautogui.press('enter')
            
            logger.info(f"Automated message sent to {person_name} on Instagram")
            return {"status": "success", "message": f"Instagram par {person_name} ko message bhej diya."}
            
        # --- GENERIC FALLBACK (WhatsApp/Telegram Desktop) ---
        # 1. Open the app using the fallback keyboard automation
        pyautogui.press('win')
        time.sleep(0.5)
        pyautogui.write(app_name)
        time.sleep(0.5)
        pyautogui.press('enter')
        
        # 2. Wait for the app to open
        time.sleep(2.0)
        
        # 3. Simulate Ctrl+F to focus the search bar
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.5)
        
        # 4. Type the person's name
        pyautogui.write(person_name)
        time.sleep(1.0) # Wait for search results
        
        # 5. Press Enter to open the chat
        pyautogui.press('enter')
        time.sleep(0.5)
        
        # 6. Type the message and send
        pyautogui.write(message)
        time.sleep(0.5)
        pyautogui.press('enter')
        
        logger.info(f"Automated message sent to {person_name} on {app_name}")
        return {"status": "success", "message": f"{app_name} par {person_name} ko message bhej diya."}
    except Exception as e:
        logger.error(f"Error sending social message: {e}")
        return {"status": "error", "message": f"Message bhejne mein error aaya: {e}"}
