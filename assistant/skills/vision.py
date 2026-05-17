"""
Screen Reader / Vision AI Skill.
Takes screenshot and uses Gemini Vision to describe what's on screen.
"""

import base64
import io
import logging
from typing import Dict

import pyautogui
from PIL import Image

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


def read_screen(question: str = "Screen pe kya dikh raha hai?") -> Dict[str, str]:
    """
    Take screenshot and ask Gemini Vision to describe/analyze it.

    Args:
        question: What to ask about the screen content.
    """
    try:
        # Take screenshot
        screenshot = pyautogui.screenshot()

        # Resize for faster upload (720p is enough for analysis)
        screenshot = screenshot.resize((1280, 720), Image.LANCZOS)

        # Convert to base64
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=70)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Send to Gemini Vision
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=[
                types.Content(
                    parts=[
                        types.Part(text=f"User asked: {question}\nDescribe what you see on this screen in 2-3 short sentences in Hinglish (Hindi in Roman script). Be specific about app names, text visible, etc."),
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=buffer.getvalue()
                            )
                        )
                    ]
                )
            ]
        )

        description = response.text.strip()
        logger.info(f"Screen read: {description[:100]}")
        return {"status": "success", "message": description}

    except Exception as e:
        logger.error(f"Screen reader error: {e}")
        return {"status": "error", "message": f"Screen read nahi ho paya: {str(e)}"}
