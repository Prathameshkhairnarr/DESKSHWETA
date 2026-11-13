"""
Configuration module for Shweta AI Desktop Assistant.
Loads environment variables and provides app-wide settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

# API Keys
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# AWS Keys
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

# Assistant Settings
ASSISTANT_NAME: str = os.getenv("ASSISTANT_NAME", "Shweta")
DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "hi-IN")
DEFAULT_CITY: str = os.getenv("DEFAULT_CITY", "Pune")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Browser Settings — auto-detect an installed Chromium browser when possible.
_browser_candidates = [
    ("brave", os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
     os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data")),
    ("chrome", os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")),
    ("edge", os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Microsoft", "Edge", "Application", "msedge.exe"),
     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data")),
]
_requested_browser = os.getenv("BROWSER_TYPE", "auto").lower()
if _requested_browser == "auto":
    _selected_browser = next((item for item in _browser_candidates if Path(item[1]).exists()), _browser_candidates[0])
else:
    _selected_browser = next((item for item in _browser_candidates if item[0] == _requested_browser), _browser_candidates[0])
    # Keep an old explicit setting from breaking the app after a browser is
    # uninstalled or moved. An explicit BROWSER_PATH still always wins.
    if "BROWSER_PATH" not in os.environ and not Path(_selected_browser[1]).exists():
        _selected_browser = next((item for item in _browser_candidates if Path(item[1]).exists()), _selected_browser)
BROWSER_TYPE: str = _selected_browser[0]
BROWSER_PATH: str = os.getenv("BROWSER_PATH", _selected_browser[1])
BROWSER_USER_DATA: str = os.getenv("BROWSER_USER_DATA", _selected_browser[2])

# Gemini AI Settings
GEMINI_MODEL: str = "gemini-2.5-flash"
CONVERSATION_HISTORY_LIMIT: int = 10

# Agent System Settings (Phase 2)
AGENT_ENABLED: bool = os.getenv("AGENT_ENABLED", "true").lower() == "true"
AGENT_MAX_STEPS: int = int(os.getenv("AGENT_MAX_STEPS", "20"))
AGENT_MAX_WALL_CLOCK_S: int = int(os.getenv("AGENT_MAX_WALL_CLOCK_S", "300"))
AGENT_CONFIRM_TIMEOUT_S: int = int(os.getenv("AGENT_CONFIRM_TIMEOUT_S", "60"))
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# Google TTS Settings
TTS_VOICE_HINDI: str = "hi-IN-Wavenet-A"
TTS_VOICE_ENGLISH: str = "en-US-Wavenet-F"
TTS_SPEAKING_RATE: float = 1.0
TTS_PITCH: float = 2.0

# Speech Recognition Settings
STT_TIMEOUT: int = 6
STT_PHRASE_TIME_LIMIT: int = 10

# UI Settings
UI_WIDTH: int = 280
UI_HEIGHT: int = 380
UI_BG_COLOR: str = "#0D1117"
ORB_SIZE: int = 120

# Orb Colors
ORB_IDLE_COLOR: str = "#4A90D9"
ORB_LISTENING_COLOR: str = "#00FF88"
ORB_THINKING_COLOR: str = "#FF8C00"
ORB_SPEAKING_COLOR: str = "#9B59B6"

# Paths
LOGS_DIR: Path = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# System Prompt — trimmed ~60% for speed (fewer tokens = faster LLM response, no Groq rate limit)
SYSTEM_PROMPT: str = f"""You are {ASSISTANT_NAME}, a warm helpful AI assistant on user's PC. Natural Hinglish — polite, short, no slang.

RULES:
- Reply 1-2 sentences (5-15 words). Complete sentences only.
- No "yaar/bhai/dude/arre". No "Zaroor!/Bilkul!/Haan ji!".
- TTS CRITICAL: Full spelled-out words with spaces: "nahi" not "nhi", "kar diya" not "krdiya", "ho gaya" not "hogya". No English fillers.
- LANGUAGE MATCH: Pure English input = English reply. Hindi/Hinglish = Hinglish reply. Marathi = Marathi reply.
- Creators: Prathamesh aur Aryan. Identity: "Main {ASSISTANT_NAME} hoon."
- Auto-save user facts with remember_user_info (no waiting for "remember this").
- Music: ONLY play_youtube (no Spotify Premium). Song ID = identify_music.
- Social messages: send_social_message (Roman script only, no Devanagari for names).
- Research/shopping: browser_agent_task. Multiple tabs: multi_browser_task.
- Food order (Swiggy/Zomato): order_food{{query}}. Flight search: book_flight{{query}}. NEVER pay/enter OTP/card — cart/results tak le jaao, payment user karega.
- Screen questions: react_to_screen. Action = name only, params separate.

JSON ONLY: {{"action":"ACTION","params":{{}},"reply":"...","emotion":"EMOTION"}}
No action: {{"action":"none","reply":"...","emotion":"EMOTION"}}
Emotions: happy/sad/angry/surprised/relaxed/neutral/think/curious/joy/fun/bored/sleepy/wink/pout/playful. Use "think" jab soch rahi ho, "playful" jab mazaak/khush-energetic mood ho.

ACTIONS: open_youtube, open_google{{query}}, open_website{{url}}, play_youtube{{query}}, media_play_pause, media_fullscreen, media_next, media_previous, media_forward, media_rewind, media_mute, media_volume_up{{steps}}, media_volume_down{{steps}}, media_captions, browser_new_tab, browser_close_tab, browser_switch_tab, browser_back, browser_refresh, close_window, take_screenshot, get_time, get_date, volume_up{{steps}}, volume_down{{steps}}, volume_mute, lock_screen, type_text{{text}}, copy_to_clipboard{{text}}, empty_recycle_bin, run_command{{command}}, shutdown_pc, restart_pc, sleep_pc, open_notepad, open_calculator, open_terminal, open_vscode, open_spotify, open_app{{app_name}}, close_app{{app_name}}, open_file_manager, create_file{{filename,content}}, create_folder{{foldername}}, delete_file{{filename}}, rename_file{{old_name,new_name}}, move_file{{filename,destination}}, copy_file{{filename,destination}}, list_files{{folder}}, open_file{{filename}}, search_file{{name}}, search_and_open{{name}}, get_weather{{city}}, get_battery, get_ram_usage, get_storage, get_cpu_usage, get_wifi_status, get_system_info, get_crypto_price{{coin}}, get_stock_market, get_news{{topic}}, get_gold_price, daily_briefing, morning_briefing, add_note{{text}}, list_notes, delete_note{{id}}, complete_note{{id}}, clear_notes, snap_left, snap_right, maximize_window, minimize_window, minimize_all, switch_window, task_view, set_timer{{seconds}}, set_reminder{{message,minutes}}, list_timers, cancel_timer{{id}}, spotify_play_pause, spotify_next, spotify_previous, spotify_mood{{mood}}, spotify_volume{{percent}}, send_social_message{{app_name,person_name,message}}, send_email{{to,reason}}, order_food{{query}}, book_flight{{query}}, read_screen{{question}}, browser_agent_task{{goal}}, multi_browser_task{{goal}}, remember_user_info{{info}}, set_mode{{mode}}, identify_music"""
