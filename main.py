"""
Shweta AI Desktop Assistant — Main Entry Point.
A voice-controlled AI desktop assistant with animated UI.
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
from assistant.ui import AssistantUI
from assistant.channels.telegram_bot import ShwetaTelegramBot

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

        # Initialize UI (must be on main thread)
        self.ui = AssistantUI(on_mic_click=self._on_mic_click)

        # Set mic button state based on microphone availability
        if not self.voice_input.is_available:
            self.ui.set_mic_enabled(False)
            self.ui.set_text("⚠ Microphone not found")

        # State tracking
        self._is_listening = False
        self._is_processing = False
        self._pending_confirm = None

        # Register global hotkeys
        self._register_hotkeys()

        # Wake word disabled — conflicts with mic recording
        # Use Ctrl+Shift+A hotkey or mic button instead

        # Start Telegram bot (background)
        self._start_telegram_bot()

        # Start command queue processor
        self._start_queue_processor()

        # Greet user on startup (instant — no delay)
        self.ui.root.after(300, self._greet)

    def _greet(self) -> None:
        """Play startup greeting with Edge TTS (natural voice)."""
        greeting = f"Namaste! Main {ASSISTANT_NAME} hoon."
        self.ui.set_text(greeting)
        self.ui.set_state(AssistantUI.STATE_SPEAKING)
        self.voice_output.speak(
            greeting,
            callback=lambda: self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)
        )

    def _on_mic_click(self) -> None:
        """Handle mic click — if stuck in thinking/speaking, reset. Otherwise start listening."""
        if self._is_processing or self._is_listening:
            # RESET — force stop everything and go back to idle
            self._is_processing = False
            self._is_listening = False
            self.voice_output.stop()
            self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)
            self.ui.schedule(self.ui.set_text, "Reset! Mic click karke phir bolo.")
            logger.info("User reset — back to idle.")
            return

        # Start listening in a background thread
        thread = threading.Thread(target=self._listen_and_process, daemon=True)
        thread.start()

    def _listen_and_process(self) -> None:
        """Listen for voice input and process it (runs in background thread)."""
        self._is_listening = True
        self.ui.schedule(self.ui.set_state, AssistantUI.STATE_LISTENING)

        # Listen for speech
        text = self.voice_input.listen()

        self._is_listening = False

        if not text:
            # No speech detected
            self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)
            self.ui.schedule(self.ui.set_text, "Samajh nahi aaya, phir se boliye...")
            self.voice_output.speak(
                "Samajh nahi aaya, phir se boliye.",
                callback=lambda: self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)
            )
            return

        # Show recognized text
        self.ui.schedule(self.ui.set_text, f"🗣 {text}")

        # Process with AI
        self._process_input(text)

    def _process_input(self, text: str) -> None:
        """
        Process user input through AI brain and execute actions.

        Args:
            text: Recognized speech text.
        """
        self._is_processing = True
        self.ui.schedule(self.ui.set_state, AssistantUI.STATE_THINKING)

        # Check for special commands
        if self._handle_special_commands(text):
            self._is_processing = False
            return

        # Send to AI brain
        response = self.ai_brain.think(text)

        action = response.get("action", "none")
        params = response.get("params", {})
        reply = response.get("reply", "")

        # First execute action, THEN speak (so action completes before voice)
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
                    self.ui.schedule(self.ui.set_state, AssistantUI.STATE_SPEAKING)
                    self.voice_output.speak(result["message"], callback=self._on_speaking_done)
                    # Store pending action for confirmation
                    self._pending_confirm = {"action": action, "params": params}
                    self._is_processing = False
                    return

                # If action returned useful info, use that as reply
                if result.get("status") == "success" and result.get("message"):
                    action_message = result["message"]

        # Use action result as reply if it has useful data (prices, weather, etc.)
        # Make it sound natural by combining AI reply + data
        info_actions = ["get_crypto_price", "get_stock_market", "get_news", "get_gold_price",
                        "get_weather", "get_battery", "get_ram_usage", "get_storage",
                        "get_cpu_usage", "get_wifi_status", "get_system_info", "get_time",
                        "get_date", "list_files", "search_file", "list_notes", "daily_briefing"]
        if action in info_actions and action_message:
            # Make it sound human — short natural sentence
            # Remove emojis and format naturally
            clean_msg = action_message.replace("📈", "").replace("📉", "").replace("🥇", "").replace("🥈", "").replace("🔋", "").replace("💾", "").replace("🖥️", "").replace("💿", "").replace("📝", "").replace("🕐", "").replace("🌤", "").strip()
            # Keep it short for TTS
            if len(clean_msg) > 150:
                clean_msg = clean_msg[:150]
            reply = clean_msg

        # Now speak the reply (action already done)
        if reply:
            self.ui.schedule(self.ui.set_text, f"💬 {reply}")
            self.ui.schedule(self.ui.set_state, AssistantUI.STATE_SPEAKING)
            self.voice_output.speak(reply, callback=self._on_speaking_done)
        else:
            self._is_processing = False
            self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)

    def _on_speaking_done(self) -> None:
        """Callback when TTS finishes speaking."""
        self._is_processing = False
        self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)

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
                self.ui.schedule(self.ui.set_state, AssistantUI.STATE_SPEAKING)
                self.voice_output.speak(
                    farewell,
                    callback=lambda: self.ui.schedule(self.ui.root.quit)
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
        self.ui.schedule(self.ui.set_text, f"⏰ {message}")
        self.ui.schedule(self.ui.set_state, AssistantUI.STATE_SPEAKING)
        self.voice_output.speak(
            message,
            callback=lambda: self.ui.schedule(self.ui.set_state, AssistantUI.STATE_IDLE)
        )

    def _start_telegram_bot(self) -> None:
        """Start Telegram bot in background thread."""
        try:
            def _desktop_action(action, params):
                return self.desktop_control.execute(action, params)

            def _ai_jawab(text):
                return self.ai_brain.think(text)

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
                lambda: self.ui.schedule(self.ui.root.quit),
                suppress=False
            )
            logger.info("Global hotkeys registered: Ctrl+Shift+A (listen), Ctrl+Shift+Q (quit)")
        except ImportError:
            logger.warning("keyboard library not available — hotkeys disabled.")
        except Exception as e:
            logger.warning(f"Failed to register hotkeys: {e}")

    def _start_wake_word(self) -> None:
        """Start wake word detection in background."""
        try:
            from assistant.skills.wakeword import WakeWordDetector
            self._wake_detector = WakeWordDetector(on_wake=self._on_mic_click)
            self._wake_detector.start()
        except Exception as e:
            logger.warning(f"Wake word detection not available: {e}")

    def _start_queue_processor(self) -> None:
        """Start processing the command queue on the UI thread."""
        def process():
            try:
                while not self.command_queue.empty():
                    func, args = self.command_queue.get_nowait()
                    func(*args)
            except queue.Empty:
                pass
            self.ui.root.after(100, process)

        self.ui.root.after(100, process)

    def run(self) -> None:
        """Start the assistant (blocks on UI main loop)."""
        logger.info(f"{ASSISTANT_NAME} is ready!")
        self.ui.run()

        # Cleanup on exit
        self.desktop_control.timer_manager.cancel_all()
        logger.info(f"{ASSISTANT_NAME} shut down.")


def main() -> None:
    """Application entry point."""
    try:
        app = ShwetaAssistant()
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
