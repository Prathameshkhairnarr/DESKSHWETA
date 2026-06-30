"""
Shweta 3D Avatar Window — PyQt5 + QWebEngineView + Local HTTP Server.
Serves VRM file via localhost to avoid file:// CORS issues.

This is now the PRIMARY UI for Shweta (replaces Tkinter).
Provides the same public API as the old AssistantUI:
  - set_state(state)
  - set_text(text)
  - set_mic_enabled(enabled)
  - schedule(func, *args)
  - run()
"""

import http.server
import logging
import os
import random
import sys
import threading
import time
import numpy as np
from collections import deque
from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtWidgets import QMainWindow, QApplication, QLabel, QWidget, QVBoxLayout, QSystemTrayIcon, QMenu, QAction, QSizeGrip
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEnginePage
from PyQt5.QtCore import QUrl, Qt, QTimer, QPoint, pyqtSignal, QObject, QMetaObject, Q_ARG
from PyQt5.QtGui import QColor, QFont, QCursor, QIcon, QPixmap

logger = logging.getLogger(__name__)

# Avatar files directory
AVATAR_DIR = Path(__file__).parent / "avatar"
HTTP_PORT = 8765


def _start_local_server():
    """Start a simple HTTP server to serve avatar files (VRM, HTML)."""
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(AVATAR_DIR))
    server = http.server.HTTPServer(("127.0.0.1", HTTP_PORT), handler)
    server.serve_forever()


class CustomWebEnginePage(QWebEnginePage):
    """Custom page subclass to redirect JavaScript console messages to Python logs."""
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        logger.warning(f"[JS Console] Line {lineNumber} of {sourceID}: {message}")


class AvatarWindow(QMainWindow):
    """
    3D VRM Avatar window for Shweta AI Assistant.
    
    Drop-in replacement for AssistantUI (Tkinter).
    Same public API: set_state, set_text, set_mic_enabled, schedule, run.
    """

    # State constants (same as old AssistantUI)
    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING = "thinking"
    STATE_SPEAKING = "speaking"

    # Qt signal for thread-safe UI updates from background threads
    _schedule_signal = pyqtSignal(object, tuple)

    def __init__(self, on_mic_click: Optional[Callable] = None, on_quick_action: Optional[Callable] = None) -> None:
        # Create QApplication if not already running
        self._app = QApplication.instance()
        if self._app is None:
            self._app = QApplication(sys.argv)

        super().__init__()

        self.on_mic_click = on_mic_click
        self._on_quick_action = on_quick_action
        self.state = self.STATE_IDLE

        # Connect schedule signal (thread-safe cross-thread calls)
        self._schedule_signal.connect(self._execute_scheduled)

        # Start local HTTP server for VRM files
        self._server_thread = threading.Thread(target=_start_local_server, daemon=True)
        self._server_thread.start()

        # Window config
        self.setWindowTitle("Shweta")
        self.setMinimumSize(280, 400)   # Min size
        self.resize(400, 650)           # Default size (resizable)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Position bottom-right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 420, screen.height() - 710)

        # Central widget
        central = QWidget(self)
        self.setCentralWidget(central)
        central.setStyleSheet("background: transparent;")

        # --- WebEngine view ---
        self.web = QWebEngineView(central)
        self.web.setAttribute(Qt.WA_TranslucentBackground)
        self.web.setPage(CustomWebEnginePage(self.web))
        self.web.setGeometry(0, 0, self.width(), self.height())

        # Enable WebGL
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

        # Background transparent
        self.web.page().setBackgroundColor(Qt.transparent)

        # Watch title changes for drag signals from JS
        self.web.page().titleChanged.connect(self._on_title_change)

        # --- Bottom labels removed — avatar takes full space ---
        # Text/status shown only via avatar's HTML overlay
        self._text_label = None
        self._status_label = None
        self._mic_hint = None

        # Mic enabled flag
        self._mic_enabled = True

        # Load page after short delay (server needs to start)
        QTimer.singleShot(500, self._load_page)

        # Drag state
        self._drag_pos = QPoint()
        self._dragging = False

        # Lip sync timer (for smooth decay when not speaking)
        self._lip_timer = QTimer(self)
        self._lip_timer.timeout.connect(self._decay_lip_sync)
        self._lip_timer.start(50)  # 20fps lip sync update
        self._current_lip_volume = 0.0

        # --- System Tray ---
        self._setup_tray()

        # --- Window Move/Shake Reaction System ---
        self._move_history: deque = deque(maxlen=20)
        self._last_move_pos: Optional[QPoint] = None
        self._shake_cooldown: bool = False
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_settle)
        self._was_moved: bool = False
        self._last_shake_intensity: str = "slow"  # Track for settle reaction
        self._speak_reaction_fn: Optional[Callable] = None  # Set by main.py
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_bored)
        self._idle_timer.start(600000)  # 10 minutes

        # Add resize grip to bottom right corner (transparent overlay)
        self.sizegrip = QSizeGrip(self)
        self.sizegrip.setStyleSheet("background: transparent;")
        self.sizegrip.raise_()

    # Voice reaction pools — now uses reaction_lines module for dramatic lines
    VOICE_REACTIONS = None  # Deprecated — using get_reaction_lines() instead

    def _setup_tray(self):
        """Setup system tray icon with right-click menu."""
        # Create tray icon (cyan circle as icon)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(0, 0, 0, 0))
        from PyQt5.QtGui import QPainter, QBrush
        painter = QPainter(pixmap)
        painter.setBrush(QBrush(QColor(0, 212, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()

        self._tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self._tray_icon.setToolTip("Shweta AI Assistant")

        # Tray menu
        tray_menu = QMenu()
        show_action = QAction("Show Shweta", self)
        show_action.triggered.connect(self._tray_show)
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self._tray_hide)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._close)

        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._tray_activated)
        self._tray_icon.show()

    def _tray_activated(self, reason):
        """Handle tray icon clicks."""
        if reason == QSystemTrayIcon.DoubleClick:
            self._tray_show()

    def _tray_show(self):
        """Show window from tray."""
        self.show()
        self.activateWindow()

    def _tray_hide(self):
        """Hide window to tray — voice still works."""
        self.hide()
        self._was_hidden = True

    def _load_page(self):
        """Load viewer.html via local HTTP server with cache bust."""
        import time
        bust = int(time.time())
        self.web.setUrl(QUrl(f"http://127.0.0.1:{HTTP_PORT}/viewer.html?v={bust}"))

    # ========== PUBLIC API (same as old AssistantUI) ==========

    def set_state(self, state: str) -> None:
        """Set avatar state: idle, listening, thinking, speaking."""
        self.state = state
        self._run_js(f"if(window.setAvatarState) window.setAvatarState('{state}')")

        if state == self.STATE_IDLE:
            # Reset lip sync when idle
            self.set_lip_sync(0.0)

    def set_text(self, text: str) -> None:
        """Set the display text (shown in avatar's HTML status area)."""
        # Escape quotes for JS
        escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        display = escaped[:100]
        self._run_js(f"if(window.setStatusText) window.setStatusText('{display}')")

    def set_mic_enabled(self, enabled: bool) -> None:
        """Enable/disable mic click."""
        self._mic_enabled = enabled

    def schedule(self, func: Callable, *args) -> None:
        """
        Thread-safe: schedule a function to run on the main Qt thread.
        Replaces Tkinter's root.after(0, func, *args).
        """
        self._schedule_signal.emit(func, args)

    def run(self) -> None:
        """Start the Qt event loop (blocks like Tkinter mainloop)."""
        self.show()
        self._app.exec_()

    # ========== LIP SYNC API ==========

    def set_lip_sync(self, volume: float) -> None:
        """Set lip sync volume (0.0 to 1.0). Called from voice_output."""
        vol = max(0.0, min(1.0, volume))
        self._current_lip_volume = vol
        self._run_js(f"if(window.setLipSync) window.setLipSync({vol:.3f})")

    def set_emotion(self, emotion: str, intensity: float = 0.8) -> None:
        """Set avatar emotion: happy, angry, sad, surprised, relaxed, neutral."""
        self._run_js(f"if(window.setEmotion) window.setEmotion('{emotion}', {intensity:.2f})")

    def change_style(self, style_type: str) -> None:
        """Change avatar style/outfit: glasses, hair_accessory, jacket, color_shift."""
        self._run_js(f"if(window.changeStyle) window.changeStyle('{style_type}')")

    def show_chat_bubble(self, text: str, duration: float = 5.0) -> None:
        """Show translucent chat bubble with text. Auto-fades after duration seconds."""
        escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        display = escaped[:120]
        self._run_js(f"if(window.showChatBubble) window.showChatBubble('{display}', {duration})")

    def show_typing_bubble(self) -> None:
        """Show typing dots animation in chat bubble (thinking state)."""
        self._run_js("if(window.showTypingBubble) window.showTypingBubble()")

    def hide_chat_bubble(self) -> None:
        """Hide the chat bubble."""
        self._run_js("if(window.hideChatBubble) window.hideChatBubble()")

    # ========== INTERNAL ==========

    def _execute_scheduled(self, func, args):
        """Execute a scheduled function on the main thread."""
        try:
            func(*args)
        except Exception as e:
            logger.error(f"Scheduled call failed: {e}")

    def _decay_lip_sync(self):
        """Smoothly decay lip sync to 0 when not actively speaking."""
        if self.state != self.STATE_SPEAKING and self._current_lip_volume > 0:
            self._current_lip_volume = max(0, self._current_lip_volume - 0.1)
            self._run_js(f"if(window.setLipSync) window.setLipSync({self._current_lip_volume:.3f})")

    def _run_js(self, code: str) -> None:
        """Run JavaScript in the WebEngine (thread-safe via QTimer)."""
        QTimer.singleShot(0, lambda: self.web.page().runJavaScript(code))

    def _on_title_change(self, title):
        """Handle signals from JavaScript via title changes."""
        if title.startswith('DRAG:'):
            parts = title.split(':')
            if len(parts) == 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    self.move(x, y)
                except ValueError:
                    pass
        elif title.startswith('RESIZE:'):
            parts = title.split(':')
            if len(parts) == 3:
                try:
                    w, h = int(parts[1]), int(parts[2])
                    self.resize(w, h)
                except ValueError:
                    pass
        elif title == 'MIC_CLICK':
            # Avatar clicked — trigger mic
            if self._mic_enabled and self.on_mic_click:
                self.on_mic_click()
        elif title.startswith('ACTION:'):
            # Quick action button clicked
            if self._on_quick_action:
                action_str = title[7:]  # Remove "ACTION:"
                self._on_quick_action(action_str)

    def _close(self) -> None:
        """Close the window and quit the app."""
        try:
            self._app.quit()
        except Exception:
            pass

    # ========== WINDOW MOVE/SHAKE REACTIONS ==========

    def set_speak_reaction_fn(self, fn: Callable) -> None:
        """Set the function to call for speaking reactions (from main.py)."""
        self._speak_reaction_fn = fn

    def moveEvent(self, event):
        """Track window movement for shake/drag reactions."""
        super().moveEvent(event)
        current_pos = self.pos()

        if self._last_move_pos is None:
            self._last_move_pos = current_pos
            return

        dx = current_pos.x() - self._last_move_pos.x()
        dy = current_pos.y() - self._last_move_pos.y()
        self._last_move_pos = current_pos

        # Ignore OS snap (huge jumps)
        if abs(dx) > 200 or abs(dy) > 200:
            return

        # Record movement
        self._move_history.append((time.time(), dx, dy))
        self._was_moved = True

        # Reset settle timer (fires 1.5s after last movement)
        self._settle_timer.stop()
        self._settle_timer.start(1500)

        # Check for shake first (priority)
        shake = self._detect_shake()
        if shake:
            self._trigger_reaction(shake)
            return

        # Check direction (only if not shaking)
        direction = self._detect_direction(dx, dy)
        if direction:
            self._trigger_reaction(direction)

    def _detect_shake(self) -> Optional[str]:
        """Detect rapid left-right shaking."""
        if len(self._move_history) < 6:
            return None

        now = time.time()
        recent = [(t, dx, dy) for t, dx, dy in self._move_history if now - t < 0.5]

        if len(recent) < 4:
            return None

        # Count direction changes (X axis)
        direction_changes = 0
        for i in range(1, len(recent)):
            if recent[i][1] != 0 and recent[i-1][1] != 0:
                if (recent[i][1] > 0) != (recent[i-1][1] > 0):
                    direction_changes += 1

        avg_speed = sum(abs(m[1]) for m in recent) / len(recent)

        if direction_changes >= 6 and avg_speed > 50:
            return "very_fast_shake"
        elif direction_changes >= 4 and avg_speed > 40:
            return "fast_shake"
        elif direction_changes >= 3 and avg_speed > 25:
            return "medium_shake"

        return None

    def _detect_direction(self, dx: int, dy: int) -> Optional[str]:
        """Detect drag direction from a single move event."""
        if abs(dx) > abs(dy):
            if dx < -20:
                return "left"
            elif dx > 20:
                return "right"
        else:
            if dy < -20:
                return "up"
            elif dy > 20:
                return "down"
        return None

    def _trigger_reaction(self, reaction_type: str) -> None:
        """Trigger dramatic avatar reaction with split delivery (burst + followup)."""
        if self._shake_cooldown:
            return

        # Set cooldown (2.5 seconds)
        self._shake_cooldown = True
        QTimer.singleShot(2500, self._reset_cooldown)

        # Track intensity for settle
        if "fast" in reaction_type or "shake" in reaction_type:
            self._last_shake_intensity = "fast"
        else:
            self._last_shake_intensity = "slow"

        # Get dramatic lines from reaction pool
        from assistant.skills.reaction_lines import get_reaction_lines
        burst_line, followup_line = get_reaction_lines(reaction_type)

        # Set emotion
        emotion_map = {
            "left": "surprised",
            "right": "happy",
            "up": "surprised",
            "down": "sad",
            "medium_shake": "surprised",
            "fast_shake": "surprised",
            "very_fast_shake": "angry",
            "settle_slow": "relaxed",
            "settle_fast": "relaxed",
        }
        emotion = emotion_map.get(reaction_type, "neutral")
        intensity = 0.9 if "fast" in reaction_type else 0.7
        self.set_emotion(emotion, intensity)

        # Trigger JS animation
        self._run_js(f"if(window.setReactionAnimation) window.setReactionAnimation('{reaction_type}')")

        # Show chat bubble
        self.show_chat_bubble(burst_line, 3.0)

        # Speak burst immediately
        if self._speak_reaction_fn and burst_line:
            try:
                self._speak_reaction_fn(burst_line)
            except Exception:
                pass

        # Speak followup after delay (split delivery for drama)
        if followup_line:
            def _speak_followup():
                self.show_chat_bubble(followup_line, 3.0)
                if self._speak_reaction_fn:
                    try:
                        self._speak_reaction_fn(followup_line)
                    except Exception:
                        pass
            QTimer.singleShot(800, _speak_followup)

    def _reset_cooldown(self) -> None:
        """Reset shake cooldown."""
        self._shake_cooldown = False

    def _on_settle(self) -> None:
        """Called 1.5s after window stops moving."""
        if self._was_moved:
            self._was_moved = False
            if random.random() < 0.35:
                settle_type = "settle_fast" if self._last_shake_intensity == "fast" else "settle_slow"
                self._trigger_reaction(settle_type)

    def _on_idle_bored(self) -> None:
        """Called after 10 minutes of no interaction."""
        from assistant.skills.reaction_lines import get_reaction_lines
        burst, _ = get_reaction_lines("idle_bored")
        self.show_chat_bubble(burst, 5.0)
        self.set_emotion("sad", 0.4)
        if self._speak_reaction_fn:
            try:
                self._speak_reaction_fn(burst)
            except Exception:
                pass
        # Restart idle timer for next bored reaction
        self._idle_timer.start(600000)

    # ========== MOUSE EVENTS (click = mic, drag from top bar) ==========

    def mousePressEvent(self, event):
        """Click anywhere on window = start listening (like mic button)."""
        if event.button() == Qt.LeftButton:
            # Top 30px = drag
            if event.y() <= 30:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                self._dragging = True
            else:
                # Click on avatar area = mic click
                if self._mic_enabled and self.on_mic_click:
                    self.on_mic_click()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def resizeEvent(self, event):
        """Keep web view filling window on resize."""
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if hasattr(self, 'web'):
            self.web.setGeometry(0, 0, w, h)
        if hasattr(self, 'sizegrip'):
            self.sizegrip.setGeometry(w - 20, h - 20, 20, 20)
            self.sizegrip.raise_()


def get_audio_volume(audio_chunk: np.ndarray) -> float:
    """Convert audio chunk (int16 or float32) to 0.0-1.0 for lip sync."""
    if audio_chunk is None or len(audio_chunk) == 0:
        return 0.0
    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
    return min(1.0, rms / 8000.0) ** 0.7


# --- STANDALONE (for testing) ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = AvatarWindow()
    win.show()
    sys.exit(app.exec_())
