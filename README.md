# 🤖 Shweta — AI Desktop Voice Assistant

A beautiful, AI-powered desktop voice assistant for Windows and Linux. Shweta speaks Hindi (and English), controls your desktop, and responds with a cute animated floating UI.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎤 Voice Input | Google Speech-to-Text (Hindi + English) |
| 🔊 Voice Output | Google Cloud TTS / pyttsx3 offline fallback |
| 🧠 AI Brain | **Google Gemini 2.5 Flash (100% FREE!)** |
| 🖥️ Desktop Control | Open apps, take screenshots, control volume |
| 🌐 Browser | Open YouTube, Google search, any website |
| 🌤️ Weather | Free Open-Meteo API (no key needed) |
| ⏰ Timers | Set timers and reminders with voice alerts |
| 🎨 Animated UI | Floating orb with state-based animations |
| ⌨️ Hotkeys | Ctrl+Shift+A to listen, Ctrl+Shift+Q to quit |
| 🗣️ Bilingual | Hindi by default, switches to English automatically |
| 💰 Cost | **Completely FREE** — no paid APIs needed! |

---

## 📸 Screenshots

> *Add screenshots of the running application here*

---

## 📋 Prerequisites

- **Python 3.10+**
- **Google Gemini API Key** (FREE from Google AI Studio — no credit card!)
- **Microphone** (for voice input)
- **Internet connection** (for AI and speech recognition)

### Optional:
- **Google Cloud Account** (only if you want premium TTS voice — app works without it using free offline TTS)

### System-specific:
- **Windows**: No extra setup needed
- **Linux**: Install `portaudio19-dev` for PyAudio:
  ```bash
  sudo apt-get install portaudio19-dev python3-pyaudio
  ```

---

## 🚀 Setup Instructions

### 1. Clone or Download the Project

```bash
git clone <your-repo-url>
cd shweta-ai-assistant
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note (Windows):** If PyAudio fails to install, download the `.whl` file from
> [Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
> and install with `pip install <filename>.whl`

### 4. Get FREE Gemini API Key (2 minutes!)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key — that's it! No credit card, no billing setup!

> **Free tier includes:** 15 requests/minute, 1 million tokens/day — more than enough for a personal assistant!

### 5. (Optional) Google Cloud TTS Setup

> Skip this if you're okay with the free offline voice. The app works perfectly without it.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **Cloud Text-to-Speech API**
4. Create a service account and download the JSON key file

### 6. Configure Environment Variables

```bash
# Copy the example file
copy .env.example .env    # Windows
cp .env.example .env      # Linux
```

Edit `.env` with your values:

```env
GEMINI_API_KEY=AIzaSy-your-key-here
GOOGLE_APPLICATION_CREDENTIALS=
ASSISTANT_NAME=Shweta
DEFAULT_LANGUAGE=hi-IN
DEFAULT_CITY=Pune
LOG_LEVEL=INFO
```

> **Note:** Leave `GOOGLE_APPLICATION_CREDENTIALS` empty if you don't have Google Cloud TTS — the app will use free offline voice automatically.

### 7. Run the Assistant

```bash
python main.py
```

---

## 🗣️ Voice Commands Reference

### Hindi Commands

| Command | Action |
|---------|--------|
| "YouTube kholo" | Opens YouTube |
| "Google pe search karo [query]" | Google search |
| "Screenshot lo" | Takes screenshot |
| "Time kya hua hai" | Tells current time |
| "Aaj ki date batao" | Tells current date |
| "Volume badha do" | Increases volume |
| "Volume kam karo" | Decreases volume |
| "Mute karo" | Mutes volume |
| "Notepad kholo" | Opens Notepad |
| "Calculator kholo" | Opens Calculator |
| "Terminal kholo" | Opens CMD/Terminal |
| "VS Code kholo" | Opens VS Code |
| "Pune ka mausam batao" | Weather for Pune |
| "5 minute ka timer lagao" | Sets 5-min timer |
| "Screen lock karo" | Locks screen |
| "Band karo" / "Bye bye" | Exits assistant |

### English Commands

| Command | Action |
|---------|--------|
| "Open YouTube" | Opens YouTube |
| "Search for [query]" | Google search |
| "Take a screenshot" | Takes screenshot |
| "What's the time" | Tells current time |
| "Open Notepad" | Opens Notepad |
| "Weather in Mumbai" | Weather for Mumbai |
| "Set timer for 10 minutes" | Sets timer |
| "Close [app name]" | Closes an app |

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+A` | Toggle listening mode |
| `Ctrl+Shift+Q` | Quit the assistant |

---

## 🔧 Troubleshooting

### Microphone not detected
- Check if your microphone is connected and set as default
- On Linux, ensure `portaudio19-dev` is installed
- The app will show "⚠ Microphone not found" and disable the mic button

### Google TTS not working
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path in `.env`
- Ensure the Cloud TTS API is enabled in your Google Cloud project
- The app will fall back to offline `pyttsx3` TTS automatically

### Claude API errors
- Check your `ANTHROPIC_API_KEY` in `.env`
- Ensure you have API credits available
- Shweta will say "Kuch gadbad hui, thodi der mein try karein"

### PyAudio installation fails (Windows)
- Install Microsoft Visual C++ Build Tools, OR
- Download pre-built wheel from unofficial binaries

### No sound output
- Ensure `pygame` is installed correctly
- Check system volume is not muted
- Try running with `LOG_LEVEL=DEBUG` for more info

---

## 🧩 Adding New Skills

1. Create a new file in `assistant/skills/` (e.g., `music.py`)

2. Define your skill functions:
```python
def play_music(song: str) -> dict:
    # Your implementation
    return {"status": "success", "message": "Playing music"}
```

3. Register the action in `assistant/desktop_control.py`:
```python
from assistant.skills import music

# In __init__, add to self._action_map:
"play_music": self._play_music,

# Add wrapper method:
def _play_music(self, params):
    return music.play_music(params.get("song", ""))
```

4. Update the system prompt in `config.py` to include the new action

---

## 📁 Project Structure

```
shweta-ai-assistant/
├── main.py                    # Entry point
├── config.py                  # Configuration & settings
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── README.md                 # This file
├── assistant/
│   ├── __init__.py
│   ├── voice_input.py        # Speech recognition
│   ├── voice_output.py       # Text-to-speech
│   ├── ai_brain.py           # Claude AI integration
│   ├── desktop_control.py    # Action router
│   ├── ui.py                 # Tkinter animated UI
│   └── skills/
│       ├── __init__.py
│       ├── browser.py        # Web browsing skills
│       ├── system.py         # System control skills
│       ├── apps.py           # App management skills
│       ├── weather.py        # Weather (Open-Meteo)
│       └── timer.py          # Timers & reminders
├── logs/                     # Auto-created log files
│   ├── errors.log
│   └── chat_YYYY-MM-DD.txt
└── screenshots/              # Auto-created screenshots
```

---

## 📄 License

This project is for personal/educational use. APIs used have their own terms of service.

---

## 💡 Tips

- Shweta works best with a clear microphone and minimal background noise
- Speak naturally — the AI understands context and conversational Hindi
- You can ask follow-up questions; Shweta remembers the last 10 exchanges
- Say "naya conversation shuru karo" to clear memory
- The floating window stays on top — drag it anywhere you like

---

*Built with ❤️ using Python, Claude AI, and Google Cloud TTS*
