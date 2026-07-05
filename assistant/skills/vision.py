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

from config import GEMINI_API_KEY, GITHUB_TOKEN

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

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=[
                    types.Content(
                        parts=[
                            types.Part(text=f"User asked: {question}\n\nINSTRUCTIONS:\n1. Describe what you see on the screen in 2-3 short sentences in Hinglish (Hindi in Roman script).\n2. IF the screen shows a social media reel, video, meme, or post (Instagram, YouTube, etc.), act like you are watching it with the user. Give a lively opinion, react to the content naturally (laugh, be surprised, etc.), and be expressive using Hinglish.\n3. Be conversational, as if you are a friend sitting next to them."),
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
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Screen reader hit rate limit for flash-lite, falling back to gemini-1.5-flash-8b: {e}")
                try:
                    response = client.models.generate_content(
                        model="gemini-1.5-flash-8b",
                        contents=[
                            types.Content(
                                parts=[
                                    types.Part(text=f"User asked: {question}\n\nINSTRUCTIONS:\n1. Describe what you see on the screen in 2-3 short sentences in Hinglish (Hindi in Roman script).\n2. IF the screen shows a social media reel, video, meme, or post (Instagram, YouTube, etc.), act like you are watching it with the user. Give a lively opinion, react to the content naturally (laugh, be surprised, etc.), and be expressive using Hinglish.\n3. Be conversational, as if you are a friend sitting next to them."),
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
                except Exception as e2:
                    logger.warning(f"Gemini 1.5 also failed, falling back to GitHub Models (gpt-4o-mini): {e2}")
                    from openai import OpenAI
                    gh_client = OpenAI(
                        base_url="https://models.inference.ai.azure.com",
                        api_key=GITHUB_TOKEN,
                    )
                    base64_image = f"data:image/jpeg;base64,{img_base64}"
                    gh_resp = gh_client.chat.completions.create(
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"User asked: {question}\n\nINSTRUCTIONS:\n1. Describe what you see on the screen in 2-3 short sentences in Hinglish (Hindi in Roman script).\n2. IF the screen shows a social media reel, video, meme, or post (Instagram, YouTube, etc.), act like you are watching it with the user. Give a lively opinion, react to the content naturally (laugh, be surprised, etc.), and be expressive using Hinglish.\n3. Be conversational, as if you are a friend sitting next to them."},
                                    {"type": "image_url", "image_url": {"url": base64_image, "detail": "low"}}
                                ]
                            }
                        ],
                        model="gpt-4o-mini",
                        temperature=0.6,
                        max_tokens=200,
                    )
                    description = gh_resp.choices[0].message.content.strip()
                    logger.info(f"Screen read (GitHub): {description[:100]}")
                    return {"status": "success", "message": description}
            else:
                raise e

        description = response.text.strip()
        logger.info(f"Screen read (Gemini): {description[:100]}")
        return {"status": "success", "message": description}

    except Exception as e:
        logger.error(f"Screen reader error: {e}")
def read_live_video(question: str) -> Dict[str, str]:
    """Capture 3 frames of live video and analyze movement."""
    try:
        import mss
        from PIL import Image
        import io
        import base64
        import time

        frames_base64 = []
        with mss.mss() as sct:
            for i in range(3):
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.thumbnail((800, 800))
                
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=70)
                frames_base64.append(buffer.getvalue())
                if i < 2:
                    time.sleep(0.5)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        parts_list = [
            types.Part(text=f"User asked: {question}\n\nINSTRUCTIONS:\n1. I am sending you a sequence of 3 screenshots taken over 1.5 seconds from a live video/reel playing on my screen.\n2. Analyze the movement, context, and plot of this short clip.\n3. Act like you are watching this video with the user. Give a lively opinion, react naturally (laugh, be surprised, etc.), and be expressive in Hinglish (Hindi in Roman script).\n4. Keep it to 2-4 conversational sentences.")
        ]
        
        for raw_bytes in frames_base64:
            parts_list.append(types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=raw_bytes)))

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=[types.Content(parts=parts_list)]
            )
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Live video reader hit rate limit for flash-lite, falling back to gemini-1.5-flash-8b: {e}")
                try:
                    response = client.models.generate_content(
                        model="gemini-1.5-flash-8b",
                        contents=[types.Content(parts=parts_list)]
                    )
                except Exception as e2:
                    logger.warning(f"Gemini 1.5 live video also failed, falling back to GitHub Models (gpt-4o-mini): {e2}")
                    from openai import OpenAI
                    gh_client = OpenAI(
                        base_url="https://models.inference.ai.azure.com",
                        api_key=GITHUB_TOKEN,
                    )
                    content_list = [
                        {"type": "text", "text": f"User asked: {question}\n\nINSTRUCTIONS:\n1. I am sending you a sequence of 3 screenshots taken over 1.5 seconds from a live video/reel playing on my screen.\n2. Analyze the movement, context, and plot of this short clip.\n3. Act like you are watching this video with the user. Give a lively opinion, react naturally (laugh, be surprised, etc.), and be expressive in Hinglish (Hindi in Roman script).\n4. Keep it to 2-4 conversational sentences."}
                    ]
                    for raw_bytes in frames_base64:
                        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_str}", "detail": "low"}
                        })
                        
                    gh_resp = gh_client.chat.completions.create(
                        messages=[{"role": "user", "content": content_list}],
                        model="gpt-4o-mini",
                        temperature=0.7,
                        max_tokens=250,
                    )
                    description = gh_resp.choices[0].message.content.strip()
                    logger.info(f"Live video read (GitHub): {description[:100]}")
                    return {"status": "success", "message": description}
            else:
                raise e

        description = response.text.strip()
        logger.info(f"Live video read (Gemini): {description[:100]}")
        return {"status": "success", "message": description}

    except Exception as e:
        logger.error(f"Live video reader error: {e}")
        return {"status": "error", "message": f"Live video read nahi ho paya: {str(e)}"}

