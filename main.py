"""
Shweta AI Desktop Assistant — Main Entry Point.
A voice-controlled AI desktop assistant with animated 3D avatar UI.

UI: PyQt5 AvatarWindow (3D VRM avatar with lip sync)
Old Tkinter UI is commented out below for easy rollback.
"""

import logging
import queue
import sys
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import ASSISTANT_NAME, LOG_LEVEL, LOGS_DIR
from assistant.voice_input import VoiceInput
from assistant.voice_output import VoiceOutput
from assistant.ai_brain import AIBrain
from assistant.desktop_control import DesktopController
from assistant.channels.telegram_bot import ShwetaTelegramBot
from assistant.activation import setup_activation
from assistant.skills.proactive_agent import ProactiveManager

# --- OLD TKINTER UI (commented out — kept for easy rollback) ---
# from assistant.ui import AssistantUI
# To revert: uncomment above, comment out AvatarWindow import below,
# and replace all AvatarWindow usage with AssistantUI in ShwetaAssistant.

# --- NEW PyQt5 Avatar UI ---
sys.path.insert(0, str(Path(__file__).parent / "assistant" / "ui"))
from avatar_window import AvatarWindow

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "errors.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ShwetaAssistant:
    """Main application class that orchestrates all components."""

    def __init__(self) -> None:
        """Initialize all assistant components."""
        logger.info(f"Starting {ASSISTANT_NAME} AI Desktop Assistant...")

        # Command queue for thread-safe communication
        self.command_queue: queue.Queue = queue.Queue()

        # Initialize components
        self.voice_input = VoiceInput()
        self.voice_output = VoiceOutput()
        self.ai_brain = AIBrain()
        self.desktop_control = DesktopController(
            on_timer_complete=self._on_timer_complete
        )

        # Initialize PyQt5 Avatar UI (main thread)
        self.ui = AvatarWindow(on_mic_click=self._on_mic_click, on_quick_action=self._on_quick_action)

        # Connect lip sync: voice_output → avatar
        self.voice_output.set_lip_sync_callback(self._on_lip_sync)

        # Connect window shake reactions to voice output (with intensity)
        self.ui.set_speak_reaction_fn(lambda text: self.voice_output.speak_reaction(text))

        # Connect music vibe to avatar
        self.desktop_control.set_music_vibe_callback(self._on_music_vibe)

        # Connect change style callback
        self.desktop_control.set_change_style_callback(self._on_change_style)

        # Set mic button state based on microphone availability
        if not self.voice_input.is_available:
            self.ui.set_mic_enabled(False)
            self.ui.set_text("⚠ Microphone not found")

        # State tracking
        self._is_listening = False
        self._is_processing = False
        self._pending_confirm = None
        self._is_music_active = False
        import time
        self._last_activity_time = time.time()

        # Register global hotkeys
        self._register_hotkeys()

        # Wake word — separate process, no mic conflict
        self._start_wake_word()

        # Start Telegram bot (background)
        self._start_telegram_bot()

        # Connect health reminders to voice
        self.desktop_control.health.speak = lambda text: self.voice_output.speak(text)

        # Connect language manager to voice output
        self.desktop_control.language  # initialized

        # Start idle check timer (checks every 10 seconds)
        self._init_idle_timer()

        # Initialize Daily Briefing Manager
        from assistant.skills.daily_briefing import DailyBriefingManager
        self.briefing_manager = DailyBriefingManager()

        # Initialize Proactive Notifications Manager
        self.proactive_manager = ProactiveManager(
            ai_brain=self.ai_brain,
            desktop_control=self.desktop_control,
            on_notify_callback=self._on_proactive_notify
        )
        self.proactive_manager.start()

        # Greet user on startup — deliver briefing if first time today, else simple greet
        # Wait for avatar to fully load (VRM takes ~3 sec)
        QTimer_singleshot_greet = threading.Timer(5.0, self._startup_greet_or_briefing)
        QTimer_singleshot_greet.daemon = True
        QTimer_singleshot_greet.start()

    def _startup_greet_or_briefing(self) -> None:
        """On startup: deliver daily briefing if not yet done today, else simple greet."""
        from assistant.skills.daily_briefing import should_brief_today, is_briefing_time

        # Set callbacks for briefing manager
        self.briefing_manager.set_callbacks(
            speak_fn=lambda text: self.voice_output.speak(
                text,
                callback=lambda: self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
            ),
            set_emotion_fn=lambda e, i: self.ui.schedule(self.ui.set_emotion, e, i),
            show_bubble_fn=lambda t, d: self.ui.schedule(self.ui.show_chat_bubble, t, d),
        )

        if should_brief_today() and is_briefing_time():
            # Deliver full briefing
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
            self.ui.schedule(self.ui.set_emotion, "happy", 0.8)
            self.briefing_manager.deliver()
        else:
            # Simple greeting
            greeting = f"Namaste! Main {ASSISTANT_NAME} hoon."
            self.ui.schedule(self.ui.set_text, greeting)
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
            self.voice_output.speak(
                greeting,
                callback=lambda: self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
            )

    def _on_proactive_notify(self, message: str) -> None:
        """Callback when the ProactiveManager wants to notify the user."""
        # Only notify if we are idle
        if self._is_processing or self._is_listening or self.voice_output.is_speaking or self._is_music_active:
            logger.info("Skipped proactive notification because assistant is busy.")
            return

        self._is_processing = True
        self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
        self.ui.schedule(self.ui.set_emotion, "neutral", 0.6)
        self.ui.schedule(self.ui.set_text, f"🔔 {message}")
        self.ui.schedule(self.ui.show_chat_bubble, message, 6.0)
        
        current_voice = self.desktop_control.language.get_voice()
        self.voice_output.speak(message, voice=current_voice, callback=self._on_speaking_done)

    def _on_lip_sync(self, volume: float) -> None:
        """Callback from voice_output with audio volume for lip sync."""
        self.ui.schedule(self.ui.set_lip_sync, volume)

    def _on_music_vibe(self, mood: str, bpm: int) -> None:
        """Callback when music starts/stops — trigger avatar vibe animation."""
        if mood == "stop":
            js_code = "if(window.stopMusicVibe) window.stopMusicVibe()"
            self._is_music_active = False
        else:
            js_code = f"if(window.startMusicVibe) window.startMusicVibe('{mood}', {bpm})"
            self._is_music_active = True
        self.ui.schedule(lambda: self.ui._run_js(js_code))
        logger.info(f"[Music Vibe] {mood} @ {bpm} BPM")

    def _on_change_style(self, style_type: str) -> None:
        """Callback to change avatar style."""
        self.ui.schedule(lambda: self.ui.change_style(style_type))

    def _on_quick_action(self, action_str: str) -> None:
        """Handle quick action button clicks from avatar UI."""
        import time
        self._last_activity_time = time.time()
        if self._is_processing:
            return

        def _execute():
            self._is_processing = True
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_THINKING)
            try:
                # Parse action string (format: "action_name" or "action_name:param")
                parts = action_str.split(":", 1)
                action = parts[0]
                params = {}
                if len(parts) > 1:
                    params = {"mood": parts[1]} if action == "spotify_mood" else {"city": parts[1]}

                result = self.desktop_control.execute(action, params)
                reply = result.get("message", "Done!")

                self.ui.schedule(self.ui.set_text, f"💬 {reply}")
                self.ui.schedule(self.ui.show_chat_bubble, reply, 5.0)
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
                current_voice = self.desktop_control.language.get_voice()
                self.voice_output.speak(reply, voice=current_voice, callback=self._on_speaking_done)
            except Exception as e:
                logger.error(f"Quick action failed: {e}")
                self._is_processing = False
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)

        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()

    def _on_mic_click(self) -> None:
        """Handle mic click — if stuck in thinking/speaking, reset. Otherwise start listening."""
        import time
        self._last_activity_time = time.time()

        if getattr(self, '_is_idle_talking', False):
            # Interrupted idle speech! Stop speaking immediately and proceed to listen
            self.voice_output.stop()
            self._is_idle_talking = False
            self._is_processing = False
            logger.info("Idle talking interrupted. Listening...")
        elif self._is_processing or self._is_listening:
            # RESET — force stop everything and go back to idle
            self._is_processing = False
            self._is_listening = False
            self.voice_output.stop()
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
            self.ui.schedule(self.ui.set_text, "Reset! Click again to speak.")
            logger.info("User reset — back to idle.")
            return

        # Start listening in a background thread
        thread = threading.Thread(target=self._listen_and_process, daemon=True)
        thread.start()

    def _listen_and_process(self) -> None:
        """Listen for voice input and process it (runs in background thread)."""
        try:
            self._is_listening = True
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_LISTENING)

            # Listen with VAD callbacks
            def on_listening():
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_LISTENING)

            def on_processing():
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_THINKING)

            text = self.voice_input.listen(on_listening=on_listening, on_processing=on_processing)

            self._is_listening = False

            if not text:
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
                self.ui.schedule(self.ui.set_text, "Samajh nahi aaya, phir se boliye...")
                self.voice_output.speak(
                    "Samajh nahi aaya, phir se boliye.",
                    callback=lambda: self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
                )
                return

            # Show recognized text
            self.ui.schedule(self.ui.set_text, f"🗣 {text}")

            # Process with AI
            self._process_input(text)

        except Exception as e:
            logger.error(f"Listen/process error: {e}", exc_info=True)
            self._is_listening = False
            self._is_processing = False
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
            self.ui.schedule(self.ui.set_text, "Kuch gadbad hui, phir try karo.")

    def _process_input(self, text: str) -> None:
        """
        Process user input through AI brain and execute actions.

        Args:
            text: Recognized speech text.
        """
        import time
        self._last_activity_time = time.time()
        self._is_processing = True
        self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_THINKING)
        self.ui.schedule(self.ui.show_typing_bubble)

        # Check for special commands
        if self._handle_special_commands(text):
            self._is_processing = False
            return

        # Feed user context to AI (learning)
        try:
            self.ai_brain._user_context = self.desktop_control.learner.get_ai_context()
        except Exception:
            pass

        # Send to AI brain (with language detection)
        response = self.ai_brain.think(text, language_manager=self.desktop_control.language)

        # Track user patterns
        try:
            self.desktop_control.learner.track_topic(text)
        except Exception:
            pass

        action = response.get("action", "none")
        params = response.get("params", {})
        reply = response.get("reply", "")
        emotion = response.get("emotion", "neutral")

        # SAFETY: Ensure params is dict, action is string
        if not isinstance(params, dict):
            params = {}
        if not isinstance(action, str):
            action = "none"
        if not isinstance(reply, str):
            reply = str(reply) if reply else ""
        if not isinstance(emotion, str):
            emotion = "neutral"

        # FALLBACK: If AI promised to play music in reply but didn't send action
        if (action == "none" or not action) and reply:
            reply_lower = reply.lower()
            music_promises = ["music", "song", "gana", "bajati", "lagati", "play karti", "sunati", "playlist"]
            if any(word in reply_lower for word in music_promises):
                # AI promised music but forgot action — auto-fix
                # Use Spotify for mood-based, YouTube for specific songs
                if any(m in reply_lower for m in ["calm", "relax", "shant", "chill", "lofi"]):
                    action = "spotify_mood"
                    params = {"mood": "chill"}
                elif any(m in reply_lower for m in ["happy", "khush", "upbeat"]):
                    action = "spotify_mood"
                    params = {"mood": "happy"}
                elif any(m in reply_lower for m in ["sad", "dukh", "udaas"]):
                    action = "spotify_mood"
                    params = {"mood": "sad"}
                elif any(m in reply_lower for m in ["coding", "focus", "concentrate"]):
                    action = "spotify_mood"
                    params = {"mood": "coding"}
                elif any(m in reply_lower for m in ["workout", "gym", "exercise"]):
                    action = "spotify_mood"
                    params = {"mood": "workout"}
                else:
                    action = "spotify_mood"
                    params = {"mood": "chill"}
                logger.info(f"[FALLBACK] AI promised music — using spotify_mood: {params['mood']}")

        # Set avatar emotion based on AI response
        if emotion:
            self.ui.schedule(self.ui.set_emotion, emotion, 0.8 if emotion != "neutral" else 0.0)
            # Track mood for learning
            try:
                self.desktop_control.learner.track_mood(emotion)
            except Exception:
                pass

        # Stop music vibe if the current command is not related to music
        music_actions = {"play_youtube", "spotify_play_song", "spotify_play_playlist", "spotify_mood", "spotify_next", "spotify_previous", "spotify_play_pause", "media_play_pause", "media_next", "media_previous"}
        if not action or action == "none" or action not in music_actions:
            self.desktop_control._stop_music_vibe()

        # Execute action first (if any)
        action_message = ""
        if action and action != "none":
            if action == "clear_history":
                self.ai_brain.clear_history()
            else:
                result = self.desktop_control.execute(action, params)
                logger.info(f"Action result: {result}")

                # Handle confirmation-needed actions
                if result.get("status") == "confirm_needed":
                    self.ui.schedule(self.ui.set_text, result["message"])
                    self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
                    current_voice = self.desktop_control.language.get_voice()
                    self.voice_output.speak(result["message"], voice=current_voice, callback=self._on_speaking_done)
                    self._pending_confirm = {"action": action, "params": params}
                    self._is_processing = False
                    return

                # If action returned useful info, use that as reply
                if result.get("status") == "success" and result.get("message"):
                    action_message = result["message"]

        # For info actions: use action result as the spoken reply
        info_actions = ["get_crypto_price", "get_stock_market", "get_news", "get_gold_price",
                        "get_battery", "get_ram_usage", "get_storage",
                        "get_cpu_usage", "get_wifi_status", "get_system_info", "get_time",
                        "get_date", "list_files", "search_file", "list_notes", "daily_briefing",
                        "morning_briefing", "browser_agent_task"]
        if action in info_actions and action_message:
            clean_msg = action_message.replace("📈", "").replace("📉", "").replace("🥇", "").replace("🥈", "").replace("🔋", "").replace("💾", "").replace("🖥️", "").replace("💿", "").replace("📝", "").replace("🕐", "").replace("🌤", "").strip()
            # Browser agent needs more chars for product recommendations
            max_len = 300 if action == "browser_agent_task" else 150
            if len(clean_msg) > max_len:
                clean_msg = clean_msg[:max_len]
            reply = clean_msg

        # Speak the reply (once only)
        if reply:
            self.ui.schedule(self.ui.set_text, f"💬 {reply}")
            self.ui.schedule(self.ui.show_chat_bubble, reply, 6.0)
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
            current_voice = self.desktop_control.language.get_voice()
            self.voice_output.speak(reply, voice=current_voice, callback=self._on_speaking_done)
        else:
            self._is_processing = False
            self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
            self.ui.schedule(self.ui.hide_chat_bubble)

    def _on_speaking_done(self) -> None:
        """Callback when TTS finishes speaking."""
        import time
        self._is_processing = False
        self._is_idle_talking = False
        self._last_activity_time = time.time()
        self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)

    def _init_idle_timer(self) -> None:
        """Initialize the background checker for idle state."""
        from PyQt5.QtCore import QTimer
        self._idle_timer = QTimer(self.ui)
        self._idle_timer.setInterval(10000)  # Check every 10 seconds
        self._idle_timer.timeout.connect(self._check_idle_activity)
        self._idle_timer.start()

    def _check_idle_activity(self) -> None:
        """Check if user has been inactive for too long and trigger idle behavior."""
        import time
        # If Shweta is actively processing, listening, speaking, or if music is active, reset activity timer
        if self._is_processing or self._is_listening or self.voice_output.is_speaking or self._is_music_active:
            self._last_activity_time = time.time()
            return

        idle_duration = time.time() - self._last_activity_time
        # Idle behavior threshold: 45 seconds
        if idle_duration >= 45:
            self._trigger_idle_behavior()

    def _trigger_idle_behavior(self) -> None:
        """Trigger a cute idle behavior (animation, text bubble, and spoken phrase) to show Shweta is alive."""
        if self._is_processing or self._is_listening or self.voice_output.is_speaking or self._is_music_active:
            return
            
        import random
        import time
        # Reset last activity time so we don't spam behaviors
        self._last_activity_time = time.time()
        
        behaviors = [
            {"phrase": "Arey yaar, tum toh kuch bol hi nahi rahe ho. Main bore ho rahi hoon!", "emotion": "sad", "animation": "down"},
            {"phrase": "Oye! So gaye kya? Chalo jaldi se kuch kaam batao!", "emotion": "happy", "animation": "left"},
            {"phrase": "Hmm, bohot sannata hai yahan. Kuch interesting baat karo na.", "emotion": "relaxed", "animation": "right"},
            {"phrase": "Acha suno, agar free ho toh chalo rock-paper-scissors khelte hain!", "emotion": "happy", "animation": "up"},
            {"phrase": "Batao na re, kya chal raha hai? Main kab se baithi hoon aise hi.", "emotion": "relaxed", "animation": "left"}
        ]
        b = random.choice(behaviors)
        
        self._is_idle_talking = True
        self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
        self.ui.schedule(self.ui.set_emotion, b["emotion"], 0.6)
        self.ui.schedule(self.ui.set_text, f"💬 {b['phrase']}")
        self.ui.schedule(self.ui.show_chat_bubble, b["phrase"], 6.0)
        
        # Trigger head turn animation
        js_code = f"if(window.setReactionAnimation) window.setReactionAnimation('{b['animation']}')"
        self.ui.schedule(lambda: self.ui._run_js(js_code))
        
        # Speak the phrase aloud
        current_voice = self.desktop_control.language.get_voice()
        self._is_processing = True # Mark as processing to block other idle checks
        self.voice_output.speak(b["phrase"], voice=current_voice, callback=self._on_speaking_done)

    def _handle_special_commands(self, text: str) -> bool:
        """
        Handle special built-in commands.

        Args:
            text: User input text.

        Returns:
            True if a special command was handled.
        """
        text_lower = text.lower().strip()

        # Handle confirmation for pending destructive actions
        if hasattr(self, '_pending_confirm') and self._pending_confirm:
            confirm_words = ["haan", "yes", "kar do", "karo", "confirm", "ok"]
            cancel_words = ["nahi", "no", "cancel", "mat karo", "ruko"]

            if any(w in text_lower for w in confirm_words):
                pending = self._pending_confirm
                self._pending_confirm = None
                # Execute the confirmed action
                if pending["action"] == "shutdown_pc":
                    from assistant.skills import system
                    system.shutdown_pc()
                    reply = "PC shutdown ho raha hai!"
                elif pending["action"] == "restart_pc":
                    from assistant.skills import system
                    system.restart_pc()
                    reply = "PC restart ho raha hai!"
                self.ui.schedule(self.ui.set_text, reply)
                self.voice_output.speak(reply)
                return True
            elif any(w in text_lower for w in cancel_words):
                self._pending_confirm = None
                self.ui.schedule(self.ui.set_text, "Cancel kar diya.")
                self.voice_output.speak("Theek hai, cancel kar diya.")
                return True

        # Quit commands
        quit_phrases = ["band karo", "bye bye", "goodbye", "quit", "exit", "band ho jao"]
        for phrase in quit_phrases:
            if phrase in text_lower:
                farewell = "Alvida! Phir milenge. Apna khayal rakhiye!"
                self.ui.schedule(self.ui.set_text, farewell)
                self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
                self.voice_output.speak(
                    farewell,
                    callback=lambda: self.ui.schedule(self.ui._close)
                )
                return True

        return False

    def _on_timer_complete(self, timer_id: str, message: str) -> None:
        """
        Callback when a timer/reminder completes.

        Args:
            timer_id: The completed timer's ID.
            message: The timer message.
        """
        import random

        # Determine if it's a timer or a reminder
        is_reminder = False
        task_text = message

        try:
            with self.desktop_control.timer_manager._lock:
                timer_info = self.desktop_control.timer_manager._timers.get(timer_id)
                if timer_info:
                    is_reminder = (timer_info.get("type") == "reminder")
        except Exception:
            pass

        if not is_reminder and message.startswith("Reminder:"):
            is_reminder = True

        if is_reminder:
            # Extract the actual task from message like "Reminder: study"
            if message.startswith("Reminder:"):
                task_text = message[len("Reminder:"):].strip()

            roasts = [
                f"Arey sun! Tujhe yaad dilana tha: {task_text}. Chal ab nakhre chhod aur jaldi se ye kar!",
                f"Tujhe bada yaad dilana padta hai re! Chal jaldi se kaam kar: {task_text}.",
                f"Oye! Aloo bhujia khana band kar aur jaldi se ye kaam kar: {task_text}. Kab se wait kar rahi hoon!",
                f"Dekho ji, tumhara reminder baj raha hai: {task_text}. Baad me mat bolna ki main batana bhool gayi!",
                f"Arey yaar, kitne reminders lagate ho! Chalo ab jaldi se karo: {task_text}."
            ]
            final_message = random.choice(roasts)
            ui_message = f"Reminder: {task_text}"
        else:
            roasts = [
                "Uth jaa re lazy bones! Kab tak soyega? PC tera raasta dekh raha hai!",
                "Suno re! Jo timer lagaya tha wo khatam ho gaya. Ab kaam shuru karo, nakhre mat dikhao!",
                "Chalo chalo, break over! Tumhara timer kab ka baj chuka hai, ab mehnat karo thodi!",
                "Ding dong! Timer khatam! Chalo ab jaldi se screen pe dhyan do, idhar udhar mat dekho!",
                "Arey! Timer baj gaya re baba! Ab toh kaam shuru kar do, ya bas vibing hi karte rahoge?"
            ]
            final_message = random.choice(roasts)
            ui_message = "Timer complete!"

        self.ui.schedule(self.ui.set_text, f"⏰ {ui_message}")
        self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_SPEAKING)
        self.voice_output.speak(
            final_message,
            callback=lambda: self.ui.schedule(self.ui.set_state, AvatarWindow.STATE_IDLE)
        )

    def _start_telegram_bot(self) -> None:
        """Start Telegram bot in background thread."""
        try:
            def _desktop_action(action, params):
                return self.desktop_control.execute(action, params)

            def _ai_jawab(text):
                return self.ai_brain.think(text, language_manager=self.desktop_control.language)

            def _bolna(text):
                self.voice_output.speak(text)

            self.telegram_bot = ShwetaTelegramBot(
                desktop_action_fn=_desktop_action,
                ai_brain_fn=_ai_jawab,
                bolna_fn=_bolna
            )
            self.telegram_bot.start_in_thread()
        except Exception as e:
            logger.warning(f"Telegram bot start failed: {e}")

    def _register_hotkeys(self) -> None:
        """Register global hotkeys using keyboard library."""
        try:
            import keyboard

            keyboard.add_hotkey(
                "ctrl+shift+a",
                self._on_mic_click,
                suppress=False
            )
            keyboard.add_hotkey(
                "ctrl+shift+q",
                lambda: self.ui.schedule(self.ui._close),
                suppress=False
            )
            logger.info("Global hotkeys registered: Ctrl+Shift+A (listen), Ctrl+Shift+Q (quit)")
        except ImportError:
            logger.warning("keyboard library not available — hotkeys disabled.")
        except Exception as e:
            logger.warning(f"Failed to register hotkeys: {e}")

    def _start_wake_word(self) -> None:
        """Start wake word detection in separate process (no mic conflict)."""
        try:
            from assistant.skills.wakeword import WakeWordManager

            def on_wake():
                # Trigger listen flow (same as mic button click)
                self._on_mic_click()

            self._wake_manager = WakeWordManager(
                on_wake_callback=on_wake,
                sensitivity=0.5
            )
            self._wake_manager.start()
        except Exception as e:
            logger.warning(f"Wake word not available: {e}")

    def run(self) -> None:
        """Start the assistant (blocks on PyQt5 main loop)."""
        logger.info(f"{ASSISTANT_NAME} is ready!")
        self.ui.run()

        # Cleanup on exit
        self.desktop_control.timer_manager.cancel_all()
        if hasattr(self, '_wake_manager'):
            self._wake_manager.stop()
        if hasattr(self, 'proactive_manager'):
            self.proactive_manager.stop()
        logger.info(f"{ASSISTANT_NAME} shut down.")


def main() -> None:
    """Application entry point."""
    try:
        # === ACTIVATION CHECK (before anything else) ===
        # In dev mode (no bundle file) this is skipped automatically
        if not setup_activation():
            logger.info("Activation cancelled — exiting.")
            sys.exit(0)

        app = ShwetaAssistant()
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
