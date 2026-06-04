# 🤖 SHWETA AI Desktop Assistant — Complete Documentation

> **Developer Reference Document**
> Last Updated: May 2026
> Author: Project Developer
> Version: 2.0 (PyQt5 Avatar UI + Multi-Provider AI)

---

## 📋 Table of Contents

1. [Project Overview](#1-project-overview)
2. [Folder Structure](#2-folder-structure)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Module-wise Explanation](#4-module-wise-explanation)
5. [Features & Skills](#5-features--skills)
6. [Tech Stack](#6-tech-stack)
7. [Voice Pipeline](#7-voice-pipeline)
8. [Supported Actions/Commands](#8-supported-actionscommands)
9. [Configuration](#9-configuration)
10. [How to Run](#10-how-to-run)

---

## 1. Project Overview

**Shweta** ek voice-controlled AI desktop assistant hai jo Windows pe run hoti hai. Ye teri
girl bestfriend ki tarah behave karti hai — Hinglish mein baat karti hai, casual aur caring
tone mein. Isko tu voice se ya Telegram se control kar sakta hai.

### Kya karti hai Shweta:

- 🎙️ Voice se commands leti hai (Hindi/English/Hinglish/Marathi)
- 🧠 AI brain (Groq + Gemini + GitHub Models) se samajhti hai kya karna hai
- 🖥️ Desktop control — apps kholna, files manage, volume, screenshots
- 🌐 Browser automation — YouTube, Google, Amazon search, multi-tab
- 🎵 Spotify deep control — mood-based playlists, play/pause/next
- 📊 TradingView chart automation — trend lines, fibonacci, support/resistance
- 📱 Telegram bot — phone se remote desktop control + file sharing
- 👁️ Vision AI — screen read karke batati hai kya dikh raha hai
- ✋ Gesture control — haath ke gestures se media control
- 📧 Email — AI-drafted professional emails via Gmail API
- 💬 WhatsApp messages — contacts ko direct message
- 🧠 Memory — user preferences yaad rakhti hai
- 📈 Learning — usage patterns track karke personalize karti hai
- 🏥 Health reminders — paani, eye rest, break yaad dilati hai
- 🌍 Multi-language — Hindi, English, Marathi, Hinglish auto-detect
- 🗣️ Wake word — "Hey Shweta" bolke activate karo
- 🎭 3D Avatar UI — PyQt5 + VRM model with lip sync + emotions

---

## 2. Folder Structure

```
Shweeta ai desk assistant/
│
├── main.py                    # 🚀 Entry point — ShwetaAssistant class
├── config.py                  # ⚙️ All configuration, API keys, system prompt
├── requirements.txt           # 📦 Python dependencies
├── .env                       # 🔑 API keys (secret, gitignored)
├── .env.example               # 📝 Template for .env setup
├── contacts.json              # 📇 WhatsApp contacts mapping
├── notes.json                 # 📝 User notes/todos storage
├── user_memory.json           # 🧠 Persistent user preferences
├── usage_patterns.json        # 📊 Usage learning data
├── hand_landmarker.task       # ✋ MediaPipe hand model
├── Start Shweta.bat           # ▶️ Windows batch launcher
├── shweta.spec                # 📦 PyInstaller build spec
├── installer.iss              # 📦 Inno Setup installer script
├── record_wakeword.py         # 🎤 Record wake word samples
├── train_wakeword.py          # 🏋️ Train wake word model
├── train_hey_shweta.py        # 🏋️ Alternative wake word trainer
├── test_*.py                  # 🧪 Various test scripts
│
├── assistant/                 # 📁 CORE PACKAGE
│   ├── __init__.py
│   ├── ai_brain.py            # 🧠 Multi-provider AI (Groq/Gemini/GitHub)
│   ├── voice_input.py         # 🎤 VAD + Google STT
│   ├── voice_output.py        # 🔊 Edge-TTS + cache + lip sync
│   ├── desktop_control.py     # 🎮 Action router (100+ actions)
│   ├── ui.py                  # 🖼️ Old Tkinter UI (deprecated)
│   │
│   ├── ui/                    # 🎭 NEW PyQt5 Avatar UI
│   │   ├── avatar_window.py   # Main window (QWebEngineView + VRM)
│   │   ├── _init_avatar.py    # Avatar initialization
│   │   └── avatar/            # VRM model + viewer.html + assets
│   │
│   ├── channels/              # 📱 External interfaces
│   │   ├── __init__.py
│   │   └── telegram_bot.py    # Telegram remote control + file sharing
│   │
│   └── skills/                # 🛠️ ALL SKILL MODULES
│       ├── __init__.py
│       ├── apps.py            # App launcher (notepad, calc, vscode, etc.)
│       ├── browser.py         # Browser control (hotkeys, media keys)
│       ├── browser_agent.py   # Autonomous browser (Playwright + AI)
│       ├── browser_auto.py    # Selenium browser automation
│       ├── multi_browser.py   # Multi-tab orchestrator (Brave)
│       ├── briefing.py        # Daily briefing (weather + news + calendar)
│       ├── email_skill.py     # Gmail API email sending
│       ├── files.py           # File management (create/delete/move/search)
│       ├── gesture.py         # Hand gesture control (MediaPipe)
│       ├── learning.py        # Usage pattern learning
│       ├── market.py          # Crypto, stocks, gold, news
│       ├── multilang.py       # Multi-language support + auto-detect
│       ├── notes.py           # Notes/Todo management
│       ├── personality.py     # Personality modes + Memory + Health
│       ├── spotify.py         # Spotify deep control (API + desktop)
│       ├── sysinfo.py         # System info (battery, RAM, CPU, WiFi)
│       ├── system.py          # System actions (volume, screenshot, lock)
│       ├── timer.py           # Timer & reminder management
│       ├── trading.py         # TradingView chart automation
│       ├── vision.py          # Screen reader (Gemini Vision)
│       ├── wakeword.py        # "Hey Shweta" wake word detection
│       ├── weather.py         # Weather information
│       ├── whatsapp.py        # WhatsApp messaging
│       └── windows.py         # Window management (snap, minimize, etc.)
│
├── cache/                     # 💾 TTS audio cache
│   └── tts_cache/             # MD5-hashed MP3 files
│
├── logs/                      # 📋 Application logs
│   ├── errors.log             # Error log
│   ├── chat_YYYY-MM-DD.txt    # Daily conversation logs
│   ├── browser_tasks.log      # Browser agent task log
│   └── file_transfers.log     # Telegram file transfer log
│
├── screenshots/               # 📸 Saved screenshots
├── build/                     # 🏗️ PyInstaller build output
└── dist/                      # 📦 Distributable .exe
    └── Shweta/
        └── Shweta.exe         # Standalone executable
```

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SHWETA AI ASSISTANT                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  INPUT LAYER │    │   AI BRAIN   │    │    OUTPUT LAYER      │  │
│  ├──────────────┤    ├──────────────┤    ├──────────────────────┤  │
│  │              │    │              │    │                      │  │
│  │ Voice Input  │───▶│ Groq (1st)   │───▶│ Voice Output         │  │
│  │ (Silero VAD  │    │ Gemini (2nd) │    │ (Edge-TTS + Cache)   │  │
│  │  + Google    │    │ GitHub (3rd) │    │                      │  │
│  │  STT)        │    │              │    │ 3D Avatar UI         │  │
│  │              │    │ Health Cache  │    │ (PyQt5 + VRM +       │  │
│  │ Wake Word    │    │ (smart       │    │  Lip Sync)           │  │
│  │ ("Hey        │    │  failover)   │    │                      │  │
│  │  Shweta")    │    │              │    │ Telegram Bot         │  │
│  │              │    │ JSON Response │    │ (Remote output)      │  │
│  │ Telegram Bot │    │ {action,     │    │                      │  │
│  │ (Text input) │    │  params,     │    └──────────────────────┘  │
│  │              │    │  reply,      │                               │
│  │ Hotkeys      │    │  emotion}    │                               │
│  │ (Ctrl+Shift  │    │              │                               │
│  │  +A)         │    └──────┬───────┘                               │
│  │              │           │                                       │
│  └──────────────┘           ▼                                       │
│                    ┌──────────────────┐                              │
│                    │ DESKTOP CONTROL  │                              │
│                    │ (Action Router)  │                              │
│                    ├──────────────────┤                              │
│                    │                  │                              │
│                    │ 100+ Actions     │                              │
│                    │ mapped to        │                              │
│                    │ Skill Modules    │                              │
│                    │                  │                              │
│                    └────────┬─────────┘                              │
│                             │                                       │
│              ┌──────────────┼──────────────────┐                    │
│              ▼              ▼                   ▼                    │
│  ┌────────────────┐ ┌─────────────┐ ┌──────────────────┐           │
│  │  SYSTEM SKILLS │ │BROWSER SKILL│ │  ADVANCED SKILLS │           │
│  ├────────────────┤ ├─────────────┤ ├──────────────────┤           │
│  │ • Apps         │ │ • Browser   │ │ • Spotify        │           │
│  │ • System       │ │ • Agent     │ │ • Trading        │           │
│  │ • Files        │ │ • Multi-tab │ │ • Vision AI      │           │
│  │ • SysInfo      │ │ • Selenium  │ │ • Gesture        │           │
│  │ • Windows      │ │             │ │ • Email          │           │
│  │ • Timer        │ │             │ │ • WhatsApp       │           │
│  │ • Notes        │ │             │ │ • Learning       │           │
│  │ • Weather      │ │             │ │ • Personality    │           │
│  └────────────────┘ └─────────────┘ └──────────────────┘           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Module-wise Explanation

### 4.1 `main.py` — Entry Point

**Kya karta hai:** Poora application yahan se start hota hai. `ShwetaAssistant` class
saare components ko initialize karti hai aur orchestrate karti hai.

**Key responsibilities:**
- Saare modules initialize karna (voice, AI, desktop control, UI)
- Voice input → AI → Action → Voice output pipeline manage karna
- Thread management (background threads for listening, processing)
- Global hotkeys register karna (Ctrl+Shift+A = listen, Ctrl+Shift+Q = quit)
- Wake word detection start karna
- Telegram bot background mein start karna
- Confirmation flow handle karna (shutdown/restart ke liye)
- Quick action buttons handle karna
- Lip sync callback connect karna (voice → avatar)

**Important methods:**
- `_listen_and_process()` — Main voice pipeline (background thread)
- `_process_input(text)` — AI brain se response leke action execute karna
- `_on_mic_click()` — Mic button/click handler (reset bhi karta hai)
- `_handle_special_commands()` — Quit, confirmation handling
- `_greet_threadsafe()` — Startup greeting with avatar animation

---

### 4.2 `config.py` — Configuration

**Kya karta hai:** Saari settings, API keys, paths, aur system prompt ek jagah define karta hai.

**Key configs:**
- API Keys: `GEMINI_API_KEY`, `GROQ_API_KEY`, `GITHUB_TOKEN`
- Assistant: `ASSISTANT_NAME`, `DEFAULT_LANGUAGE`, `DEFAULT_CITY`
- AI Model: `gemini-2.0-flash-lite`, conversation history limit = 10
- TTS: Hindi/English voices, speaking rate, pitch
- STT: Timeout 6s, phrase limit 10s
- UI: Window size, colors (idle=blue, listening=green, thinking=orange, speaking=purple)
- **SYSTEM_PROMPT**: Ye sabse important hai — Shweta ki personality, available actions,
  rules sab yahan define hai. AI ko batata hai kaise respond karna hai (JSON format mein).

---

### 4.3 `assistant/ai_brain.py` — AI Brain (Multi-Provider)

**Kya karta hai:** User input ko AI providers ko bhejta hai aur structured JSON response
parse karta hai. Smart failover system hai — agar ek provider rate-limited ho jaye toh
automatically dusre pe switch karta hai.

**Providers (priority order):**
1. **Groq** (Primary) — Llama 3.3 70B, fastest, 14400 req/day free
2. **Gemini** (Fallback 1) — Google's gemini-2.0-flash-lite
3. **GitHub Models** (Fallback 2) — GPT-4o-mini via Azure endpoint

**ProviderHealthCache system:**
- 429 Rate Limit → 5 minute cooldown
- Connection/timeout error → 30 second cooldown
- Other errors → 10 second cooldown
- Automatically skips unavailable providers
- Tracks last success time for smart ordering

**Response format (AI returns):**
```json
{"action": "open_youtube", "params": {"query": "lofi"}, "reply": "YouTube khol rahi hoon", "emotion": "happy"}
```

**Key features:**
- Conversation history maintain karta hai (last 10 exchanges)
- Language detection integration (responds in detected language)
- User context injection (learning data → AI prompt)
- Robust JSON parsing (handles malformed responses, embedded params)
- Emotion detection from reply text (keyword-based fallback)
- Daily conversation logging

---

### 4.4 `assistant/voice_input.py` — Voice Input (VAD + STT)

**Kya karta hai:** Microphone se smart recording — sirf jab user bole tab record kare,
silence detect hone pe stop kare. Phir Google STT se text mein convert kare.

**Technology:**
- **Silero VAD** (Voice Activity Detection) — PyTorch model
- **Google Speech-to-Text API** — Hindi + English recognition
- **sounddevice** — Low-level audio capture

**Flow:**
1. Silero VAD model load (startup pe ek baar)
2. Mic stream open (30ms chunks, 16kHz, mono)
3. Wait for speech (VAD confidence ≥ 0.45)
4. Record while speaking
5. Stop after 1.2s silence
6. Send to Google STT (hi-IN primary, en-IN fallback)

**Smart features:**
- 6 second timeout agar koi nahi bola
- Minimum 300ms speech required (blips ignore)
- Maximum 12 second recording cap
- Pre-speech buffer (last 300ms keep karta hai for context)

---

### 4.5 `assistant/voice_output.py` — Voice Output (TTS + Lip Sync)

**Kya karta hai:** Text ko natural voice mein convert karta hai with real-time lip sync
for the 3D avatar. Cache system hai for instant playback.

**TTS Engine:** Microsoft Edge-TTS (FREE, neural voices)
- Primary voice: `en-IN-NeerjaNeural` (Indian English, female)
- Fallback voice: `hi-IN-SwaraNeural` (Hindi, female)
- Speaking rate: +35%

**Cache System:**
- 22 common phrases pre-generated at startup (background thread)
- Cache location: `cache/tts_cache/`
- Filename: MD5 hash of normalized text + `.mp3`
- Auto-cache: Short phrases (≤40 chars) automatically cached after first generation
- Cached phrases play INSTANTLY (no network delay)

**Lip Sync Pipeline:**
1. Decode MP3 → PCM numpy array (via soundfile/libsndfile)
2. Play via winsound (instant start)
3. Parallel thread: analyze RMS amplitude per frame at 30fps
4. Normalize, threshold, smooth → send volume (0.0-1.0) to avatar
5. Avatar's VRM model opens/closes mouth accordingly

**Fallback chain:** Edge-TTS → pyttsx3 (offline)

---

### 4.6 `assistant/desktop_control.py` — Action Router

**Kya karta hai:** AI brain se jo action aaye, usse correct skill module pe route karta hai.
100+ actions mapped hain different skill functions pe.

**Design pattern:** Dictionary-based action mapping
```python
self._action_map = {
    "open_youtube": self._open_youtube,
    "take_screenshot": self._take_screenshot,
    ...
}
```

**Key features:**
- Safe initialization — agar ek skill fail ho toh baaki kaam kare
- Parameter validation (ensures params is always dict)
- Confirmation flow for dangerous actions (shutdown/restart)
- Usage tracking (every action logged to learner)
- Error handling with user-friendly messages

---

### 4.7 `assistant/ui/avatar_window.py` — 3D Avatar UI

**Kya karta hai:** PyQt5 window with embedded WebEngine that renders a 3D VRM avatar
model. Lip sync, emotions, chat bubbles, system tray — sab handle karta hai.

**Technology:**
- PyQt5 + QWebEngineView (Chromium-based)
- Local HTTP server (port 8765) serves VRM files
- Three.js + VRM loader in viewer.html
- WebGL for 3D rendering

**States:** idle, listening, thinking, speaking
**Emotions:** happy, sad, angry, surprised, relaxed, neutral

**Features:**
- Frameless, always-on-top, bottom-right positioned
- Draggable from top bar
- Click anywhere = mic activation
- System tray icon (minimize to tray, right-click menu)
- Chat bubbles with auto-fade
- Typing animation (thinking state)
- Thread-safe UI updates via Qt signals
- Lip sync decay (smooth mouth close when not speaking)

---

### 4.8 `assistant/channels/telegram_bot.py` — Telegram Remote Control

**Kya karta hai:** Phone se desktop control karne deta hai. File sharing, screenshots,
AI chat, system control — sab Telegram se.

**Security features:**
- Single authorized user (TELEGRAM_ALLOWED_USER_ID)
- Safe folders only (Desktop, Documents, Downloads, Pictures, Music, Videos)
- Blocked paths (C:\Windows, /etc, etc.)
- Blocked keywords in filenames (password, secret, token, .env)
- Allowed extensions only (.pdf, .txt, .docx, .jpg, .mp3, etc.)
- 50MB file size limit
- Dangerous actions blocked from Telegram (shutdown, restart, run_command)
- File transfer confirmation required
- 60 second request expiry

**Commands:**
- `/start` — Quick action keyboard
- `/screenshot` — Desktop screenshot (hides Shweta window)
- `/status` — System status
- `/files` — Recent files list
- `/stream` — 5 screenshots every 3 sec (live view)
- `/clipboard` — Get PC clipboard
- `/copy <text>` — Set PC clipboard
- Text message → AI response + action execution
- Send file → Saves to Desktop

---

## 5. Features & Skills

### 5.1 Browser Skills (`browser.py`)
- YouTube open/search/play
- Google search
- Any website open
- Media controls: play/pause, fullscreen, next/prev, forward/rewind, mute, volume, captions
- Tab management: new tab, close tab, switch tab, back, refresh

### 5.2 Browser Agent (`browser_agent.py`)
- **Autonomous web browsing** — Playwright + AI planning
- AI plans steps (goto, click, type, scroll, extract)
- Supports Amazon, Flipkart, Google structured extraction
- Multi-provider AI for step planning (Groq → Gemini → GitHub)
- Results summarized in Hinglish
- Task history logging
- Use case: Product research, price comparison, online info lookup

### 5.3 Multi-Browser (`multi_browser.py`)
- **Multiple tabs simultaneously** in Brave browser
- Fast regex-based URL detection (no AI needed for common sites)
- Supports: YouTube, TradingView, Prime Video, Netflix, Amazon, Flipkart, Google, Spotify, GitHub, ChatGPT, Twitter, Instagram, LinkedIn, Reddit, WhatsApp Web
- Complex interactions via Playwright + Brave CDP
- AI fallback for unrecognized patterns
- Uses user's logged-in Brave profile

### 5.4 Spotify (`spotify.py`)
- **Hybrid approach:** Desktop app (media keys) + Web API (spotipy)
- Play/Pause, Next, Previous
- Now Playing info
- Search & play specific songs
- Playlist playback
- **Mood-based playlists:** happy, sad, chill, coding, workout, party, romantic, focus, sleep
- Volume control, Shuffle toggle
- Fallback to YouTube if Spotify API unavailable

### 5.5 Trading (`trading.py`)
- TradingView chart automation via pyautogui
- Open TradingView with specific symbol
- Draw: Trend line, Horizontal line, Rectangle, Fibonacci
- AI Vision-based support/resistance marking
- Undo/Clear drawings
- Change symbol, Change timeframe (1m to 1M)
- Keyboard shortcuts: Alt+T (trend), Alt+H (horizontal), Alt+R (rectangle), Alt+F (fib)

### 5.6 Vision AI (`vision.py`)
- Screenshot → Gemini Vision analysis
- Describes what's on screen in Hinglish
- Resizes to 720p for fast upload
- Use case: "Screen pe kya hai?", chart analysis, reading text

### 5.7 Gesture Control (`gesture.py`)
- MediaPipe HandLandmarker (webcam-based)
- **Gestures:**
  - 5 fingers (open palm) = Play/Pause
  - 0 fingers (fist) = Mute
  - 2 fingers (peace) = Next track
  - 3 fingers = Volume Up
  - 4 fingers = Volume Down
- 1.5 second cooldown between gestures
- Auto-downloads hand model if not present

### 5.8 Email (`email_skill.py`)
- Gmail API (OAuth, free)
- AI drafts professional email (Groq/Gemini)
- Supports contacts: HR, Manager, Team, Boss
- Multiple recipients (comma-separated)
- One-time browser OAuth login
- Template fallback if AI unavailable

### 5.9 WhatsApp (`whatsapp.py`)
- Send messages via WhatsApp Web automation
- Contact name → phone number mapping (contacts.json)
- Devanagari to Roman script transliteration for names

### 5.10 Personality & Memory (`personality.py`)
- **3 Modes:** Fun (default), Professional, Study
- **Memory Store:** Persistent JSON (name, city, fav songs, language)
- **Health Reminders:**
  - Water: every 30 min
  - Eye rest (20-20-20 rule): every 20 min
  - Break: every 60 min

### 5.11 Learning (`learning.py`)
- Tracks hourly action patterns
- Frequent queries, favorite songs, favorite apps
- Mood history tracking
- User habits detection (night owl, morning music)
- Conversation topic tracking
- AI context generation (makes Shweta feel like she KNOWS you)
- Proactive suggestions based on time patterns

### 5.12 Multi-Language (`multilang.py`)
- **Supported:** Hindi, English, Marathi, Hinglish, Tamil, Telugu
- Auto-detection from text (Devanagari detection, word matching)
- Per-language Edge TTS voice selection
- AI prompt injection for language-specific responses
- Manual language switching available

### 5.13 Wake Word (`wakeword.py`)
- "Hey Shweta" detection
- Runs in **SEPARATE PROCESS** (no mic conflict)
- Records 2-sec clips → Google STT → keyword check
- Triggers: "shweta", "schweta", "shveta", "swetha", "sweta"
- 4 second cooldown between detections
- RMS silence check (skips quiet clips)

### 5.14 System Skills (`system.py`, `sysinfo.py`, `apps.py`, `windows.py`)
- Volume up/down/mute
- Screenshot (saved to screenshots/)
- Lock screen, Sleep PC
- Shutdown/Restart (with confirmation)
- Type text, Copy to clipboard
- Empty recycle bin, Run command
- Battery, RAM, CPU, Storage, WiFi status
- App launcher (any app by name)
- Window management (snap left/right, maximize, minimize, task view)

### 5.15 File Management (`files.py`)
- Create/Delete files and folders
- Rename, Move, Copy files
- List files in directory
- Search file by name (recursive)
- Search and open file
- Open file with default app

### 5.16 Notes/Todo (`notes.py`)
- Add note, List notes, Delete note
- Complete note (mark done)
- Clear all notes
- Persistent JSON storage

### 5.17 Timer & Reminders (`timer.py`)
- Set timer (seconds)
- Set reminder (message + minutes)
- List active timers
- Cancel timer by ID
- Voice notification on completion

### 5.18 Market & News (`market.py`)
- Crypto prices (CoinGecko API)
- Stock market info
- Gold price
- News by topic

### 5.19 Daily Briefing (`briefing.py`)
- Combined: Weather + News + System status
- One command se sab info mil jaati hai

---

## 6. Tech Stack

### Core
| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| UI Framework | PyQt5 + QWebEngineView |
| 3D Avatar | Three.js + VRM (via WebGL) |
| AI (Primary) | Groq API (Llama 3.3 70B) |
| AI (Fallback 1) | Google Gemini 2.0 Flash Lite |
| AI (Fallback 2) | GitHub Models (GPT-4o-mini) |
| STT | Google Speech-to-Text API |
| TTS | Microsoft Edge-TTS (Neural) |
| TTS Offline | pyttsx3 |
| VAD | Silero VAD (PyTorch) |

### Browser Automation
| Component | Technology |
|-----------|-----------|
| Autonomous Agent | Playwright (async) |
| Legacy Automation | Selenium |
| Multi-tab | Playwright + Brave CDP |
| Target Browser | Brave Browser |

### Desktop Control
| Component | Technology |
|-----------|-----------|
| GUI Automation | pyautogui |
| Keyboard | keyboard library |
| Window Mgmt | pygetwindow |
| Clipboard | pyperclip |

### External Services
| Component | Technology |
|-----------|-----------|
| Telegram | python-telegram-bot |
| Spotify | spotipy (OAuth) |
| Email | Gmail API (google-api-python-client) |
| Vision | Gemini Vision API |
| Gesture | MediaPipe HandLandmarker |
| Webcam | OpenCV |

### Data & Storage
| Component | Technology |
|-----------|-----------|
| Config | python-dotenv (.env) |
| Persistence | JSON files |
| Logging | Python logging (daily files) |
| TTS Cache | MD5-hashed MP3 files |

---

## 7. Voice Pipeline

### Complete Flow: User bolte hai → Shweta action leti hai → Reply bolti hai

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VOICE PIPELINE FLOW                              │
└─────────────────────────────────────────────────────────────────────────┘

STEP 1: ACTIVATION
─────────────────
  User clicks avatar / says "Hey Shweta" / presses Ctrl+Shift+A
       │
       ▼
  UI State → LISTENING (avatar green glow)

STEP 2: VOICE INPUT (voice_input.py)
─────────────────────────────────────
  Mic stream open (16kHz, mono, 30ms chunks)
       │
       ▼
  Silero VAD checks each chunk (confidence ≥ 0.45?)
       │
       ├── NO speech for 6s → "Samajh nahi aaya" → IDLE
       │
       └── YES speech detected → Start recording
              │
              ▼
         Record until 1.2s silence (or 12s max)
              │
              ▼
         Convert float32 → int16 PCM bytes
              │
              ▼
         UI State → THINKING (avatar orange glow)

STEP 3: SPEECH-TO-TEXT (Google STT)
───────────────────────────────────
  PCM bytes → Base64 encode
       │
       ▼
  POST to Google STT API
  (languageCode: "hi-IN", alternativeLanguageCodes: ["en-IN"])
       │
       ├── Success → Recognized text (e.g., "YouTube pe lofi music laga do")
       │
       └── Fail → Try en-IN only → Still fail → "Samajh nahi aaya"

STEP 4: AI PROCESSING (ai_brain.py)
────────────────────────────────────
  Text + Conversation History + User Context + Language Instruction
       │
       ▼
  ProviderHealthCache → Get ordered providers (skip rate-limited ones)
       │
       ▼
  Try Provider 1 (Groq/Gemini/GitHub based on health)
       │
       ├── Success → JSON response
       │     {"action": "play_youtube", "params": {"query": "lofi music"},
       │      "reply": "Lofi laga rahi hoon, chill kar!", "emotion": "relaxed"}
       │
       └── Fail → Mark failed in cache → Try next provider

STEP 5: ACTION EXECUTION (desktop_control.py)
─────────────────────────────────────────────
  Action name → _action_map lookup → Skill function call
       │
       ▼
  browser.play_youtube("lofi music")
       │
       ▼
  Opens YouTube search in browser, clicks first video
       │
       ▼
  Returns: {"status": "success", "message": "YouTube pe lofi music play ho raha hai"}

STEP 6: VOICE OUTPUT (voice_output.py)
──────────────────────────────────────
  Reply text: "Lofi laga rahi hoon, chill kar!"
       │
       ▼
  Check TTS cache (MD5 hash lookup)
       │
       ├── CACHED → Instant playback from MP3 file
       │
       └── NOT CACHED → Edge-TTS generate MP3
              │
              ▼
         Decode MP3 → PCM numpy array (soundfile)
              │
              ▼
         Play via winsound + Lip Sync thread (parallel)
              │
              ├── Audio plays through speakers
              │
              └── RMS amplitude → 30fps → Avatar mouth movement
                     │
                     ▼
              UI State → SPEAKING (avatar purple glow, mouth moving)
                     │
                     ▼
              Audio done → UI State → IDLE (avatar blue, mouth closed)

STEP 7: LEARNING (background)
─────────────────────────────
  • Action tracked in usage_patterns.json
  • Mood tracked in mood_history
  • Topic extracted from user text
  • Conversation logged to daily file
```

---

## 8. Supported Actions/Commands

### 🌐 Browser Actions
| Action | Params | Description |
|--------|--------|-------------|
| `open_youtube` | — | YouTube homepage kholo |
| `open_google` | `{query}` | Google search karo |
| `open_website` | `{url}` | Koi bhi website kholo |
| `play_youtube` | `{query}` | YouTube pe search + play |
| `media_play_pause` | — | Play/Pause toggle |
| `media_fullscreen` | — | Fullscreen toggle |
| `media_next` | — | Next video/track |
| `media_previous` | — | Previous video/track |
| `media_forward` | — | 5 sec forward |
| `media_rewind` | — | 5 sec rewind |
| `media_mute` | — | Mute toggle |
| `media_volume_up` | `{steps}` | Browser volume up |
| `media_volume_down` | `{steps}` | Browser volume down |
| `media_captions` | — | Subtitles toggle |
| `browser_new_tab` | — | New tab |
| `browser_close_tab` | — | Close current tab |
| `browser_switch_tab` | — | Next tab |
| `browser_back` | — | Go back |
| `browser_refresh` | — | Refresh page |
| `close_window` | — | Close window (Alt+F4) |

### 🖥️ System Actions
| Action | Params | Description |
|--------|--------|-------------|
| `take_screenshot` | — | Screenshot le ke save karo |
| `get_time` | — | Current time batao |
| `get_date` | — | Current date batao |
| `volume_up` | `{steps}` | System volume up |
| `volume_down` | `{steps}` | System volume down |
| `volume_mute` | — | System mute |
| `lock_screen` | — | PC lock karo |
| `type_text` | `{text}` | Text type karo |
| `copy_to_clipboard` | `{text}` | Clipboard mein copy |
| `empty_recycle_bin` | — | Recycle bin khali karo |
| `run_command` | `{command}` | CMD command run karo |
| `shutdown_pc` | — | PC shutdown (confirmation) |
| `restart_pc` | — | PC restart (confirmation) |
| `sleep_pc` | — | PC sleep mode |

### 📱 App Actions
| Action | Params | Description |
|--------|--------|-------------|
| `open_notepad` | — | Notepad kholo |
| `open_calculator` | — | Calculator kholo |
| `open_terminal` | — | Terminal/CMD kholo |
| `open_vscode` | — | VS Code kholo |
| `open_spotify` | — | Spotify kholo |
| `open_app` | `{app_name}` | Koi bhi app kholo |
| `close_app` | `{app_name}` | App band karo |
| `open_file_manager` | — | File Explorer kholo |

### 📁 File Actions
| Action | Params | Description |
|--------|--------|-------------|
| `create_file` | `{filename, content}` | File banao |
| `create_folder` | `{foldername}` | Folder banao |
| `delete_file` | `{filename}` | File delete karo |
| `rename_file` | `{old_name, new_name}` | Rename karo |
| `move_file` | `{filename, destination}` | Move karo |
| `copy_file` | `{filename, destination}` | Copy karo |
| `list_files` | `{folder}` | Files list karo |
| `open_file` | `{filename}` | File kholo |
| `search_file` | `{name}` | File dhundo |
| `search_and_open` | `{name}` | Dhundo aur kholo |

### ℹ️ Info Actions
| Action | Params | Description |
|--------|--------|-------------|
| `get_weather` | `{city}` | Weather batao |
| `get_battery` | — | Battery status |
| `get_ram_usage` | — | RAM usage |
| `get_storage` | — | Disk space |
| `get_cpu_usage` | — | CPU usage |
| `get_wifi_status` | — | WiFi status |
| `get_system_info` | — | Full system info |
| `get_crypto_price` | `{coin}` | Crypto price |
| `get_stock_market` | — | Stock market |
| `get_news` | `{topic}` | News headlines |
| `get_gold_price` | — | Gold price |
| `daily_briefing` | — | Full daily briefing |

### 📝 Notes Actions
| Action | Params | Description |
|--------|--------|-------------|
| `add_note` | `{text}` | Note add karo |
| `list_notes` | — | Saari notes dikhao |
| `delete_note` | `{id}` | Note delete karo |
| `complete_note` | `{id}` | Note complete mark |
| `clear_notes` | — | Sab notes clear |

### 🪟 Window Actions
| Action | Params | Description |
|--------|--------|-------------|
| `snap_left` | — | Window left half |
| `snap_right` | — | Window right half |
| `maximize_window` | — | Maximize |
| `minimize_window` | — | Minimize |
| `minimize_all` | — | Sab minimize |
| `switch_window` | — | Alt+Tab |
| `task_view` | — | Task View kholo |

### ⏰ Timer Actions
| Action | Params | Description |
|--------|--------|-------------|
| `set_timer` | `{seconds}` | Timer set karo |
| `set_reminder` | `{message, minutes}` | Reminder set karo |
| `list_timers` | — | Active timers dikhao |
| `cancel_timer` | `{id}` | Timer cancel karo |

### 🎵 Spotify Actions
| Action | Params | Description |
|--------|--------|-------------|
| `spotify_play_pause` | — | Play/Pause |
| `spotify_next` | — | Next track |
| `spotify_previous` | — | Previous track |
| `spotify_now_playing` | — | Current track info |
| `spotify_play_song` | `{query}` | Song search + play |
| `spotify_play_playlist` | `{name}` | Playlist play |
| `spotify_mood` | `{mood}` | Mood-based playlist |
| `spotify_volume` | `{percent}` | Volume set |
| `spotify_shuffle` | `{on}` | Shuffle toggle |

### 💬 Communication Actions
| Action | Params | Description |
|--------|--------|-------------|
| `send_whatsapp` | `{phone, message}` | WhatsApp by number |
| `send_whatsapp_by_name` | `{name, message}` | WhatsApp by name |
| `send_email` | `{to, reason}` | Professional email |

### 🧠 Advanced Actions
| Action | Params | Description |
|--------|--------|-------------|
| `read_screen` | `{question}` | Screen read (Vision AI) |
| `start_gesture` | — | Gesture control ON |
| `stop_gesture` | — | Gesture control OFF |
| `browser_agent_task` | `{goal}` | Autonomous browser task |
| `multi_browser_task` | `{goal}` | Multi-tab browser task |
| `set_mode` | `{mode}` | Personality mode change |
| `remember` | `{key, value}` | Memory store |
| `get_memory` | — | Show all memory |
| `health_reminders_on` | — | Health reminders start |
| `health_reminders_off` | — | Health reminders stop |
| `set_language` | `{language}` | Language switch |
| `get_usage_stats` | — | Usage statistics |
| `clear_history` | — | Chat history clear |

### 📊 Trading Actions
| Action | Params | Description |
|--------|--------|-------------|
| `open_tradingview` | `{symbol}` | TradingView kholo |
| `draw_trend_line` | — | Trend line draw |
| `draw_horizontal_line` | — | Horizontal line |
| `draw_rectangle` | — | Rectangle zone |
| `draw_fibonacci` | — | Fibonacci retracement |
| `mark_support_resistance` | — | AI-based S/R levels |
| `undo_drawing` | — | Last drawing undo |
| `clear_drawings` | — | All drawings clear |
| `change_symbol` | `{symbol}` | Chart symbol change |
| `change_timeframe` | `{timeframe}` | Timeframe change |

---

## 9. Configuration

### 9.1 Environment Variables (`.env`)

```env
# === REQUIRED ===
GEMINI_API_KEY=your_key          # Google AI Studio (FREE)
GROQ_API_KEY=your_key            # Groq Cloud (FREE, 14400 req/day)

# === OPTIONAL (enhanced features) ===
GITHUB_TOKEN=your_token          # GitHub Models fallback AI
TELEGRAM_BOT_TOKEN=your_token    # Telegram bot (@BotFather)
TELEGRAM_ALLOWED_USER_ID=123456  # Your Telegram user ID

SPOTIFY_CLIENT_ID=your_id        # Spotify Developer Dashboard
SPOTIFY_CLIENT_SECRET=your_secret

GOOGLE_APPLICATION_CREDENTIALS=  # Google Cloud TTS (optional)

# === ASSISTANT SETTINGS ===
ASSISTANT_NAME=Shweta
DEFAULT_LANGUAGE=hi-IN
DEFAULT_CITY=Pune
LOG_LEVEL=INFO

# === EMAIL (optional) ===
EMAIL_HR=hr@company.com
EMAIL_MANAGER=manager@company.com
USER_FULL_NAME=Your Name
USER_DESIGNATION=Your Role
```

### 9.2 Key Configuration in `config.py`

| Setting | Value | Description |
|---------|-------|-------------|
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | AI model for Gemini |
| `CONVERSATION_HISTORY_LIMIT` | 10 | Max conversation pairs kept |
| `TTS_VOICE_HINDI` | `hi-IN-Wavenet-A` | Google Cloud TTS voice |
| `TTS_SPEAKING_RATE` | 1.0 | TTS speed |
| `TTS_PITCH` | 2.0 | TTS pitch |
| `STT_TIMEOUT` | 6 | Seconds to wait for speech |
| `STT_PHRASE_TIME_LIMIT` | 10 | Max phrase duration |
| `UI_WIDTH` | 280 | Old UI width |
| `UI_HEIGHT` | 380 | Old UI height |

### 9.3 Voice Configuration (`voice_output.py`)

| Setting | Value |
|---------|-------|
| Primary Voice | `en-IN-NeerjaNeural` |
| Fallback Voice | `hi-IN-SwaraNeural` |
| Speaking Rate | `+35%` |
| Cache Dir | `cache/tts_cache/` |
| Auto-cache max length | 40 chars |

### 9.4 VAD Configuration (`voice_input.py`)

| Setting | Value |
|---------|-------|
| Sample Rate | 16000 Hz |
| Chunk Size | 512 samples (30ms) |
| VAD Threshold | 0.45 |
| Silence Timeout | 1.2 seconds |
| Max Record | 12 seconds |
| Min Speech | 0.3 seconds |

### 9.5 Wake Word Configuration (`wakeword.py`)

| Setting | Value |
|---------|-------|
| Listen Duration | 2.0 seconds per clip |
| Cooldown | 4.0 seconds between detections |
| Silence RMS Threshold | 300 (int16 scale) |
| Triggers | shweta, schweta, shveta, swetha, sweta |

### 9.6 Health Reminders Intervals

| Reminder | Interval |
|----------|----------|
| Water | Every 30 minutes |
| Eye Rest (20-20-20) | Every 20 minutes |
| Break/Stretch | Every 60 minutes |

### 9.7 Spotify Mood Playlists

| Mood | Playlist |
|------|----------|
| happy | Happy Hits (Bollywood) |
| sad | Sad Songs |
| chill | Chill Hits / Lofi |
| coding | Coding Mode / Lofi Beats |
| workout | Beast Mode |
| party | Bollywood Party |
| romantic | Romance |
| focus | Deep Focus |
| sleep | Sleep / Calm |

---

## 10. How to Run

### 10.1 Prerequisites

- **OS:** Windows 10/11
- **Python:** 3.10+ (project uses 3.14)
- **Microphone:** Required for voice input
- **Webcam:** Optional (for gesture control)
- **Brave Browser:** Required for multi-browser features
- **Spotify Desktop App:** Required for Spotify control

### 10.2 Installation

```bash
# 1. Clone/download the project
cd "d:\Vibe projects\Shweeta ai desk assistant"

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install additional dependencies (not in requirements.txt but used)
pip install edge-tts sounddevice soundfile numpy torch
pip install PyQt5 PyQtWebEngine
pip install spotipy python-telegram-bot
pip install playwright
playwright install chromium
pip install mediapipe opencv-python
pip install google-genai groq
pip install google-auth google-auth-oauthlib google-api-python-client
pip install pygetwindow

# 4. Setup .env file
copy .env.example .env
# Edit .env and add your API keys (minimum: GEMINI_API_KEY)

# 5. (Optional) Gmail setup
# Place credentials.json from Google Cloud Console in project root
# First email send will open browser for OAuth login
```

### 10.3 Running

```bash
# Method 1: Direct Python
python main.py

# Method 2: Batch file (Windows)
"Start Shweta.bat"

# Method 3: Built executable
dist\Shweta\Shweta.exe
```

### 10.4 First Run Checklist

1. ✅ `.env` file created with at least `GEMINI_API_KEY`
2. ✅ Microphone connected and working
3. ✅ Brave Browser installed (for browser features)
4. ✅ Spotify Desktop app installed (for music)
5. ✅ Internet connection (for AI, TTS, STT)
6. ✅ Run `python main.py` — avatar window should appear bottom-right
7. ✅ Wait 3 seconds for greeting: "Namaste! Main Shweta hoon."
8. ✅ Click avatar or press Ctrl+Shift+A to start talking

### 10.5 Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Shift+A` | Start listening (same as clicking avatar) |
| `Ctrl+Shift+Q` | Quit Shweta |
| Click avatar | Start listening / Reset if stuck |

### 10.6 Building Executable

```bash
# PyInstaller build
pyinstaller shweta.spec

# Output: dist/Shweta/Shweta.exe
# Installer: Use installer.iss with Inno Setup
```

### 10.7 Troubleshooting

| Problem | Solution |
|---------|----------|
| "Microphone not found" | Check mic connection, run `python test_mic.py` |
| AI not responding | Check API keys in `.env`, check internet |
| Avatar not loading | Wait 3-5 sec, check port 8765 not in use |
| TTS not working | Install edge-tts: `pip install edge-tts` |
| Spotify not connecting | Add SPOTIFY_CLIENT_ID/SECRET in .env |
| Telegram bot not starting | Add TELEGRAM_BOT_TOKEN in .env |
| Wake word not detecting | Check mic, run `python test_stt.py` |
| Gesture not working | Install mediapipe, check webcam |
| Browser agent failing | Install playwright: `playwright install chromium` |

---

## 🎯 Quick Reference — Common Voice Commands

```
"YouTube pe lofi music laga do"          → play_youtube
"Screenshot le lo"                        → take_screenshot
"Weather batao Pune ka"                   → get_weather
"Spotify pe chill music laga"             → spotify_mood
"5 minute ka timer laga"                  → set_timer
"Note likh — meeting 3 baje"             → add_note
"VS Code kholo"                           → open_vscode
"Volume badha do"                         → volume_up
"Screen pe kya hai?"                      → read_screen
"Amazon pe headphones dhundo 2000 ke andar" → browser_agent_task
"YouTube kholo aur TradingView pe NVDA"   → multi_browser_task
"HR ko leave ka email bhejo"              → send_email
"Prasad ko WhatsApp karo — late aaunga"   → send_whatsapp_by_name
"TradingView pe trend line draw karo"     → draw_trend_line
"Gesture control on karo"                 → start_gesture
"Band karo" / "Bye bye"                   → Quit
```

---

> **Note:** Ye documentation project ke current state ke hisaab se hai.
> Naye features add hone pe isko update karna. Har skill module ke andar
> docstrings bhi hain for quick reference.

---
*Built with ❤️ — Shweta AI Desktop Assistant*
