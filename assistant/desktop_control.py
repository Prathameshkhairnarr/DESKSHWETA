"""
Desktop Control Module for Shweta AI Desktop Assistant.
Routes AI actions to the appropriate skill functions.
"""

import logging
from typing import Any, Callable, Dict, Optional

from assistant.skills import browser, system, apps, weather
from assistant.skills.timer import TimerManager
from assistant.skills import files as file_skills
from assistant.skills import sysinfo, notes, windows, briefing, whatsapp, vision
from assistant.skills import market as market_skills
from assistant.skills.gesture import GestureController
from assistant.skills.browser_agent import BrowserAgent
from assistant.skills.browser_auto import BrowserAutomation

logger = logging.getLogger(__name__)


class DesktopController:
    """Routes and executes desktop actions from AI responses."""

    def __init__(self, on_timer_complete: Optional[Callable] = None) -> None:
        """
        Initialize the desktop controller with all skill modules.

        Args:
            on_timer_complete: Callback for when timers complete.
        """
        self.timer_manager = TimerManager(on_timer_complete=on_timer_complete)
        self.browser_auto = BrowserAutomation()
        self.gesture = GestureController(on_gesture=self._on_gesture)
        self.browser_agent = BrowserAgent()
        self.browser_auto = BrowserAutomation()

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
            # WhatsApp
            "send_whatsapp": self._send_whatsapp,
            "send_whatsapp_by_name": self._send_whatsapp_by_name,
            # Vision AI
            "read_screen": self._read_screen,
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
        }

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Execute a desktop action by name.

        Args:
            action: The action name to execute.
            params: Parameters for the action.

        Returns:
            Result dictionary from the executed skill.
        """
        if action == "none" or not action:
            return {"status": "no_action", "message": "No action needed."}

        handler = self._action_map.get(action)
        if handler:
            try:
                result = handler(params)
                logger.info(f"Action executed: {action} → {result.get('status')}")
                return result
            except Exception as e:
                logger.error(f"Action failed: {action} — {e}")
                return {"status": "error", "message": f"Action failed: {str(e)}"}
        else:
            logger.warning(f"Unknown action: {action}")
            return {"status": "error", "message": f"Unknown action: {action}"}

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
        return browser.play_youtube(query)

    # --- System skill wrappers ---

    def _take_screenshot(self, params: Dict) -> Dict[str, str]:
        return system.take_screenshot()

    def _get_time(self, params: Dict) -> Dict[str, str]:
        return system.get_time()

    def _get_date(self, params: Dict) -> Dict[str, str]:
        return system.get_date()

    def _volume_up(self, params: Dict) -> Dict[str, str]:
        steps = params.get("steps", 5)
        return system.volume_up(int(steps))

    def _volume_down(self, params: Dict) -> Dict[str, str]:
        steps = params.get("steps", 5)
        return system.volume_down(int(steps))

    def _volume_mute(self, params: Dict) -> Dict[str, str]:
        return system.volume_mute()

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
        seconds = params.get("seconds", 60)
        return self.timer_manager.set_timer(int(seconds))

    def _set_reminder(self, params: Dict) -> Dict[str, str]:
        message = params.get("message", "Reminder!")
        minutes = params.get("minutes", 5)
        return self.timer_manager.set_reminder(message, int(minutes))

    def _list_timers(self, params: Dict) -> Dict[str, str]:
        return self.timer_manager.list_timers()

    def _cancel_timer(self, params: Dict) -> Dict[str, str]:
        timer_id = params.get("id", "")
        if not timer_id:
            return {"status": "error", "message": "Timer ID not provided."}
        return self.timer_manager.cancel_timer(timer_id)

    # --- Media/Browser control wrappers ---

    def _media_play_pause(self, params: Dict) -> Dict[str, str]:
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
        return browser.browser_close_tab()

    def _browser_switch_tab(self, params: Dict) -> Dict[str, str]:
        return browser.browser_switch_tab()

    def _browser_back(self, params: Dict) -> Dict[str, str]:
        return browser.browser_back()

    def _browser_refresh(self, params: Dict) -> Dict[str, str]:
        return browser.browser_refresh()

    # --- Browser Automation (Selenium) wrappers ---

    def _auto_search_and_play(self, params: Dict) -> Dict[str, str]:
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.search_and_play(query)

    def _auto_youtube_search(self, params: Dict) -> Dict[str, str]:
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.search_youtube(query)

    def _auto_play_first(self, params: Dict) -> Dict[str, str]:
        return self.browser_auto.play_first_video()

    def _auto_google_search(self, params: Dict) -> Dict[str, str]:
        query = params.get("query", "")
        if not query:
            return {"status": "error", "message": "Query not provided."}
        return self.browser_auto.google_search(query)

    def _auto_open_url(self, params: Dict) -> Dict[str, str]:
        url = params.get("url", "")
        if not url:
            return {"status": "error", "message": "URL not provided."}
        return self.browser_auto.open_url(url)

    def _auto_click(self, params: Dict) -> Dict[str, str]:
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "Click target not provided."}
        return self.browser_auto.click_element(text)

    def _auto_type(self, params: Dict) -> Dict[str, str]:
        text = params.get("text", "")
        if not text:
            return {"status": "error", "message": "Text not provided."}
        return self.browser_auto.type_in_page(text)

    def _auto_scroll_down(self, params: Dict) -> Dict[str, str]:
        return self.browser_auto.scroll_down()

    def _auto_scroll_up(self, params: Dict) -> Dict[str, str]:
        return self.browser_auto.scroll_up()

    def _auto_go_back(self, params: Dict) -> Dict[str, str]:
        return self.browser_auto.go_back()

    def _auto_close_browser(self, params: Dict) -> Dict[str, str]:
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
        note_id = params.get("id", 0)
        return notes.delete_note(int(note_id))

    def _complete_note(self, params: Dict) -> Dict[str, str]:
        note_id = params.get("id", 0)
        return notes.complete_note(int(note_id))

    def _clear_notes(self, params: Dict) -> Dict[str, str]:
        return notes.clear_notes()

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
        return windows.close_window()

    def _task_view(self, params: Dict) -> Dict[str, str]:
        return windows.task_view()

    # --- Daily Briefing ---

    def _daily_briefing(self, params: Dict) -> Dict[str, str]:
        return briefing.daily_briefing()

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
        return whatsapp.send_whatsapp_by_name(name, message)

    # --- Vision AI ---

    def _read_screen(self, params: Dict) -> Dict[str, str]:
        question = params.get("question", "Screen pe kya dikh raha hai?")
        return vision.read_screen(question)

    # --- Gesture Control ---

    def _start_gesture(self, params: Dict) -> Dict[str, str]:
        return self.gesture.start()

    def _stop_gesture(self, params: Dict) -> Dict[str, str]:
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
        goal = params.get("goal", params.get("task", ""))
        if not goal:
            return {"status": "error", "message": "Goal not provided."}
        return self.browser_agent.execute(goal)

    def _browser_agent_history(self, params: Dict) -> Dict[str, str]:
        history = self.browser_agent.get_history()
        if not history:
            return {"status": "success", "message": "Koi browser task history nahi hai."}
        lines = []
        for h in history[-5:]:
            status = "✅" if h["success"] else "❌"
            lines.append(f"{status} {h['goal'][:50]} ({h['time_taken']})")
        return {"status": "success", "message": "Browser tasks:\n" + "\n".join(lines)}
