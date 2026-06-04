# Shweta AI Desktop Assistant — Complete Project Context Document

## Overview
Shweta is a voice-controlled AI desktop assistant for Windows, built in Python. It speaks Hinglish (Hindi in Roman script), controls the desktop, plays media, manages files, sends WhatsApp messages, has a Telegram bot for remote control, and much more.

**GitHub:** https://github.com/Prathameshkhairnarr/DESKSHWETA
**Location:** D:\Shweeta ai desk assistant\
**Python:** 3.14 (Windows, path: C:\Users\sai\AppData\Local\Python\bin\python3.exe)
**Browser:** Brave (C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe)

---

## Architecture

```
main.py                          → Entry point, orchestrates everything
├── assistant/
│   ├── ui.py                    → Tkinter floating UI with animated gradient ring
│   ├── voice_input.py           → Mic recording (sounddevice) + Google STT via HTTP
│   ├── voice_output.py          → Edge TTS (natural voice) + pyttsx3 fallback
│   ├── ai_brain.py              → Multi-provider AI (Groq → Gemini → GitHub Models)
│   ├── desktop_control.py       → Action router (60+ actions mapped)
│   ├── channels/
│   │   └── telegram_bot.py      → Telegram bot (remote control + file sharing)
│   └── skills/
│       ├── browser.py           → YouTube play, media controls, browser tabs
│       ├── browser_auto.py      → Selenium automation (Brave)
│       ├── browser_agent.py     → Autonomous Playwright browser agent
│       ├── system.py            → Screenshot, volume, time, shutdown, run_command
│       ├── apps.py              → Open/close any app (with app_map)
│       ├── files.py             → Create/delete/rename/move/search files
│       ├── weather.py           → Open-Meteo free API
│       ├── timer.py             → Timers & reminders (threading)
│       ├── notes.py             → Persistent notes/todo (JSON)
│       ├── sysinfo.py           → Battery, RAM, CPU, WiFi, storage (psutil)
│       ├── windows.py           → Window management (snap, minimize, switch)
│       ├── briefing.py          → Daily briefing (time + weather + battery + notes)
│       ├── whatsapp.py          → WhatsApp Desktop messaging
│       ├── vision.py            → Screen reader (Gemini Vision)
│       ├── gesture.py           → Hand gesture control (MediaPipe + webcam)
│       ├── market.py            → Crypto, stocks, news, gold prices
│       ├── personality.py       → Personality modes + Memory + Health reminders
│       ├── multilang.py         → Multi-language support (6 languages)
│       ├── learning.py          → Usage pattern tracking + suggestions
│       └── wakeword.py          → Wake word detection (disabled — mic conflict)
├── config.py                    → All settings, API keys (from .env), system prompt
├── .env                         → API keys (NOT in git)
├── user_memory.json             → Persistent user preferences
├── usage_patterns.json          → Usage tracking data
├── contacts.json                → WhatsApp contacts (optional)
└── logs/                        → Chat logs, error logs, file transfer logs
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Voice Input | sounddevice + Google Speech API (HTTP, no library) |
| Voice Output | edge-tts (Microsoft Neural Voices) + pyttsx3 fallback |
| AI Brain | Groq (llama-3.3-70b, primary) → Gemini → GitHub Models (fallback) |
| UI | Tkinter + PIL/numpy (animated gradient ring) |
| Desktop Control | pyautogui, subprocess, pygetwindow |
| Browser | subprocess (Brave), Selenium (backup), Playwright (agent) |
| Telegram | python-telegram-bot 21.5 |
| System Info | psutil |
| Gesture | MediaPipe HandLandmarker + OpenCV |
| Config | python-dotenv |

---

## API Keys (.env)

```
GEMINI_API_KEY=...          # Google Gemini (free tier, limited)
GROQ_API_KEY=...            # Groq (primary, 14400 req/day)
GITHUB_TOKEN=...            # GitHub Models (fallback)
TELEGRAM_BOT_TOKEN=...      # Telegram bot
TELEGRAM_ALLOWED_USER_ID=...# Telegram security
```

---

## AI Brain — Multi-Provider System

- **Primary:** Groq (llama-3.3-70b-versatile) — fastest, max_retries=0
- **Fallback 1:** Gemini (gemini-2.0-flash-lite)
- **Fallback 2:** GitHub Models (gpt-4o-mini via Azure endpoint)
- If one hits 429, instantly tries next
- System prompt is large (~3000 tokens) with all available actions
- AI responds in JSON: `{"action": "ACTION", "params": {...}, "reply": "..."}`
- Parser handles different formats (GitHub puts params at top level)

---

## Voice System

### Input (voice_input.py)
- Records 3 seconds via `sd.rec()` (sounddevice)
- Sends raw PCM to Google Speech API v2 (HTTP POST, no library)
- Uses public Chromium key: `AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw`
- Language: hi-IN (tries en-IN as fallback)

### Output (voice_output.py)
- Primary: edge-tts (en-IN-NeerjaNeural for Hinglish, +30% speed)
- Fallback voices: hi-IN-SwaraNeural, mr-IN-AarohiNeural, ta-IN-PallaviNeural, te-IN-ShrutiNeural
- Plays via PowerShell MediaPlayer (.NET)
- pyttsx3 (Zira) as offline fallback

---

## UI (ui.py) — Current State

- Tkinter with overrideredirect (no title bar)
- Floating window, always-on-top, bottom-right
- Animated gradient ring (numpy + PIL, LANCZOS downscale)
- Ring colors change per state (idle=blue, listening=green, thinking=orange, speaking=purple)
- Mic button in center of ring
- Suggestion pills below
- Win32 API hide/show for clean screenshots
- **PENDING:** PyQt5 + OpenGL 3D UI upgrade

---

## Telegram Bot Features

- User ID whitelist security
- Keyboard buttons (Screenshot, Weather, Volume, Files, Status)
- File search + secure send (confirmation required)
- Blocked: system files, .exe, passwords, >50MB
- File upload (phone → PC Desktop)
- Live screen stream (/stream — 5 screenshots)
- Clipboard sync (/clipboard, /copy)
- Dangerous actions blocked from Telegram
- Shweta window hidden during screenshots

---

## Security Measures

1. **run_command allowlist** — only safe commands (dir, ipconfig, ping, etc.)
2. **Destructive action confirmation** — shutdown/restart need voice "haan"
3. **Telegram blocks** — shutdown, restart, run_command, recycle bin, lock
4. **File sharing** — extension whitelist, path restrictions, size limit, confirmation
5. **.gitignore** — .env excluded from git

---

## Known Issues / Pending Fixes

1. **Browser Agent** — search works but summarization fails when all AI providers are rate-limited
2. **Wake Word** — disabled (conflicts with mic recording)
3. **Gesture Control** — works but unstable (MediaPipe new API)
4. **WhatsApp by name** — depends on pyautogui timing, sometimes misses
5. **UI** — Tkinter is basic, needs PyQt5+OpenGL upgrade
6. **Voice delay** — Edge TTS has 1-2 sec network delay

---

## All Available Actions (60+)

### Browser & Media
open_youtube, open_google, open_website, play_youtube, media_play_pause, media_fullscreen, media_exit_fullscreen, media_next, media_previous, media_forward, media_rewind, media_mute, media_volume_up, media_volume_down, media_set_volume, media_captions, browser_new_tab, browser_close_tab, browser_switch_tab, browser_back, browser_refresh, close_window

### System
take_screenshot, get_time, get_date, volume_up, volume_down, volume_mute, lock_screen, open_file_manager, type_text, copy_to_clipboard, empty_recycle_bin, run_command, shutdown_pc, restart_pc, sleep_pc

### Apps
open_notepad, open_calculator, open_terminal, open_vscode, open_spotify, open_app, close_app

### Files
create_file, create_folder, delete_file, rename_file, move_file, copy_file, list_files, open_file, search_file, search_and_open

### Info
get_weather, get_battery, get_ram_usage, get_storage, get_cpu_usage, get_wifi_status, get_system_info, get_crypto_price, get_stock_market, get_news, get_gold_price, daily_briefing

### Communication
send_whatsapp, send_whatsapp_by_name

### Productivity
add_note, list_notes, delete_note, complete_note, clear_notes, set_timer, set_reminder, list_timers, cancel_timer

### Window Management
snap_left, snap_right, maximize_window, minimize_window, minimize_all, switch_window, close_window, task_view

### AI & Advanced
read_screen, start_gesture, stop_gesture, browser_agent_task, browser_agent_history

### Personality & Memory
set_mode (fun/professional/study), remember, get_memory, health_reminders_on, health_reminders_off, set_language, get_usage_stats

---

## How to Run

```bash
cd "D:\Shweeta ai desk assistant"
& "C:\Users\sai\AppData\Local\Python\bin\python3.exe" main.py
```

Or double-click: `Start Shweta.bat`

---

## Next Session TODO

1. **PyQt5 + OpenGL 3D UI** — Replace Tkinter with proper 3D animated interface
2. **Browser Agent fix** — Summarization when all providers rate-limited
3. **Voice speed optimization** — Reduce Edge TTS delay further
4. **Wake word** — Fix mic conflict for hands-free activation


---

## NEXT SESSION — PRIORITY TODO

### 1. Migrate from Tkinter to PyQt5 Avatar UI (CRITICAL)
- Remove Tkinter UI (`assistant/ui.py`) from main.py
- Make Avatar Window (`assistant/ui/avatar_window.py`) the ONLY UI
- Run everything in one PyQt5 process (not separate subprocess)
- Integrate state changes: listening/thinking/speaking → avatar expressions
- Integrate lip sync: voice_output.py → avatar mouth movement
- Add mic button click on avatar (click anywhere = start listening)

### 2. Avatar Improvements
- Drag working (top bar approach is set up, needs testing in single process)
- Lip sync: read audio amplitude during TTS playback → call setLipSync()
- Blinking animation already in viewer.html (working)
- Mouse eye tracking already in viewer.html (working)

### 3. Files to modify:
- `main.py` — Remove Tkinter, use QApplication + AvatarWindow as main loop
- `assistant/ui/avatar_window.py` — Add mic click, state management
- `assistant/voice_output.py` — Add lip sync callback during audio playback

### 4. Key constraint:
- PyQt5 uses QApplication.exec_() as main loop (replaces Tkinter mainloop)
- All voice/AI/telegram runs in background threads (same as now)
- Avatar window is the main thread UI
