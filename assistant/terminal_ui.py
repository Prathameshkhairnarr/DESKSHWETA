"""
Beautiful Terminal Logging for Shweta AI.

Proper colors, spacing, feature/skill names prominently displayed.
Human-readable at a glance — no khichidi.

Color scheme:
  GREEN   = Success / Running / OK
  RED     = Error / Failed / Critical
  YELLOW  = Warning / Attention
  CYAN    = Feature/Skill name
  MAGENTA = Speech/TTS output
  BLUE    = System info / Debug
  WHITE   = Normal text
  GRAY    = Timestamp / Less important
"""

import logging
import sys
import os

# Enable ANSI color codes on Windows 10+ terminal & force UTF-8 encoding
if sys.platform == "win32":
    os.system("")  # Enables VT100 escape sequences in Windows cmd/powershell
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ============================================================
# ANSI Color Codes
# ============================================================

class C:
    """ANSI color codes for terminal output."""
    RESET    = "\033[0m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"

    # Foreground
    BLACK    = "\033[30m"
    RED      = "\033[91m"       # Bright red
    GREEN    = "\033[92m"       # Bright green
    YELLOW   = "\033[93m"       # Bright yellow
    BLUE     = "\033[94m"       # Bright blue
    MAGENTA  = "\033[95m"       # Bright magenta
    CYAN     = "\033[96m"       # Bright cyan
    WHITE    = "\033[97m"       # Bright white
    GRAY     = "\033[90m"       # Gray/dim

    # Background (for status badges)
    BG_GREEN  = "\033[42m"
    BG_RED    = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_BLUE   = "\033[44m"
    BG_CYAN   = "\033[46m"


# ============================================================
# Module → Feature Name Mapping
# ============================================================

MODULE_DISPLAY_NAMES = {
    "assistant.agent_system":        "Agent Hub",
    "assistant.voice_output":       "Voice Output",
    "assistant.voice_input":        "Voice Input",
    "assistant.brain_tool":         "AI Brain",
    "assistant.ai_brain":           "AI Brain",
    "assistant.brain_claude":       "Claude AI",
    "assistant.desktop_control":    "Desktop Control",
    "assistant.activation":         "Activation",
    "assistant.audio_hub":          "Audio Hub",
    "assistant.skills.apps":        "Apps",
    "assistant.skills.browser":     "Browser",
    "assistant.skills.browser_agent": "Browser Agent",
    "assistant.skills.browser_auto": "Browser Auto",
    "assistant.skills.multi_browser": "Multi Browser",
    "assistant.skills.files":       "Files",
    "assistant.skills.games":       "Games",
    "assistant.skills.gesture":     "Gesture",
    "assistant.skills.email_skill": "Email",
    "assistant.skills.briefing":    "Briefing",
    "assistant.skills.daily_briefing": "Daily Briefing",
    "assistant.skills.market":      "Market",
    "assistant.skills.wakeword":    "Wake Word",
    "assistant.skills.multilang":   "Language",
    "assistant.skills.learning":    "Learning",
    "assistant.channels.telegram_bot": "Telegram",
    "__main__":                     "Shweta",
}


def _get_feature_name(logger_name: str) -> str:
    """Convert logger name (module path) to a clean feature display name."""
    if logger_name in MODULE_DISPLAY_NAMES:
        return MODULE_DISPLAY_NAMES[logger_name]
    # Fallback: take the last part of the module name and title-case it
    parts = logger_name.split(".")
    return parts[-1].replace("_", " ").title()


# ============================================================
# Level → Icon/Color Mapping
# ============================================================

LEVEL_STYLES = {
    logging.DEBUG:    (C.GRAY,    "   "),
    logging.INFO:     (C.GREEN,   " ✓ "),
    logging.WARNING:  (C.YELLOW,  " ⚠ "),
    logging.ERROR:    (C.RED,     " ✗ "),
    logging.CRITICAL: (C.RED + C.BOLD, " ✗✗"),
}


# ============================================================
# Custom Formatter
# ============================================================

class ShwetaTerminalFormatter(logging.Formatter):
    """
    Beautiful, human-readable terminal log formatter.

    Format:
    HH:MM:SS  ✓  [Feature Name]  message text here
    HH:MM:SS  ✗  [Feature Name]  ERROR: something went wrong
    HH:MM:SS  ⚠  [Feature Name]  warning about something
    """

    def format(self, record: logging.LogRecord) -> str:
        # Time (gray, compact)
        time_str = self.formatTime(record, "%H:%M:%S")

        # Level icon + color
        color, icon = LEVEL_STYLES.get(record.levelno, (C.WHITE, "   "))

        # Feature/skill name (cyan, prominent)
        feature = _get_feature_name(record.name)

        # Message
        msg = record.getMessage()

        # Special formatting for specific message patterns
        msg = self._style_message(msg, record.levelno)

        # Build the final line
        line = (
            f"{C.GRAY}{time_str}{C.RESET}"
            f"  {color}{icon}{C.RESET}"
            f"  {C.CYAN}{C.BOLD}[{feature}]{C.RESET}"
            f"  {color}{msg}{C.RESET}"
        )

        # Add exception info if present
        if record.exc_info and record.exc_info[0]:
            exc_text = self.formatException(record.exc_info)
            line += f"\n{C.RED}{C.DIM}{exc_text}{C.RESET}"

        return line

    def _style_message(self, msg: str, level: int) -> str:
        """Apply extra styling to specific message patterns."""
        # Highlight TTS speech text in magenta
        if "spoke:" in msg or "Polly" in msg:
            msg = msg.replace("✅", f"{C.GREEN}✓{C.RESET}")

        # Highlight file paths
        if "cache/" in msg or ".mp3" in msg or ".wav" in msg:
            pass  # Keep as-is, color from level is enough

        return msg


# ============================================================
# Setup Function — call this ONCE in main.py
# ============================================================

def setup_terminal_logging(level: str = "INFO") -> None:
    """
    Configure logging with beautiful colored terminal output.
    Call this INSTEAD of logging.basicConfig() in main.py.

    Args:
        level: Log level string ("DEBUG", "INFO", "WARNING", "ERROR")
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root logger
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove any existing handlers
    root.handlers.clear()

    # Terminal handler (colored, beautiful)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(ShwetaTerminalFormatter())

    # File handler (plain text, full detail for debugging)
    from config import LOGS_DIR
    file_handler = logging.FileHandler(LOGS_DIR / "errors.log", encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root.addHandler(console)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in [
        "urllib3", "botocore", "boto3", "requests", "PIL", "numba",
        "httpx", "httpcore", "telegram", "telegram.ext",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def print_banner() -> None:
    """Print a beautiful startup banner."""
    banner = f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════╗
║                                                      ║
║          {C.WHITE}S H W E T A   A I   A S S I S T A N T{C.CYAN}       ║
║                                                      ║
╚══════════════════════════════════════════════════════╝{C.RESET}

{C.GREEN}  Engine  :{C.RESET} Murf Falcon 2.1 (primary) + Amazon Polly (fallback)
{C.GREEN}  Voice   :{C.RESET} Pooja — Conversational Falcon 2.1 (hi-LATN Hinglish)
{C.GREEN}  Status  :{C.RESET} Starting up...
"""
    print(banner)


def print_status(feature: str, status: str, detail: str = "") -> None:
    """
    Print a prominent status line for feature initialization.

    Args:
        feature: Feature name (e.g. "Voice Output", "Wake Word")
        status: "OK", "FAIL", "SKIP", "LOADING"
        detail: Optional detail text
    """
    status_styles = {
        "OK":      (C.BG_GREEN + C.BLACK + C.BOLD, " OK "),
        "FAIL":    (C.BG_RED + C.WHITE + C.BOLD,   "FAIL"),
        "SKIP":    (C.BG_YELLOW + C.BLACK,          "SKIP"),
        "LOADING": (C.BG_BLUE + C.WHITE,            " .. "),
    }
    style, label = status_styles.get(status.upper(), (C.WHITE, status))
    detail_str = f"  {C.GRAY}{detail}{C.RESET}" if detail else ""
    print(f"  {style} {label} {C.RESET}  {C.CYAN}{feature:<20}{C.RESET}{detail_str}")
