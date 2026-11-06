"""
WhatsApp Messaging Skill — Uses WhatsApp Desktop app or Web fallback.
Opens app, searches contact by name or number, sends message.
"""

import json
import logging
import os
import threading
import time
import urllib.parse
from typing import Dict

import pyautogui
import pyperclip

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# WhatsApp Desktop package fallback
WHATSAPP_PACKAGE = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm"


def _open_whatsapp() -> bool:
    """Open WhatsApp Desktop app or Web fallback."""
    try:
        os.startfile("whatsapp:")
        logger.info("WhatsApp opened via URI scheme ('whatsapp:').")
        return True
    except Exception:
        try:
            os.startfile(f"shell:AppsFolder\\{WHATSAPP_PACKAGE}!App")
            logger.info("WhatsApp opened via package folder.")
            return True
        except Exception:
            try:
                import webbrowser
                webbrowser.open("https://web.whatsapp.com")
                logger.info("WhatsApp Web opened in default browser.")
                return True
            except Exception as e:
                logger.error(f"Failed to open WhatsApp: {e}")
                return False


def send_whatsapp(phone: str, message: str) -> Dict[str, str]:
    """Send WhatsApp message by phone number using whatsapp:// protocol."""
    try:
        phone = phone.replace("+", "").replace(" ", "").replace("-", "").strip()
        if len(phone) == 10:
            phone = "91" + phone

        encoded_msg = urllib.parse.quote(message)
        url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
        try:
            os.startfile(url)
        except Exception:
            import webbrowser
            webbrowser.open(f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}")

        def _auto_send():
            time.sleep(6)
            pyautogui.press("enter")
            logger.info(f"WhatsApp message sent to {phone}.")

        threading.Thread(target=_auto_send, daemon=True).start()
        return {"status": "success", "message": f"{phone} ko WhatsApp message bhej rahi hoon."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def send_whatsapp_by_name(name: str, message: str) -> Dict[str, str]:
    """
    Send WhatsApp message by searching contact name in contacts.json or WhatsApp Desktop.
    """
    try:
        # Step 1: Check contacts.json first
        contacts_file = PROJECT_ROOT / "contacts.json"
        if contacts_file.exists():
            try:
                contacts = json.loads(contacts_file.read_text(encoding="utf-8"))
                name_clean = name.lower().strip()
                for c_name, c_phone in contacts.items():
                    if name_clean in c_name.lower():
                        logger.info(f"Found contact '{c_name}' in contacts.json -> {c_phone}")
                        return send_whatsapp(c_phone, message)
            except Exception as e:
                logger.warning(f"Error reading contacts.json: {e}")

        # Step 2: Open WhatsApp app
        _open_whatsapp()
        logger.info(f"WhatsApp opened for contact search: {name}, msg: {message}")

        def _search_and_send():
            time.sleep(3.5)  # Wait for app window to focus

            try:
                # Try Ctrl+N to open New Chat / Search bar in WhatsApp
                pyautogui.hotkey("ctrl", "n")
                time.sleep(0.8)

                # Paste contact name
                pyperclip.copy(name)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(2.0)  # Wait for search results

                # Select top result and open chat
                pyautogui.press("down")
                time.sleep(0.4)
                pyautogui.press("enter")
                time.sleep(1.2)

                # Paste message
                pyperclip.copy(message)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.4)

                # Send message
                pyautogui.press("enter")
                logger.info(f"WhatsApp message sent to {name}!")

            except Exception as e:
                logger.error(f"WhatsApp send failed: {e}")

        threading.Thread(target=_search_and_send, daemon=True).start()
        return {"status": "success", "message": f"'{name}' ko WhatsApp message bhej rahi hoon."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
