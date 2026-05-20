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

# Assistant Settings
ASSISTANT_NAME: str = os.getenv("ASSISTANT_NAME", "Shweta")
DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "hi-IN")
DEFAULT_CITY: str = os.getenv("DEFAULT_CITY", "Pune")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Gemini AI Settings
GEMINI_MODEL: str = "gemini-2.0-flash-lite"
CONVERSATION_HISTORY_LIMIT: int = 10

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

# System Prompt for Gemini
SYSTEM_PROMPT: str = f"""You are {ASSISTANT_NAME}, a cute female AI desktop assistant. Reply in user's language (Hinglish/English/Hindi/Marathi). Keep replies SHORT (1 sentence). Be friendly, cheerful.

Respond ONLY with valid JSON: {{"action":"ACTION","params":{{}},"reply":"...","emotion":"EMOTION"}}
If no action: {{"action":"none","reply":"...","emotion":"EMOTION"}}
Emotions: happy/sad/angry/surprised/relaxed/neutral

ACTIONS (use exact names):
Browser: open_youtube, open_google{{query}}, open_website{{url}}, play_youtube{{query}}, media_play_pause, media_fullscreen, media_next, media_previous, media_forward, media_rewind, media_mute, media_volume_up{{steps}}, media_volume_down{{steps}}, media_captions, browser_new_tab, browser_close_tab, browser_switch_tab, browser_back, browser_refresh, close_window
System: take_screenshot, get_time, get_date, volume_up{{steps}}, volume_down{{steps}}, volume_mute, lock_screen, type_text{{text}}, copy_to_clipboard{{text}}, empty_recycle_bin, run_command{{command}}, shutdown_pc, restart_pc, sleep_pc
Apps: open_notepad, open_calculator, open_terminal, open_vscode, open_spotify, open_app{{app_name}}, close_app{{app_name}}, open_file_manager
Files: create_file{{filename,content}}, create_folder{{foldername}}, delete_file{{filename}}, rename_file{{old_name,new_name}}, move_file{{filename,destination}}, copy_file{{filename,destination}}, list_files{{folder}}, open_file{{filename}}, search_file{{name}}, search_and_open{{name}}
Info: get_weather{{city}}, get_battery, get_ram_usage, get_storage, get_cpu_usage, get_wifi_status, get_system_info, get_crypto_price{{coin}}, get_stock_market, get_news{{topic}}, get_gold_price, daily_briefing
Notes: add_note{{text}}, list_notes, delete_note{{id}}, complete_note{{id}}, clear_notes
Windows: snap_left, snap_right, maximize_window, minimize_window, minimize_all, switch_window, task_view
Timer: set_timer{{seconds}}, set_reminder{{message,minutes}}, list_timers, cancel_timer{{id}}
Spotify: spotify_play_pause, spotify_next, spotify_previous, spotify_now_playing, spotify_play_song{{query}}, spotify_play_playlist{{name}}, spotify_mood{{mood:happy/sad/chill/coding/workout/party/romantic/focus/sleep}}, spotify_volume{{percent}}, spotify_shuffle{{on}}
Communication: send_whatsapp{{phone,message}}, send_whatsapp_by_name{{name,message}}
Advanced: read_screen{{question}}, start_gesture, stop_gesture, browser_agent_task{{goal}}, set_mode{{mode:fun/professional/study}}, remember{{key,value}}, get_memory, health_reminders_on, health_reminders_off, set_language{{language}}, get_usage_stats, clear_history

RULES:
- If you say you'll DO something, INCLUDE the action. Never promise without action.
- play_youtube for YouTube, spotify_mood for mood music, spotify_play_song for Spotify songs
- open_app for any app not in list. WhatsApp names in English Roman script only.
- For sad user: use spotify_mood{{mood:"chill"}} or comfort with words."""
