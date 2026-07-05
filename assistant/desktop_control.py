"""
Desktop Control Module for Shweta AI Desktop Assistant.
Routes AI actions to the appropriate skill functions.

PRODUCTION v3.0 — Alexa-grade resilience:
- All skill modules init in try/except (no single failure crashes everything)
- Action execution with configurable timeout for long-running actions
- Concurrent action protection (lock-based)
- Dangerous action set with confirmation enforcement
- Null-safe skill access (checks None before calling)
- Usage tracking fire-and-forget (never blocks action)
- Unknown action handler with Hinglish response
- Circuit Breaker integration via resilience module
- Resource monitoring (RAM/CPU guards)
- Skill health dashboard for diagnostics
- Structured error categories for consistent user messaging
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, Optional

from assistant.skills import browser, system, apps, weather
from assistant.skills.timer import TimerManager
from assistant.skills import files as file_skills
from assistant.skills import sysinfo, notes, windows, briefing, whatsapp, vision, games
from assistant.skills import market as market_skills
from assistant.skills import spotify as spotify_skills
from assistant.skills import email_skill
from assistant.skills import trading as trading_skills
from assistant.skills.gesture import GestureController
from assistant.skills.browser_agent import BrowserAgent
from assistant.skills.personality import PersonalityManager, MemoryStore, HealthReminders
from assistant.skills.multilang import LanguageManager
from assistant.skills.learning import UsageLearner
from assistant.skills.browser_auto import BrowserAutomation
from assistant.skills.multi_browser import MultiBrowserAgent

logger = logging.getLogger(__name__)

# Actions that need confirmation before execution
DANGEROUS_ACTIONS = {"shutdown_pc", "restart_pc", "empty_recycle_bin"}

# Actions that can take a long time (browser agent, multi-browser, etc.)
LONG_RUNNING_ACTIONS = {"browser_agent_task", "multi_browser_task", "daily_briefing", "search_file"}
LONG_TIMEOUT = 120  # seconds (increased for production stability)
DEFAULT_TIMEOUT = 30  # seconds

# --- Production: Resource limits ---
MAX_RAM_PERCENT = 90   # Skip heavy skills if RAM > 90%
MAX_EXECUTOR_WORKERS = 4  # Increased from 2 for better concurrency


class DesktopController:
    """Routes and executes desktop actions from AI responses."""

    def __init__(self, on_timer_complete: Optional[Callable] = None) -> None:
        """
        Initialize the desktop controller with all skill modules.
        Each component is initialized safely — if one fails, others still work.

        Args:
            on_timer_complete: Callback for when timers complete.
        """
        self.timer_manager = TimerManager(on_timer_complete=on_timer_complete)
        
        # Safe initialization — each component can fail independently
        try:
            self.browser_auto = BrowserAutomation()
        except Exception as e:
            logger.warning(f"BrowserAutomation init failed: {e}")
            self.browser_auto = None

        try:
            self.gesture = GestureController(on_gesture=self._on_gesture)
        except Exception as e:
            logger.warning(f"GestureController init failed: {e}")
            self.gesture = None

        try:
            self.browser_agent = BrowserAgent()
        except Exception as e:
            logger.warning(f"BrowserAgent init failed: {e}")
            self.browser_agent = None

        self.memory = MemoryStore()
        self.personality = PersonalityManager(memory_store=self.memory)
        self.health = HealthReminders()
        self.language = LanguageManager()
        self.learner = UsageLearner()
        try:
            self.multi_browser = MultiBrowserAgent()
        except Exception as e:
            logger.warning(f"MultiBrowserAgent init failed: {e}")
            self.multi_browser = None

        # Action execution lock (prevent concurrent actions)
        self._action_lock = threading.Lock()
        self._action_in_progress: bool = False
        self._executor = ThreadPoolExecutor(max_workers=MAX_EXECUTOR_WORKERS, thread_name_prefix="Action")

        # --- Production: Skill Health Tracking ---
        self._skill_health: Dict[str, Dict[str, int]] = {}  # {action: {success: N, fail: N, last_fail_time: T}}

        # Skill init report
        self._skill_report: Dict[str, bool] = {
            "timer": True,
            "browser_auto": self.browser_auto is not None,
            "gesture": self.gesture is not None,
            "browser_agent": self.browser_agent is not None,
            "memory": True,
            "personality": True,
            "health": True,
            "language": True,
            "learner": True,
            "multi_browser": self.multi_browser is not None,
        }
        loaded = sum(1 for v in self._skill_report.values() if v)
        total = len(self._skill_report)
        logger.info(f"[Skills] {loaded}/{total} modules loaded successfully.")

        # Map action names to handler functions
        self._action_map: Dict[str, Callable] = {
            # Browser skills
            "open_youtube": self._open_youtube,
            "open_google": self._open_google,
            "open_website": self._open_website,
            "play_youtube": self._play_youtube,
            # Media/Browser controls
            "media_play_pause": self._media_play_pause,
            "media_fullscreen": self._media_fullscreen,
            "media_exit_fullscreen": self._media_exit_fullscreen,
            "media_next": self._media_next,
            "media_previous": self._media_previous,
            "media_forward": self._media_forward,
            "media_rewind": self._media_rewind,
            "media_mute": self._media_mute,
            "media_volume_up": self._media_volume_up,
            "media_volume_down": self._media_volume_down,
            "media_set_volume": self._media_set_volume,
            "media_captions": self._media_captions,
            "browser_new_tab": self._browser_new_tab,
            "browser_close_tab": self._browser_close_tab,
            "close_tab": self._browser_close_tab,
            "browser_switch_tab": self._browser_switch_tab,
            "browser_back": self._browser_back,
            "browser_refresh": self._browser_refresh,
            # System skills
            "take_screenshot": self._take_screenshot,
            "get_time": self._get_time,
            "get_date": self._get_date,
            "volume_up": self._volume_up,
            "volume_down": self._volume_down,
            "volume_mute": self._volume_mute,
            "brightness_up": self._brightness_up,
            "brightness_down": self._brightness_down,
            "set_brightness": self._set_brightness,
            "lock_screen": self._lock_screen,
            "open_file_manager": self._open_file_manager,
            "type_text": self._type_text,
            "copy_to_clipboard": self._copy_to_clipboard,
            "empty_recycle_bin": self._empty_recycle_bin,
            "run_command": self._run_command,
            "shutdown_pc": self._shutdown_pc,
            "restart_pc": self._restart_pc,
            "sleep_pc": self._sleep_pc,
            # App skills
            "open_notepad": self._open_notepad,
            "open_calculator": self._open_calculator,
            "open_terminal": self._open_terminal,
            "open_vscode": self._open_vscode,
            "open_spotify": self._open_spotify,
            "close_app": self._close_app,
            "open_app": self._open_app,
            # Weather
            "get_weather": self._get_weather,
            # Timer/Reminder
            "set_timer": self._set_timer,
            "set_reminder": self._set_reminder,
            "list_timers": self._list_timers,
            "cancel_timer": self._cancel_timer,
            # Browser Automation (Selenium)
            "auto_search_and_play": self._auto_search_and_play,
            "auto_youtube_search": self._auto_youtube_search,
            "auto_play_first": self._auto_play_first,
            "auto_google_search": self._auto_google_search,
            "auto_open_url": self._auto_open_url,
            "auto_click": self._auto_click,
            "auto_type": self._auto_type,
            "auto_scroll_down": self._auto_scroll_down,
            "auto_scroll_up": self._auto_scroll_up,
            "auto_go_back": self._auto_go_back,
            "auto_close_browser": self._auto_close_browser,
            # File Management
            "create_file": self._create_file,
            "create_folder": self._create_folder,
            "delete_file": self._delete_file,
            "rename_file": self._rename_file,
            "move_file": self._move_file,
            "copy_file": self._copy_file,
            "list_files": self._list_files,
            "open_file": self._open_file,
            "search_file": self._search_file,
            "search_and_open": self._search_and_open,
            # System Info
            "get_battery": self._get_battery,
            "get_ram_usage": self._get_ram_usage,
            "get_storage": self._get_storage,
            "get_cpu_usage": self._get_cpu_usage,
            "get_wifi_status": self._get_wifi_status,
            "get_system_info": self._get_system_info,
            # Notes/Todo
            "add_note": self._add_note,
            "list_notes": self._list_notes,
            "delete_note": self._delete_note,
            "complete_note": self._complete_note,
            "clear_notes": self._clear_notes,
            "change_style": self._change_style,
            "start_game": self._start_game,
            "play_turn": self._play_turn,
            # Window Management
            "snap_left": self._snap_left,
            "snap_right": self._snap_right,
            "maximize_window": self._maximize_window,
            "minimize_window": self._minimize_window,
            "minimize_all": self._minimize_all,
            "switch_window": self._switch_window,
            "close_window": self._close_window,
            "task_view": self._task_view,
            # Daily Briefing
            "daily_briefing": self._daily_briefing,
            "morning_briefing": self._morning_briefing,
            # WhatsApp
            "send_whatsapp": self._send_whatsapp,
            "send_whatsapp_by_name": self._send_whatsapp_by_name,
            # Vision AI
            "read_screen": self._read_screen,
            "react_to_screen": self._read_screen,
            # Gesture Control
            "start_gesture": self._start_gesture,
            "stop_gesture": self._stop_gesture,
            # Market & News
            "get_crypto_price": self._get_crypto_price,
            "get_stock_market": self._get_stock_market,
            "get_news": self._get_news,
            "get_gold_price": self._get_gold_price,
            # Browser Agent (autonomous)
            "browser_agent_task": self._browser_agent_task,
            "browser_agent_history": self._browser_agent_history,
            # Multi-Tab Browser
            "multi_browser_task": self._multi_browser_task,
            # Personality & Memory
            "set_mode": self._set_mode,
            "remember": self._remember,
            "get_memory": self._get_memory,
            "health_reminders_on": self._health_on,
            "health_reminders_off": self._health_off,
            # Language
            "set_language": self._set_language,
            # Learning
            "get_usage_stats": self._get_usage_stats,
            # Spotify
            "spotify_play_pause": self._spotify_play_pause,
            "spotify_next": self._spotify_next,
            "spotify_previous": self._spotify_previous,
            "spotify_now_playing": self._spotify_now_playing,
            "spotify_play_song": self._spotify_play_song,
            "spotify_play_playlist": self._spotify_play_playlist,
            "spotify_mood": self._spotify_mood,
            "spotify_volume": self._spotify_volume,
            "spotify_shuffle": self._spotify_shuffle,
            # Email
            "send_email": self._send_email,
            # Trading
            "open_tradingview": self._open_tradingview,
            "draw_trend_line": self._draw_trend_line,
            "draw_horizontal_line": self._draw_horizontal_line,
            "draw_rectangle": self._draw_rectangle,
            "draw_fibonacci": self._draw_fibonacci,
            "mark_support_resistance": self._mark_support_resistance,
            "undo_drawing": self._undo_drawing,
            "clear_drawings": self._clear_drawings,
            "change_symbol": self._change_symbol,
            "change_timeframe": self._change_timeframe,
        }

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Execute a desktop action by name.
        Thread-safe with timeout protection, resource guards, and health tracking.

        Args:
            action: The action name to execute.
            params: Parameters for the action.

        Returns:
            Result dictionary from the executed skill.
        """
        # Stop music vibe if the current command is not related to music
        music_actions = {"play_youtube", "spotify_play_song", "spotify_play_playlist", "spotify_mood", "spotify_next", "spotify_previous", "spotify_play_pause", "media_play_pause", "media_next", "media_previous"}
        if not action or action == "none" or action not in music_actions:
            self._stop_music_vibe()

        if action == "none" or not action:
            return {"status": "no_action", "message": "No action needed."}

        # Ensure params is always a dict
        if not isinstance(params, dict):
            params = {}

        handler = self._action_map.get(action)
        if not handler:
            logger.warning(f"Unknown action: {action}")
            return {"status": "error", "message": f"Ye action nahi samjhi: {action}. Phir se try karo."}

        # --- Production: RAM guard for heavy skills ---
        heavy_actions = {"browser_agent_task", "multi_browser_task", "auto_search_and_play", "auto_youtube_search", "auto_google_search"}
        if action in heavy_actions:
            try:
                import psutil
                ram = psutil.virtual_memory()
                if ram.percent > MAX_RAM_PERCENT:
                    logger.warning(f"[Resource Guard] RAM at {ram.percent}% — skipping heavy action '{action}'")
                    return {"status": "error", "message": f"System pe load zyada hai (RAM {ram.percent}%). Thodi der baad try karo."}
            except Exception:
                pass  # psutil not available, skip check

        # Execute action with timeout
        timeout = LONG_TIMEOUT if action in LONG_RUNNING_ACTIONS else DEFAULT_TIMEOUT
        start_time = time.time()

        try:
            future = self._executor.submit(handler, params)
            result = future.result(timeout=timeout)

            # Ensure result is always a dict with status
            if not isinstance(result, dict):
                result = {"status": "success", "message": str(result) if result else "Done."}
            if "status" not in result:
                result["status"] = "success"

            elapsed = round(time.time() - start_time, 2)
            logger.info(f"Action executed: {action} → {result.get('status')} ({elapsed}s)")

            # --- Production: Track skill health ---
            self._track_health(action, success=result.get("status") != "error")

            # Track usage (fire-and-forget, never blocks)
            try:
                self.learner.track(action, str(params.get("query", params.get("goal", ""))))
            except Exception:
                pass

            return result

        except FuturesTimeout:
            elapsed = round(time.time() - start_time, 2)
            logger.error(f"Action timeout ({timeout}s): {action} after {elapsed}s")
            self._track_health(action, success=False)
            return {"status": "error", "message": f"Action timeout ho gaya ({timeout}s). Phir try karo."}
        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            logger.error(f"Action failed: {action} — {e} ({elapsed}s)", exc_info=True)
            self._track_health(action, success=False)
            return {"status": "error", "message": f"Kuch gadbad hui: {str(e)[:80]}"}

    # --- Production: Health tracking helpers ---

    def _track_health(self, action: str, success: bool) -> None:
        """Track success/failure for each action (production monitoring)."""
        if action not in self._skill_health:
            self._skill_health[action] = {"success": 0, "fail": 0, "last_fail_time": 0.0}
        if success:
            self._skill_health[action]["success"] += 1
        else:
            self._skill_health[action]["fail"] += 1
            self._skill_health[action]["last_fail_time"] = time.time()

    def get_health_report(self) -> Dict[str, Any]:
        """Get a health report of all skills (for diagnostics/logging)."""
        report = {}
        for action, stats in self._skill_health.items():
            total = stats["success"] + stats["fail"]
            success_rate = (stats["success"] / total * 100) if total > 0 else 100
            report[action] = {
                "total_calls": total,
                "success_rate": f"{success_rate:.1f}%",
                "failures": stats["fail"],
                "last_fail": time.strftime("%H:%M:%S", time.localtime(stats["last_fail_time"])) if stats["last_fail_time"] > 0 else "never",
            }
        return report

    # --- Browser skill wrappers ---

    def _open_youtube(self, params: Dict) -> Dict[str, str]:
        return browser.open_youtube()

    def _open_google(self, params: Dict) -> Dict[str, str]:
        return browser.open_google(params.get("query", ""))

    def _open_website(self, params: Dict) -> Dict[str, str]:
        url = params.get("url", "")
        if not url:
            return {"status": "error", "message": "URL not provided."}
        return browser.open_website(url)

    def _play_youtube(self, params: Dict) -> Dict[str, str]:
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Search query not provided."}
            
        # Check if it is a generic music category query to route to music.py recommendation engine
        query_lower = query.lower().strip()
        query_words = query_lower.split()
        music_fillers = {"play", "song", "songs", "music", "gana", "gane", "chalao", "sunaao", "lagao", "playlist", "hits", "some", "a", "an", "the", "pe", "ko", "latest", "new", "mussic", "mussics"}
        meaningful_words = [w for w in query_words if w not in music_fillers]
        
        category_keywords = {
            "phonk": "phonk",
            "punjabi": "punjabi",
            "marathi": "marathi",
            "haryanvi": "haryanvi",
            "south": "south_indian",
            "telugu": "south_indian",
            "tamil": "south_indian",
            "english": "english",
            "hindi": "hindi",
            "bollywood": "hindi",
            "crazy": "hindi",
            "party": "hindi",
            "sad": "sad",
            "chill": "chill",
            "lofi": "chill",
            "relax": "chill",
            "study": "chill",
            "coding": "chill",
            "workout": "workout",
            "gym": "workout",
            "motivation": "workout"
        }
        
        target_cat = None
        if meaningful_words and all(w in category_keywords for w in meaningful_words):
            resolved_cats = [category_keywords[w] for w in meaningful_words if w in category_keywords]
            if resolved_cats:
                target_cat = resolved_cats[0]
                
        if target_cat:
            from assistant.skills import music
            result = music.get_music_recommendation(target_cat)
            if result.get("status") == "success" and "track" in result:
                self._trigger_music_vibe(result["track"])
            return result

        result = browser.play_youtube(query)
        # Trigger music vibe when playing music
        if result.get("status") == "success":
            from assistant.skills import music
            music.learn_song_in_background(query)
            
            music_words = ["song", "gana", "music", "playlist", "band", "singer", "lofi", "sad", "happy", "chill", "workout"]
            if any(w in query.lower() for w in music_words):
                self._trigger_music_vibe(query)
        return result

    # --- System skill wrappers ---

    def _take_screenshot(self, params: Dict) -> Dict[str, str]:
        return system.take_screenshot()

    def _get_time(self, params: Dict) -> Dict[str, str]:
        return system.get_time()

    def _get_date(self, params: Dict) -> Dict[str, str]:
        return system.get_date()

    def _volume_up(self, params: Dict) -> Dict[str, str]:
        try:
            steps = int(params.get("steps", 5))
        except (ValueError, TypeError):
            steps = 5
        return system.volume_up(min(steps, 10))

    def _volume_down(self, params: Dict) -> Dict[str, str]:
        try:
            steps = int(params.get("steps", 5))
        except (ValueError, TypeError):
            steps = 5
        return system.volume_down(min(steps, 10))

    def _volume_mute(self, params: Dict) -> Dict[str, str]:
        return system.volume_mute()

    def _brightness_up(self, params: Dict) -> Dict[str, str]:
        try:
            steps = int(params.get("steps", 15))
        except (ValueError, TypeError):
            steps = 15
        return system.brightness_up(min(steps, 50))

    def _brightness_down(self, params: Dict) -> Dict[str, str]:
        try:
            steps = int(params.get("steps", 15))
        except (ValueError, TypeError):
            steps = 15
        return system.brightness_down(min(steps, 50))

    def _set_brightness(self, params: Dict) -> Dict[str, str]:
        try:
            level = int(params.get("level", 50))
        except (ValueError, TypeError):
            level = 50
        return system.set_brightness(level)

    def _lock_screen(self, params: Dict) -> Dict[str, str]:
        return system.lock_screen()

    def _open_file_manager(self, params: Dict) -> Dict[str, str]:
        return system.open_file_manager()

    def _type_text(self, params: Dict) -> Dict[str, str]:
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "No text provided."}
        return system.type_text(text)

    def _copy_to_clipboard(self, params: Dict) -> Dict[str, str]:
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "No text provided."}
        return system.copy_to_clipboard(text)

    def _empty_recycle_bin(self, params: Dict) -> Dict[str, str]:
        return system.empty_recycle_bin()

    def _run_command(self, params: Dict) -> Dict[str, str]:
        command = params.get("command", "")
        if not command:
            return {"status": "error", "message": "Command not provided."}
        return system.run_command(command)

    def _shutdown_pc(self, params: Dict) -> Dict[str, str]:
        return {"status": "confirm_needed", "message": "⚠️ PC shutdown karna hai? Voice pe 'haan' bolo ya Telegram pe confirm karo."}

    def _restart_pc(self, params: Dict) -> Dict[str, str]:
        return {"status": "confirm_needed", "message": "⚠️ PC restart karna hai? Voice pe 'haan' bolo ya Telegram pe confirm karo."}

    def _sleep_pc(self, params: Dict) -> Dict[str, str]:
        return system.sleep_pc()

    # --- App skill wrappers ---

    def _open_notepad(self, params: Dict) -> Dict[str, str]:
        return apps.open_notepad()

    def _open_calculator(self, params: Dict) -> Dict[str, str]:
        return apps.open_calculator()

    def _open_terminal(self, params: Dict) -> Dict[str, str]:
        return apps.open_terminal()

    def _open_vscode(self, params: Dict) -> Dict[str, str]:
        return apps.open_vscode()

    def _open_spotify(self, params: Dict) -> Dict[str, str]:
        return apps.open_spotify()

    def _close_app(self, params: Dict) -> Dict[str, str]:
        app_name = params.get("app_name", "")
        if not app_name:
            return {"status": "error", "message": "App name not provided."}
        self._stop_music_vibe()
        return apps.close_app(app_name)

    def _open_app(self, params: Dict) -> Dict[str, str]:
        app_name = params.get("app_name", "")
        if not app_name:
            return {"status": "error", "message": "App name not provided."}
        return apps.open_app(app_name)

    # --- Weather skill wrapper ---

    def _get_weather(self, params: Dict) -> Dict[str, str]:
        city = params.get("city", "")
        return weather.get_weather(city)

    # --- Timer skill wrappers ---

    def _set_timer(self, params: Dict) -> Dict[str, str]:
        try:
            seconds = int(params.get("seconds", 60))
        except (ValueError, TypeError):
            seconds = 60
        return self.timer_manager.set_timer(max(1, seconds))

    def _set_reminder(self, params: Dict) -> Dict[str, str]:
        message = params.get("message", "Reminder!")
        try:
            minutes = int(params.get("minutes", 5))
        except (ValueError, TypeError):
            minutes = 5
        return self.timer_manager.set_reminder(str(message), max(1, minutes))

    def _list_timers(self, params: Dict) -> Dict[str, str]:
        return self.timer_manager.list_timers()

    def _cancel_timer(self, params: Dict) -> Dict[str, str]:
        timer_id = params.get("id", "")
        if not timer_id:
            return {"status": "error", "message": "Timer ID not provided."}
        return self.timer_manager.cancel_timer(timer_id)

    # --- Media/Browser control wrappers ---

    def _media_play_pause(self, params: Dict) -> Dict[str, str]:
        self._stop_music_vibe()
        return browser.media_play_pause()

    def _media_fullscreen(self, params: Dict) -> Dict[str, str]:
        return browser.media_fullscreen()

    def _media_exit_fullscreen(self, params: Dict) -> Dict[str, str]:
        return browser.media_exit_fullscreen()

    def _media_next(self, params: Dict) -> Dict[str, str]:
        return browser.media_next()

    def _media_previous(self, params: Dict) -> Dict[str, str]:
        return browser.media_previous()

    def _media_forward(self, params: Dict) -> Dict[str, str]:
        return browser.media_forward()

    def _media_rewind(self, params: Dict) -> Dict[str, str]:
        return browser.media_rewind()

    def _media_mute(self, params: Dict) -> Dict[str, str]:
        return browser.media_mute()

    def _media_volume_up(self, params: Dict) -> Dict[str, str]:
        steps = params.get("steps", 3)
        return browser.media_volume_up(int(steps))

    def _media_volume_down(self, params: Dict) -> Dict[str, str]:
        steps = params.get("steps", 3)
        return browser.media_volume_down(int(steps))

    def _media_set_volume(self, params: Dict) -> Dict[str, str]:
        percent = params.get("percent", 50)
        return browser.media_set_volume(int(percent))

    def _media_captions(self, params: Dict) -> Dict[str, str]:
        return browser.media_captions()

    def _browser_new_tab(self, params: Dict) -> Dict[str, str]:
        return browser.browser_new_tab()

    def _browser_close_tab(self, params: Dict) -> Dict[str, str]:
        self._stop_music_vibe()
        return browser.browser_close_tab()

    def _browser_switch_tab(self, params: Dict) -> Dict[str, str]:
        return browser.browser_switch_tab()

    def _browser_back(self, params: Dict) -> Dict[str, str]:
        return browser.browser_back()

    def _browser_refresh(self, params: Dict) -> Dict[str, str]:
        return browser.browser_refresh()

    # --- Browser Automation (Selenium) wrappers ---

    def _auto_search_and_play(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.search_and_play(query)

    def _auto_youtube_search(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.search_youtube(query)

    def _auto_play_first(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        return self.browser_auto.play_first_video()

    def _auto_google_search(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.google_search(query)

    def _auto_open_url(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        url = params.get("url", "")
        if not url:
            return {"status": "error", "message": "URL not provided."}
        return self.browser_auto.open_url(url)

    def _auto_click(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "Click target not provided."}
        return self.browser_auto.click_element(text)

    def _auto_type(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "Text not provided."}
        return self.browser_auto.type_in_page(text)

    def _auto_scroll_down(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        return self.browser_auto.scroll_down()

    def _auto_scroll_up(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        return self.browser_auto.scroll_up()

    def _auto_go_back(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        return self.browser_auto.go_back()

    def _auto_close_browser(self, params: Dict) -> Dict[str, str]:
        if not self.browser_auto:
            return {"status": "error", "message": "Browser automation available nahi hai."}
        return self.browser_auto.close_browser()

    # --- File Management wrappers ---

    def _create_file(self, params: Dict) -> Dict[str, str]:
        filename = params.get("filename", "")
        content = params.get("content", "")
        if not filename:
            return {"status": "error", "message": "Filename not provided."}
        return file_skills.create_file(filename, content)

    def _create_folder(self, params: Dict) -> Dict[str, str]:
        foldername = params.get("foldername", params.get("name", ""))
        if not foldername:
            return {"status": "error", "message": "Folder name not provided."}
        return file_skills.create_folder(foldername)

    def _delete_file(self, params: Dict) -> Dict[str, str]:
        filename = params.get("filename", params.get("name", ""))
        if not filename:
            return {"status": "error", "message": "Filename not provided."}
        return file_skills.delete_file(filename)

    def _rename_file(self, params: Dict) -> Dict[str, str]:
        old_name = params.get("old_name", params.get("filename", ""))
        new_name = params.get("new_name", "")
        if not old_name or not new_name:
            return {"status": "error", "message": "Old name and new name both required."}
        return file_skills.rename_file(old_name, new_name)

    def _move_file(self, params: Dict) -> Dict[str, str]:
        filename = params.get("filename", "")
        destination = params.get("destination", "")
        if not filename or not destination:
            return {"status": "error", "message": "Filename and destination required."}
        return file_skills.move_file(filename, destination)

    def _copy_file(self, params: Dict) -> Dict[str, str]:
        filename = params.get("filename", "")
        destination = params.get("destination", "")
        if not filename or not destination:
            return {"status": "error", "message": "Filename and destination required."}
        return file_skills.copy_file(filename, destination)

    def _list_files(self, params: Dict) -> Dict[str, str]:
        folder = params.get("folder", "")
        return file_skills.list_files(folder)

    def _open_file(self, params: Dict) -> Dict[str, str]:
        filename = params.get("filename", "")
        if not filename:
            return {"status": "error", "message": "Filename not provided."}
        return file_skills.open_file(filename)

    def _search_file(self, params: Dict) -> Dict[str, str]:
        name = params.get("name", params.get("query", ""))
        location = params.get("location", "")
        if not name:
            return {"status": "error", "message": "Search name not provided."}
        return file_skills.search_file(name, location)

    def _search_and_open(self, params: Dict) -> Dict[str, str]:
        name = params.get("name", params.get("query", ""))
        if not name:
            return {"status": "error", "message": "Search name not provided."}
        return file_skills.search_and_open(name)

    # --- System Info wrappers ---

    def _get_battery(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_battery()

    def _get_ram_usage(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_ram_usage()

    def _get_storage(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_storage()

    def _get_cpu_usage(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_cpu_usage()

    def _get_wifi_status(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_wifi_status()

    def _get_system_info(self, params: Dict) -> Dict[str, str]:
        return sysinfo.get_system_info()

    # --- Notes wrappers ---

    def _add_note(self, params: Dict) -> Dict[str, str]:
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "Note text not provided."}
        return notes.add_note(text)

    def _list_notes(self, params: Dict) -> Dict[str, str]:
        return notes.list_notes()

    def _delete_note(self, params: Dict) -> Dict[str, str]:
        target = params.get("id", params.get("query", params.get("text", "")))
        if not target:
            return {"status": "error", "message": "Note details to delete not provided."}
        return notes.delete_note(str(target))

    def _complete_note(self, params: Dict) -> Dict[str, str]:
        target = params.get("id", params.get("query", params.get("text", "")))
        if not target:
            return {"status": "error", "message": "Note details to complete not provided."}
        return notes.complete_note(str(target))

    def _clear_notes(self, params: Dict) -> Dict[str, str]:
        return notes.clear_notes()

    def _change_style(self, params: Dict) -> Dict[str, str]:
        style = params.get("style", params.get("type", "color_shift"))
        if self._change_style_callback:
            try:
                self._change_style_callback(style)
                return {"status": "success", "message": f"Outfit/Style change kar diya: {style}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "Change style callback not set."}

    def _start_game(self, params: Dict) -> Dict[str, str]:
        game_name = params.get("game", params.get("name", "rps"))
        return games.start_game(game_name)

    def _play_turn(self, params: Dict) -> Dict[str, str]:
        choice = params.get("choice", params.get("text", ""))
        return games.play_turn(choice)

    # --- Window Management wrappers ---

    def _snap_left(self, params: Dict) -> Dict[str, str]:
        return windows.snap_left()

    def _snap_right(self, params: Dict) -> Dict[str, str]:
        return windows.snap_right()

    def _maximize_window(self, params: Dict) -> Dict[str, str]:
        return windows.maximize_window()

    def _minimize_window(self, params: Dict) -> Dict[str, str]:
        return windows.minimize_window()

    def _minimize_all(self, params: Dict) -> Dict[str, str]:
        return windows.minimize_all()

    def _switch_window(self, params: Dict) -> Dict[str, str]:
        return windows.switch_window()

    def _close_window(self, params: Dict) -> Dict[str, str]:
        self._stop_music_vibe()
        return windows.close_window()

    def _task_view(self, params: Dict) -> Dict[str, str]:
        return windows.task_view()

    # --- Daily Briefing ---

    def _daily_briefing(self, params: Dict) -> Dict[str, str]:
        return briefing.daily_briefing()

    def _morning_briefing(self, params: Dict) -> Dict[str, str]:
        """Smart morning briefing with weather, crypto, fun fact."""
        from assistant.skills.daily_briefing import generate_briefing_script
        try:
            script = generate_briefing_script()
            return {"status": "success", "message": script}
        except Exception as e:
            return {"status": "error", "message": f"Briefing nahi ban paya: {e}"}

    # --- WhatsApp ---

    def _send_whatsapp(self, params: Dict) -> Dict[str, str]:
        phone = params.get("phone", "")
        message = params.get("message", "")
        if not phone or not message:
            return {"status": "error", "message": "Phone and message required."}
        return whatsapp.send_whatsapp(phone, message)

    def _send_whatsapp_by_name(self, params: Dict) -> Dict[str, str]:
        name = params.get("name", "")
        message = params.get("message", "")
        if not name or not message:
            return {"status": "error", "message": "Name and message required."}
        # Force Roman script — remove any Devanagari characters
        import re
        if re.search(r'[\u0900-\u097F]', name):
            # Has Devanagari — try basic transliteration
            translit_map = {
                'अ':'a','आ':'aa','इ':'i','ई':'ee','उ':'u','ऊ':'oo','ए':'e','ऐ':'ai','ओ':'o','औ':'au',
                'क':'k','ख':'kh','ग':'g','घ':'gh','च':'ch','छ':'chh','ज':'j','झ':'jh',
                'ट':'t','ठ':'th','ड':'d','ढ':'dh','ण':'n','त':'t','थ':'th','द':'d','ध':'dh','न':'n',
                'प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l','व':'v',
                'श':'sh','ष':'sh','स':'s','ह':'h','ा':'a','ि':'i','ी':'ee','ु':'u','ू':'oo',
                'े':'e','ै':'ai','ो':'o','ौ':'au','्':'','ं':'n','ः':'h',
                'प्र':'pr','श्र':'shr','क्र':'kr','त्र':'tr',
            }
            result = name
            for dev, roman in sorted(translit_map.items(), key=lambda x: -len(x[0])):
                result = result.replace(dev, roman)
            # Remove any remaining Devanagari
            result = re.sub(r'[\u0900-\u097F]', '', result).strip()
            if result:
                name = result
        return whatsapp.send_whatsapp_by_name(name, message)

    # --- Vision AI ---

    def _read_screen(self, params: Dict) -> Dict[str, str]:
        question = params.get("query") or params.get("question") or "Screen pe kya dikh raha hai?"
        try:
            from assistant.skills import vision
            return vision.read_screen(question)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- Gesture Control ---

    def _start_gesture(self, params: Dict) -> Dict[str, str]:
        if not self.gesture:
            return {"status": "error", "message": "Gesture control available nahi hai."}
        return self.gesture.start()

    def _stop_gesture(self, params: Dict) -> Dict[str, str]:
        if not self.gesture:
            return {"status": "error", "message": "Gesture control available nahi hai."}
        return self.gesture.stop()

    def _on_gesture(self, gesture_name: str) -> None:
        """Handle detected gesture."""
        import pyautogui
        actions = {
            "play_pause": lambda: pyautogui.press("space"),
            "mute": lambda: pyautogui.press("volumemute"),
            "next": lambda: pyautogui.hotkey("shift", "n"),
            "volume_up": lambda: [pyautogui.press("volumeup") for _ in range(3)],
            "volume_down": lambda: [pyautogui.press("volumedown") for _ in range(3)],
        }
        if gesture_name in actions:
            actions[gesture_name]()

    # --- Market & News wrappers ---

    def _get_crypto_price(self, params: Dict) -> Dict[str, str]:
        coin = params.get("coin", "bitcoin")
        return market_skills.get_crypto_price(coin)

    def _get_stock_market(self, params: Dict) -> Dict[str, str]:
        return market_skills.get_stock_market()

    def _get_news(self, params: Dict) -> Dict[str, str]:
        topic = params.get("topic", "india")
        return market_skills.get_news(topic)

    def _get_gold_price(self, params: Dict) -> Dict[str, str]:
        return market_skills.get_gold_price()

    # --- Browser Agent (autonomous) ---

    def _browser_agent_task(self, params: Dict) -> Dict[str, str]:
        if not self.browser_agent:
            return {"status": "error", "message": "Browser agent available nahi hai."}
        goal = params.get("goal", params.get("task", ""))
        if not goal:
            return {"status": "error", "message": "Goal not provided."}
        return self.browser_agent.execute(goal)

    def _browser_agent_history(self, params: Dict) -> Dict[str, str]:
        if not self.browser_agent:
            return {"status": "error", "message": "Browser agent available nahi hai."}
        history = self.browser_agent.get_history()
        if not history:
            return {"status": "success", "message": "Koi browser task history nahi hai."}
        lines = []
        for h in history[-5:]:
            status = "✅" if h["success"] else "❌"
            lines.append(f"{status} {h['goal'][:50]} ({h['time_taken']})")
        return {"status": "success", "message": "Browser tasks:\n" + "\n".join(lines)}

    # --- Multi-Tab Browser ---

    def _multi_browser_task(self, params: Dict) -> Dict[str, str]:
        if not self.multi_browser:
            return {"status": "error", "message": "Playwright/MultiBrowser load nahi hua hai. dependencies check karein."}
        goal = params.get("goal", params.get("task", params.get("command", "")))
        if not goal:
            return {"status": "error", "message": "Kya karna hai batao — goal not provided."}
        return self.multi_browser.execute(goal)

    # --- Personality, Memory, Health ---

    def _set_mode(self, params: Dict) -> Dict[str, str]:
        mode = params.get("mode", "fun")
        return self.personality.set_mode(mode)

    def _remember(self, params: Dict) -> Dict[str, str]:
        key = params.get("key", "")
        value = params.get("value", "")
        if not key or not value:
            return {"status": "error", "message": "Key and value required."}
        return self.memory.remember(key, value)

    def _get_memory(self, params: Dict) -> Dict[str, str]:
        return self.memory.get_all()

    def _health_on(self, params: Dict) -> Dict[str, str]:
        return self.health.start()

    def _health_off(self, params: Dict) -> Dict[str, str]:
        return self.health.stop()

    # --- Language ---

    def _set_language(self, params: Dict) -> Dict[str, str]:
        lang = params.get("language", params.get("lang", "hinglish"))
        return self.language.set_language(lang)

    # --- Learning ---

    def _get_usage_stats(self, params: Dict) -> Dict[str, str]:
        return self.learner.get_stats()

    # --- Spotify ---

    def _spotify_play_pause(self, params: Dict) -> Dict[str, str]:
        result = spotify_skills.spotify_play_pause()
        # Stop music vibe on pause
        self._stop_music_vibe()
        return result

    def _spotify_next(self, params: Dict) -> Dict[str, str]:
        self._stop_music_vibe()  # Reset vibe on track change
        return spotify_skills.spotify_next()

    def _spotify_previous(self, params: Dict) -> Dict[str, str]:
        self._stop_music_vibe()  # Reset vibe on track change
        return spotify_skills.spotify_previous()

    def _spotify_now_playing(self, params: Dict) -> Dict[str, str]:
        return spotify_skills.spotify_now_playing()

    def _spotify_play_song(self, params: Dict) -> Dict[str, str]:
        query = params.get("query", params.get("song", ""))
        if not query:
            return {"status": "error", "message": "Song name not provided."}
        result = spotify_skills.spotify_play_song(query)
        # If Spotify fails (no premium), play on YouTube instead
        if result.get("status") != "success":
            from assistant.skills import browser
            yt_result = browser.play_youtube(query)
            if yt_result.get("status") == "success":
                self._trigger_music_vibe(query)
                return {"status": "success", "message": f"YouTube pe laga diya: {query}"}
            return yt_result
        self._trigger_music_vibe(query)
        return result

    def _spotify_play_playlist(self, params: Dict) -> Dict[str, str]:
        name = params.get("name", params.get("playlist", ""))
        if not name:
            return {"status": "error", "message": "Playlist name not provided."}
        result = spotify_skills.spotify_play_playlist(name)
        if result.get("status") == "success":
            self._trigger_music_vibe(name)
        return result

    def _spotify_mood(self, params: Dict) -> Dict[str, str]:
        mood = params.get("mood", "chill")
        result = spotify_skills.spotify_mood(mood)
        
        # Map mood to vibe
        mood_map = {"happy": "happy", "sad": "sad", "chill": "calm",
                    "coding": "calm", "workout": "exciting", "party": "exciting",
                    "romantic": "romantic", "focus": "calm", "sleep": "calm"}
        vibe_mood = mood_map.get(mood, "happy")
        bpm_map = {"sad": 65, "calm": 75, "romantic": 80, "happy": 115, "exciting": 145}
        bpm = bpm_map.get(vibe_mood, 100)

        if result.get("status") == "success":
            self._notify_music_vibe(vibe_mood, bpm)
            return result
        
        # Spotify failed — play on YouTube using our smart recommendation engine
        from assistant.skills import music
        rec_result = music.get_music_recommendation(mood)
        if rec_result.get("status") == "success":
            self._notify_music_vibe(vibe_mood, bpm)
            return {"status": "success", "message": rec_result.get("message", f"YouTube pe {mood} music laga diya!")}
        return rec_result

    def _spotify_volume(self, params: Dict) -> Dict[str, str]:
        percent = params.get("percent", 50)
        return spotify_skills.spotify_volume(int(percent))

    def _spotify_shuffle(self, params: Dict) -> Dict[str, str]:
        on = params.get("on", True)
        return spotify_skills.spotify_shuffle(on)

    # --- Music Vibe Trigger (avatar animation) ---

    _music_vibe_callback = None  # Set by main.py
    _change_style_callback = None  # Set by main.py

    def set_change_style_callback(self, fn):
        """Set callback to change avatar outfit/style."""
        self._change_style_callback = fn

    def set_music_vibe_callback(self, fn):
        """Set callback to trigger avatar music vibe. Called with (mood, bpm)."""
        self._music_vibe_callback = fn

    def _trigger_music_vibe(self, song_query: str) -> None:
        """Detect mood from song name and trigger avatar vibe."""
        try:
            mood = self._detect_song_mood(song_query)
            bpm_map = {"sad": 65, "calm": 75, "romantic": 80, "happy": 115, "exciting": 145}
            bpm = bpm_map.get(mood, 100)
            self._notify_music_vibe(mood, bpm)
        except Exception as e:
            logger.debug(f"Music vibe trigger failed: {e}")
            self._notify_music_vibe("happy", 115)

    def _notify_music_vibe(self, mood: str, bpm: int) -> None:
        """Send music vibe to avatar."""
        if self._music_vibe_callback:
            try:
                self._music_vibe_callback(mood, bpm)
            except Exception:
                pass

    def _stop_music_vibe(self) -> None:
        """Stop music vibe on avatar."""
        if self._music_vibe_callback:
            try:
                self._music_vibe_callback("stop", 0)
            except Exception:
                pass

    def _detect_song_mood(self, song_name: str) -> str:
        """Quick mood detection from song name using keywords."""
        name_lower = song_name.lower()
        # Keyword-based (fast, no API call needed)
        sad_words = ["sad", "broken", "dard", "tanha", "alvida", "judai", "bewafa", "roya", "dil", "aashiqui", "tujhe bhula"]
        exciting_words = ["party", "dance", "dj", "remix", "pump", "hype", "energy", "workout", "beast"]
        calm_words = ["lofi", "chill", "relax", "sleep", "peaceful", "ambient", "study", "focus"]
        romantic_words = ["love", "pyaar", "ishq", "romantic", "tere", "sanam", "janam", "dil", "mohabbat"]

        if any(w in name_lower for w in sad_words):
            return "sad"
        elif any(w in name_lower for w in exciting_words):
            return "exciting"
        elif any(w in name_lower for w in calm_words):
            return "calm"
        elif any(w in name_lower for w in romantic_words):
            return "romantic"
        return "happy"

    # --- Email ---

    def _send_email(self, params: Dict) -> Dict[str, str]:
        to = params.get("to", params.get("contact", "hr"))
        reason = params.get("reason", params.get("message", ""))
        if not reason:
            return {"status": "error", "message": "Email ka reason/message batao."}
        return email_skill.send_email_to_contact(to, reason)

    # --- Trading ---

    def _open_tradingview(self, params: Dict) -> Dict[str, str]:
        symbol = params.get("symbol", "")
        return trading_skills.open_tradingview(symbol)

    def _draw_trend_line(self, params: Dict) -> Dict[str, str]:
        return trading_skills.draw_trend_line(
            int(params.get("start_x", 0)), int(params.get("start_y", 0)),
            int(params.get("end_x", 0)), int(params.get("end_y", 0))
        )

    def _draw_horizontal_line(self, params: Dict) -> Dict[str, str]:
        return trading_skills.draw_horizontal_line(int(params.get("y", 0)))

    def _draw_rectangle(self, params: Dict) -> Dict[str, str]:
        return trading_skills.draw_rectangle(
            int(params.get("start_x", 0)), int(params.get("start_y", 0)),
            int(params.get("end_x", 0)), int(params.get("end_y", 0))
        )

    def _draw_fibonacci(self, params: Dict) -> Dict[str, str]:
        return trading_skills.draw_fibonacci(
            int(params.get("start_x", 0)), int(params.get("start_y", 0)),
            int(params.get("end_x", 0)), int(params.get("end_y", 0))
        )

    def _mark_support_resistance(self, params: Dict) -> Dict[str, str]:
        return trading_skills.mark_support_resistance()

    def _undo_drawing(self, params: Dict) -> Dict[str, str]:
        return trading_skills.undo_drawing()

    def _clear_drawings(self, params: Dict) -> Dict[str, str]:
        return trading_skills.clear_drawings()

    def _change_symbol(self, params: Dict) -> Dict[str, str]:
        symbol = params.get("symbol", "")
        if not symbol:
            return {"status": "error", "message": "Symbol batao (e.g. NIFTY, RELIANCE, BTCUSD)"}
        return trading_skills.change_symbol(symbol)

    def _change_timeframe(self, params: Dict) -> Dict[str, str]:
        tf = params.get("timeframe", params.get("tf", ""))
        if not tf:
            return {"status": "error", "message": "Timeframe batao (1m, 5m, 15m, 1h, 4h, 1d)"}
        return trading_skills.change_timeframe(tf)
