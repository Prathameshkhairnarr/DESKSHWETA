"""
WhatsApp Messaging Skill — Uses WhatsApp Desktop app.
Opens app, searches contact by name, sends message.
No manual contact list needed — searches directly in WhatsApp.
"""

import logging
import os
import time
import threading
import urllib.parse
from typing import Dict

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

# WhatsApp Desktop package
WHATSAPP_PACKAGE = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm"


def _open_whatsapp() -> None:
    """Open WhatsApp Desktop app."""
    try:
        os.startfile(f"shell:AppsFolder\\{WHATSAPP_PACKAGE}!App")
    except Exception:
        import subprocess
        subprocess.Popen(f'start "" "shell:AppsFolder\\{WHATSAPP_PACKAGE}!App"', shell=True)


def send_whatsapp(phone: str, message: str) -> Dict[str, str]:
    """Send WhatsApp message by phone number using whatsapp:// protocol."""
    try:
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        if len(phone) == 10:
            phone = "91" + phone

        encoded_msg = urllib.parse.quote(message)
        url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
        os.startfile(url)

        def _auto_send():
            time.sleep(7)
            pyautogui.press("enter")
            logger.info("WhatsApp message sent via number.")

        threading.Thread(target=_auto_send, daemon=True).start()
        return {"status": "success", "message": f"Message bhej raha hoon {phone} ko."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_whatsapp_by_name(name: str, message: str) -> Dict[str, str]:
    """
    Send WhatsApp message by searching contact name in WhatsApp Desktop.
    No manual contact list — searches directly in the app.
    """
    try:
        # Open WhatsApp
        _open_whatsapp()
        logger.info(f"WhatsApp opened, will search: {name}, msg: {message}")

        def _search_and_send():
            time.sleep(4)  # Wait for app to come to foreground

            try:
                # Step 1: Click on search area (top-left of WhatsApp)
                # WhatsApp Desktop search is at the top
                # Use keyboard shortcut to open search
                pyautogui.hotkey("ctrl", "f")
                time.sleep(1)

                # Step 2: Clear and type contact name
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyperclip.copy(name)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(2.5)  # Wait for search results

                # Step 3: Press Down arrow to select first result, then Enter
                pyautogui.press("down")
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(1.5)

                # Step 4: Now we're in the chat — type message
                pyperclip.copy(message)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.3)

                # Step 5: Send
                pyautogui.press("enter")
                logger.info(f"WhatsApp message sent to {name}!")

            except Exception as e:
                logger.error(f"WhatsApp send failed: {e}")

        threading.Thread(target=_search_and_send, daemon=True).start()
        return {"status": "success", "message": f"'{name}' ko message bhej raha hoon."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
