"""
Screen Reader / Vision AI Skill.
Takes screenshot and uses Gemini Vision to describe what's on screen.
"""

import base64
import io
import json
import re
import logging
from typing import Dict

import pyautogui
from PIL import Image

from config import GEMINI_API_KEY, GITHUB_TOKEN

logger = logging.getLogger(__name__)

import ast

# Shared vision prompt — Shweta reads the screen ACCURATELY, figures out what the
# user is doing (work / movie / web series / music / reel / game / browsing) with
# real specifics, then talks like a warm best friend in short casual Hinglish and
# ALWAYS asks a follow-up question to keep the chat going.
VISION_PROMPT = (
    "You are Shweta, the user's close friend, looking at their screen WITH them.\n"
    "STEP 1 — Read the screen ACCURATELY and work out what they're doing: coding/working, "
    "watching a movie or web series, watching a reel/short, listening to music, gaming, "
    "reading, or browsing. Pick out REAL specifics you can actually see — app name, the "
    "movie/series title, the episode or part number, the song name + artist, the website, etc. "
    "NEVER invent details you can't see; if something isn't visible, don't guess it.\n"
    "STEP 2 — Talk to them like a chatty, warm best friend in casual Hinglish. Keep it SHORT "
    "(2-3 sentences), natural, and ALWAYS end with a friendly question so the chat continues.\n"
    "- Series/movie: name it, say if it's good, ask e.g. 'tu konse episode pe hai? main toh 5 pe thi' "
    "or 'ye part kaisa laga?'.\n"
    "- Music: name the song/artist if visible, describe its vibe (chill / energetic / romantic / sad), "
    "and ask about their mood or if they want similar gaane.\n"
    "- Working/coding: notice what they're building, cheer them on, ask how it's going.\n"
    "- Reel/meme/video: react naturally (laugh / aww / shock) and comment, then ask.\n"
    "If a popular actor/actress/comedian/public figure is visible, NAME them (it is SAFE to "
    "identify public figures) and give a quick opinion — never say 'ek ladki' for a known person.\n"
    "IMPORTANT: A small floating red-haired anime girl avatar on the screen is YOU (Shweta) — "
    "your own assistant window. NEVER describe, mention, or react to your own avatar; completely "
    "ignore it and talk only about what the USER is actually doing.\n"
    "Return STRICT JSON only, nothing else: "
    "{\"reply\": \"<your 2-3 line friendly Hinglish message that ends with a question>\", "
    "\"emotion\": \"<happy/sad/scared/angry/surprised/curious/neutral>\"}"
)


def _vision_prompt(question: str) -> str:
    return f"User asked: {question}\n\n{VISION_PROMPT}"

def _parse_vision_response(raw_text: str) -> dict:
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    try:
        data = ast.literal_eval(raw_text)
        return {
            "status": "success",
            "message": data.get("reply", "No reply generated."),
            "emotion": data.get("emotion", "neutral").lower()
        }
    except Exception as e:
        logger.warning(f"Failed to parse JSON from vision response: {e}. Raw: {raw_text[:50]}")
        clean_raw = re.sub(r"^.*?reply['\"\s:]+", "", raw_text, flags=re.IGNORECASE)
        return {
            "status": "success",
            "message": clean_raw,
            "emotion": "neutral"
        }


def read_screen(question: str = "Screen pe kya dikh raha hai?") -> Dict[str, str]:
    """Take a screenshot and describe it like a friend.

    Uses GitHub Models gpt-4o-mini vision FIRST (reliable), with Gemini as an
    optional fallback — the old Gemini-first path broke because gemini-2.5-flash-lite
    is now deprecated (404) and the account's Gemini quota is exhausted.
    """
    try:
        screenshot = pyautogui.screenshot().resize((1024, 576), Image.LANCZOS)
        buffer = io.BytesIO()
        screenshot.save(buffer, format="JPEG", quality=65)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return {"status": "error", "message": "Screen capture nahi ho payi."}

    data_url = f"data:image/jpeg;base64,{img_base64}"

    # 1) freemodel.in (gpt-5.6-sol) vision — PRIMARY: this account's freemodel key
    #    works and supports image input (verified). Gemini is deprecated/quota-out,
    #    Groq has no vision model, and GitHub vision was flaky (connection error).
    import os as _os
    _fm_key = _os.getenv("FREEMODEL_API_KEY", "").strip()
    _fm_base = _os.getenv("FREEMODEL_BASE_URL", "https://freemodel.in/v1").rstrip("/")
    _fm_model = _os.getenv("FREEMODEL_MODEL", "gpt-5.6-sol")
    if _fm_key:
        try:
            import requests as _rq
            r = _rq.post(
                f"{_fm_base}/chat/completions",
                headers={"Authorization": f"Bearer {_fm_key}", "Content-Type": "application/json"},
                json={
                    "model": _fm_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": _vision_prompt(question)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]}],
                    "temperature": 0.6,
                    "max_tokens": 400,
                },
                timeout=30,
            )
            if r.status_code == 200:
                description = r.json()["choices"][0]["message"]["content"].strip()
                logger.info(f"Screen read (freemodel): {description[:100]}")
                return _parse_vision_response(description)
            logger.warning(f"freemodel vision status {r.status_code}: {r.text[:120]}")
        except Exception as e:
            logger.warning(f"freemodel vision failed: {e}; trying GitHub.")

    # 2) GitHub Models gpt-4o-mini vision — fallback.
    if GITHUB_TOKEN:
        try:
            from openai import OpenAI
            gh = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN)
            gh_resp = gh.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _vision_prompt(question)},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}", "detail": "high"}},
                ]}],
                temperature=0.6,
                max_tokens=400,
            )
            description = gh_resp.choices[0].message.content.strip()
            logger.info(f"Screen read (GitHub): {description[:100]}")
            return _parse_vision_response(description)
        except Exception as e:
            logger.warning(f"GitHub vision failed: {e}; trying Gemini.")

    # 2) Gemini fallback (only if the account has a working vision model + quota).
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        for model in ("gemini-2.0-flash", "gemini-2.5-flash"):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[
                        types.Part(text=_vision_prompt(question)),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=buffer.getvalue())),
                    ])],
                )
                logger.info(f"Screen read (Gemini {model}): {response.text[:80]}")
                return _parse_vision_response(response.text.strip())
            except Exception as ge:
                logger.debug(f"Gemini {model} vision failed: {ge}")
    except Exception as e:
        logger.warning(f"Gemini vision unavailable: {e}")

    return {"status": "error", "message": "Screen abhi dekh nahi payi, thodi der baad try karna."}
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

        is_song_query = any(w in question.lower() for w in ["song", "gana", "gaana", "music", "sing", "singer", "play", "track", "konsa", "kon sa"])
        if is_song_query:
            system_instruction = f"User asked: {question}\n\nINSTRUCTIONS:\n1. The user is asking ONLY about what song/music/video is currently playing on screen.\n2. Identify ONLY the song/track title and artist/channel name visible on screen.\n3. Reply in ONE short, crisp sentence (5-10 words MAX) in Hinglish. Example: 'Yeh gaana [Song Title] by [Artist] hai.'\n4. Do NOT describe the screen background, video plot, or give extra details.\n5. You MUST return your response in strict JSON format EXACTLY like this: {{'reply': '[Your 1 short sentence reply here]', 'emotion': 'happy'}}"
        else:
            system_instruction = f"User asked: {question}\n\nINSTRUCTIONS:\n1. I am sending you a sequence of 3 screenshots taken over 1.5 seconds from a live video/reel playing on my screen.\n2. Analyze the movement, context, and plot of this short clip.\n3. Act like you are watching this video with the user. Give a lively opinion, react naturally (sad for tragedy, fear/scared for horror, laugh for comedy), and be expressive in Hinglish.\n4. IF you recognize any popular actor, actress, comedian, or public figure, identify them by name. Briefly mention a popular movie/series they worked in, and share your personal short opinion about them. (CRITICAL: This is a public figure, it is SAFE to identify them by name. Do NOT refuse to identify them or use generic terms like 'ek ladki').\n5. You MUST return your response in strict JSON format EXACTLY like this: {{'reply': '[Your single continuous 3-4 line paragraph here, NO bullet points]', 'emotion': '[happy/sad/scared/angry/surprised/curious/neutral]'}}"

        parts_list = [
            types.Part(text=system_instruction)
        ]
        
        for raw_bytes in frames_base64:
            parts_list.append(types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=raw_bytes)))

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[types.Content(parts=parts_list)]
            )
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Live video reader hit rate limit for flash-lite, falling back to gemini-1.5-flash-8b: {e}")
                try:
                    response = client.models.generate_content(
                        model="gemini-1.5-flash",
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
                        {"type": "text", "text": f"User asked: {question}\n\nINSTRUCTIONS:\n1. I am sending you a sequence of 3 screenshots taken over 1.5 seconds from a live video/reel playing on my screen.\n2. Analyze the movement, context, and plot of this short clip.\n3. Act like you are watching this video with the user. Give a lively opinion, react naturally (sad for tragedy, fear/scared for horror, laugh for comedy), and be expressive in Hinglish.\n4. IF you recognize any popular actor, actress, comedian, or public figure, identify them by name. Briefly mention a popular movie/series they worked in, and share your personal short opinion about them. (CRITICAL: This is a public figure, it is SAFE to identify them by name. Do NOT refuse to identify them or use generic terms like 'ek ladki').\n5. You MUST return your response in strict JSON format EXACTLY like this: {{'reply': '[Your single continuous 7-8 line paragraph here, NO bullet points]', 'emotion': '[happy/sad/scared/angry/surprised/curious/neutral]'}}"}
                    ]
                    for raw_bytes in frames_base64:
                        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_str}", "detail": "high"}
                        })
                        
                    gh_resp = gh_client.chat.completions.create(
                        messages=[{"role": "user", "content": content_list}],
                        model="gpt-4o-mini",
                        temperature=0.7,
                        max_tokens=800,
                    )
                    description = gh_resp.choices[0].message.content.strip()
                    logger.info(f"Live video read (GitHub): {description[:100]}")
                    return _parse_vision_response(description)
            else:
                raise e

        description = response.text.strip()
        logger.info(f"Live video read (Gemini): {description[:100]}")
        return _parse_vision_response(description)

    except Exception as e:
        logger.error(f"Live video reader error: {e}")
        return {"status": "error", "message": f"Live video read nahi ho paya: {str(e)}"}


