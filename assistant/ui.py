"""
Clean Premium UI for Shweta AI Desktop Assistant.
Meta AI inspired — clean gradient ring, no artifacts, no dark shadows.
"""

import math
import tkinter as tk
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from config import ASSISTANT_NAME

# ---------- DIMENSIONS ----------
WIN_WIDTH = 380
WIN_HEIGHT = 600
RING_RENDER_SIZE = 200

# ---------- COLORS ----------
BG_COLOR = "#0f1123"
CARD_COLOR = "#1a1f3a"
PILL_COLOR = "#252b4a"
TEXT_WHITE = "#ffffff"
TEXT_GRAY = "#7a82a6"
TEXT_MUTED = "#4a5070"

# Ring colors per state
RING_COLORS = {
    "idle": [(70, 100, 255), (150, 80, 255), (60, 200, 255)],
    "listening": [(0, 220, 130), (0, 180, 255), (100, 255, 200)],
    "thinking": [(255, 140, 50), (255, 80, 150), (255, 200, 80)],
    "speaking": [(200, 60, 255), (255, 60, 180), (100, 140, 255)],
}


class AssistantUI:
    """Clean floating UI with smooth gradient ring."""

    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING = "thinking"
    STATE_SPEAKING = "speaking"

    def __init__(self, on_mic_click: Optional[Callable] = None) -> None:
        self.on_mic_click = on_mic_click
        self.state = self.STATE_IDLE
        self._frame = 0
        self._rotation = 0.0

        # Window
        self.root = tk.Tk()
        self.root.title(ASSISTANT_NAME)
        self.root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.configure(bg=BG_COLOR)

        # Position bottom-right
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - WIN_WIDTH - 20}+{sh - WIN_HEIGHT - 60}")

        self._drag_x = 0
        self._drag_y = 0
        self._refs = {}

        self._build_ui()
        self._animate()

    def _build_ui(self) -> None:
        """Build all UI elements."""
        # Main container
        main = tk.Frame(self.root, bg=BG_COLOR)
        main.pack(fill=tk.BOTH, expand=True)
        main.bind("<Button-1>", self._start_drag)
        main.bind("<B1-Motion>", self._on_drag)

        # --- Top section ---
        top = tk.Frame(main, bg=BG_COLOR)
        top.pack(fill=tk.X, pady=(12, 0))
        top.bind("<Button-1>", self._start_drag)
        top.bind("<B1-Motion>", self._on_drag)

        # Close X
        close_btn = tk.Label(top, text="✕", bg=BG_COLOR, fg=TEXT_MUTED,
                             font=("Segoe UI", 12), cursor="hand2")
        close_btn.pack(side=tk.LEFT, padx=16)
        close_btn.bind("<Button-1>", lambda e: self._close())

        # Title center
        title_frame = tk.Frame(top, bg=BG_COLOR)
        title_frame.pack(side=tk.LEFT, expand=True)
        tk.Label(title_frame, text=f"{ASSISTANT_NAME} ✦", bg=BG_COLOR, fg=TEXT_WHITE,
                 font=("Segoe UI Semibold", 13)).pack()
        tk.Label(title_frame, text="with Groq AI", bg=BG_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack()

        # Info
        tk.Label(top, text="ⓘ", bg=BG_COLOR, fg="#4a6aff",
                 font=("Segoe UI", 12)).pack(side=tk.RIGHT, padx=16)

        # --- Ring canvas (transparent background matching window) ---
        # Ring + Mic button inside it
        ring_frame = tk.Frame(main, bg=BG_COLOR)
        ring_frame.pack(pady=(20, 10))

        self.ring_label = tk.Label(ring_frame, bg=BG_COLOR, borderwidth=0)
        self.ring_label.pack()

        # Mic button overlaid in center of ring (invisible background)
        self.mic_btn = tk.Label(ring_frame, text="🎤", bg=BG_COLOR, fg=TEXT_WHITE,
                                font=("Segoe UI Emoji", 20), cursor="hand2",
                                borderwidth=0, highlightthickness=0, padx=0, pady=0)
        self.mic_btn.place(relx=0.5, rely=0.5, anchor="center")
        self.mic_btn.bind("<Button-1>", lambda e: self._mic_clicked())
        self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg="#aabbff"))
        self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(fg=TEXT_WHITE))

        # --- Main text ---
        self.main_text = tk.Label(main, text=f"Ask {ASSISTANT_NAME} anything",
                                  bg=BG_COLOR, fg=TEXT_WHITE,
                                  font=("Segoe UI Semibold", 14),
                                  wraplength=WIN_WIDTH - 40)
        self.main_text.pack(pady=(5, 2))

        # --- Status ---
        self.status_text = tk.Label(main, text="", bg=BG_COLOR, fg=TEXT_GRAY,
                                    font=("Segoe UI", 9))
        self.status_text.pack(pady=(0, 12))

        # --- Suggestion pills (2 rows only) ---
        pills_data = [
            ["🎵 Play music", "🌤 Weather", "📸 Screenshot"],
            ["📝 Notepad", "🌐 Google", "🔊 Volume"],
        ]
        for row in pills_data:
            row_frame = tk.Frame(main, bg=BG_COLOR)
            row_frame.pack(pady=4)
            for text in row:
                pill = tk.Label(row_frame, text=text, bg=PILL_COLOR, fg="#b0b8d8",
                                font=("Segoe UI", 9), padx=12, pady=5, cursor="hand2")
                pill.pack(side=tk.LEFT, padx=3)
                pill.bind("<Enter>", lambda e, p=pill: p.config(bg="#333a5c"))
                pill.bind("<Leave>", lambda e, p=pill: p.config(bg=PILL_COLOR))

        # --- Response text (simple, below pills) ---
        self.response_label = tk.Label(main, text="", bg=BG_COLOR, fg=TEXT_GRAY,
                                       font=("Segoe UI", 10), wraplength=WIN_WIDTH - 40)
        self.response_label.pack(pady=(15, 10))

    # ---------- RING RENDERING ----------

    def _render_ring(self) -> ImageTk.PhotoImage:
        """Render a clean anti-aliased gradient ring with no artifacts."""
        size = RING_RENDER_SIZE
        ss = 3  # Supersampling for smooth edges
        big = size * ss

        # Create transparent image
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

        cx, cy = big // 2, big // 2
        outer_r = int(big * 0.44)
        thickness = int(big * 0.09)
        inner_r = outer_r - thickness

        colors = RING_COLORS[self.state]
        rotation = self._rotation

        # Draw ring using numpy for smooth gradient
        arr = np.zeros((big, big, 4), dtype=np.uint8)
        y_grid, x_grid = np.mgrid[0:big, 0:big]

        # Distance from center
        dx = x_grid - cx
        dy = y_grid - cy
        dist = np.sqrt(dx ** 2 + dy ** 2)

        # Ring mask (smooth edges with anti-aliasing)
        outer_mask = np.clip(outer_r - dist + 1, 0, 1)
        inner_mask = np.clip(dist - inner_r + 1, 0, 1)
        ring_mask = outer_mask * inner_mask

        # Angle for gradient color
        angle = (np.arctan2(dy, dx) + np.pi) / (2 * np.pi)  # 0 to 1
        # Apply rotation
        angle = (angle + rotation / 360.0) % 1.0

        # 3-color gradient around the ring
        c1, c2, c3 = colors
        # Segment 1: 0-0.33
        # Segment 2: 0.33-0.66
        # Segment 3: 0.66-1.0
        r = np.zeros_like(angle)
        g = np.zeros_like(angle)
        b = np.zeros_like(angle)

        # Segment 1
        mask1 = angle < 0.333
        t1 = angle / 0.333
        r = np.where(mask1, c1[0] * (1 - t1) + c2[0] * t1, r)
        g = np.where(mask1, c1[1] * (1 - t1) + c2[1] * t1, g)
        b = np.where(mask1, c1[2] * (1 - t1) + c2[2] * t1, b)

        # Segment 2
        mask2 = (angle >= 0.333) & (angle < 0.666)
        t2 = (angle - 0.333) / 0.333
        r = np.where(mask2, c2[0] * (1 - t2) + c3[0] * t2, r)
        g = np.where(mask2, c2[1] * (1 - t2) + c3[1] * t2, g)
        b = np.where(mask2, c2[2] * (1 - t2) + c3[2] * t2, b)

        # Segment 3
        mask3 = angle >= 0.666
        t3 = (angle - 0.666) / 0.334
        r = np.where(mask3, c3[0] * (1 - t3) + c1[0] * t3, r)
        g = np.where(mask3, c3[1] * (1 - t3) + c1[1] * t3, g)
        b = np.where(mask3, c3[2] * (1 - t3) + c1[2] * t3, b)

        # Apply ring mask
        arr[..., 0] = (r * ring_mask).astype(np.uint8)
        arr[..., 1] = (g * ring_mask).astype(np.uint8)
        arr[..., 2] = (b * ring_mask).astype(np.uint8)
        arr[..., 3] = (ring_mask * 255).astype(np.uint8)

        img = Image.fromarray(arr, "RGBA")

        # Add soft outer glow
        glow = img.copy().filter(ImageFilter.GaussianBlur(radius=8))
        glow_arr = np.array(glow)
        glow_arr[..., 3] = (glow_arr[..., 3] * 0.4).astype(np.uint8)
        glow = Image.fromarray(glow_arr)

        final = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        final = Image.alpha_composite(final, glow)
        final = Image.alpha_composite(final, img)

        # Downscale with LANCZOS
        final = final.resize((size, size), Image.LANCZOS)

        # Composite onto background color
        bg = Image.new("RGBA", (size, size), (15, 17, 35, 255))
        bg = Image.alpha_composite(bg, final)

        return ImageTk.PhotoImage(bg.convert("RGB"))

    # ---------- ANIMATION ----------

    def _animate(self) -> None:
        self._frame += 1

        # Rotation speed per state
        speeds = {"idle": 0.4, "listening": 1.0, "thinking": 2.5, "speaking": 1.2}
        self._rotation = (self._rotation + speeds.get(self.state, 0.4)) % 360

        try:
            photo = self._render_ring()
            self._refs["ring"] = photo
            self.ring_label.config(image=photo)
        except Exception:
            pass

        self.root.after(50, self._animate)  # ~20fps

    # ---------- WINDOW CONTROLS ----------

    def _start_drag(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event) -> None:
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _close(self) -> None:
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _mic_clicked(self) -> None:
        if self.on_mic_click:
            self.on_mic_click()

    # ---------- PUBLIC API ----------

    def set_state(self, state: str) -> None:
        self.state = state
        status = {
            self.STATE_IDLE: "",
            self.STATE_LISTENING: "🎙 Listening...",
            self.STATE_THINKING: "💭 Thinking...",
            self.STATE_SPEAKING: "🔊 Speaking...",
        }
        self.status_text.config(text=status.get(state, ""))
        if state == self.STATE_IDLE:
            self.main_text.config(text=f"Ask {ASSISTANT_NAME} anything")
        elif state == self.STATE_LISTENING:
            self.main_text.config(text="I'm listening...")
        elif state == self.STATE_THINKING:
            self.main_text.config(text="Thinking...")

    def set_text(self, text: str) -> None:
        display = text[:100] + "..." if len(text) > 100 else text
        self.main_text.config(text=display)
        self.response_label.config(text=display)

    def set_mic_enabled(self, enabled: bool) -> None:
        pass

    def schedule(self, func: Callable, *args) -> None:
        self.root.after(0, func, *args)

    def run(self) -> None:
        self.root.mainloop()
