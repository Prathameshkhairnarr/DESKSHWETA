"""
Desktop tool wrappers.

Bridges the existing DesktopController (~90 actions) into the agent tool
registry with proper metadata (description, risk level, timeout, params schema).
No business logic lives here — all calls forward to DesktopController.execute().

Call register_desktop_tools(dc) once at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from agent.types import RiskLevel, ToolResult
from agent.tools.registry import register_function

if TYPE_CHECKING:
    from assistant.desktop_control import DesktopController

# ---------------------------------------------------------------------------
# Action metadata table
# (action_name, description, risk_level, timeout_s, params_schema)
# ---------------------------------------------------------------------------
_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}

def _p(**props: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to build a params schema dict."""
    return {"type": "object", "properties": props, "required": []}

def _pr(**props_required: Dict[str, Any]) -> Dict[str, Any]:
    """Helper — all keys are required."""
    return {"type": "object", "properties": props_required,
            "required": list(props_required.keys())}


_ACTION_META: list[tuple[str, str, RiskLevel, int, Dict[str, Any]]] = [
    # ── Browser / Media ────────────────────────────────────────────────────
    ("open_youtube",        "YouTube kholna",                                   RiskLevel.LOW,  10, _p()),
    ("open_google",         "Google pe search karna",                           RiskLevel.LOW,  10, _p(query=_STR)),
    ("open_website",        "Koi bhi website kholna",                           RiskLevel.LOW,  10, _p(url=_STR)),
    ("play_youtube",        "YouTube pe gaana/video play karna",                RiskLevel.LOW,  20, _p(query=_STR)),
    ("media_play_pause",    "Media play/pause toggle karna",                    RiskLevel.LOW,  5,  _p()),
    ("media_fullscreen",    "Video fullscreen karna",                           RiskLevel.LOW,  5,  _p()),
    ("media_exit_fullscreen","Fullscreen se bahar aana",                        RiskLevel.LOW,  5,  _p()),
    ("media_next",          "Next track/video",                                 RiskLevel.LOW,  5,  _p()),
    ("media_previous",      "Previous track/video",                             RiskLevel.LOW,  5,  _p()),
    ("media_forward",       "10 second aage jana",                              RiskLevel.LOW,  5,  _p()),
    ("media_rewind",        "10 second peeche jana",                            RiskLevel.LOW,  5,  _p()),
    ("media_mute",          "Audio mute karna",                                 RiskLevel.LOW,  5,  _p()),
    ("media_volume_up",     "Media volume badhana",                             RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("media_volume_down",   "Media volume kam karna",                           RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("media_set_volume",    "Media volume set karna (0-100)",                   RiskLevel.LOW,  5,  _p(percent=_INT)),
    ("media_captions",      "Subtitles/captions toggle karna",                  RiskLevel.LOW,  5,  _p()),
    ("browser_new_tab",     "Browser mein new tab kholna",                      RiskLevel.LOW,  5,  _p()),
    ("browser_close_tab",   "Browser mein current tab band karna",              RiskLevel.LOW,  5,  _p()),
    ("browser_switch_tab",  "Browser mein next tab pe switch karna",            RiskLevel.LOW,  5,  _p()),
    ("browser_back",        "Browser mein back jana",                           RiskLevel.LOW,  5,  _p()),
    ("browser_refresh",     "Browser page refresh karna",                       RiskLevel.LOW,  5,  _p()),

    # ── System ─────────────────────────────────────────────────────────────
    ("take_screenshot",     "Screen ka screenshot lena",                        RiskLevel.LOW,  10, _p()),
    ("get_time",            "Abhi ka time batana",                              RiskLevel.LOW,  5,  _p()),
    ("get_date",            "Aaj ki date batana",                               RiskLevel.LOW,  5,  _p(query_type=_STR)),
    ("volume_up",           "System volume badhana",                            RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("volume_down",         "System volume kam karna",                          RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("volume_mute",         "System audio mute/unmute karna",                   RiskLevel.LOW,  5,  _p()),
    ("brightness_up",       "Screen brightness badhana",                        RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("brightness_down",     "Screen brightness kam karna",                      RiskLevel.LOW,  5,  _p(steps=_INT)),
    ("set_brightness",      "Screen brightness set karna (0-100)",              RiskLevel.LOW,  5,  _p(level=_INT)),
    ("lock_screen",         "PC lock karna",                                    RiskLevel.MEDIUM, 5, _p()),
    ("open_file_manager",   "File manager (Explorer) kholna",                   RiskLevel.LOW,  5,  _p()),
    ("type_text",           "Keyboard se text type karna",                      RiskLevel.MEDIUM, 10, _p(text=_STR)),
    ("copy_to_clipboard",   "Text clipboard pe copy karna",                     RiskLevel.LOW,  5,  _p(text=_STR)),
    ("run_command",         "Shell command run karna",                          RiskLevel.HIGH, 30, _p(command=_STR)),
    ("sleep_pc",            "PC sleep mode mein dalna",                         RiskLevel.MEDIUM, 5, _p()),
    ("shutdown_pc",         "PC band karna (shutdown)",                         RiskLevel.HIGH, 5,  _p()),
    ("restart_pc",          "PC restart karna",                                 RiskLevel.HIGH, 5,  _p()),
    ("empty_recycle_bin",   "Recycle bin khaali karna",                         RiskLevel.HIGH, 10, _p()),
    ("send_social_message", "Social media pe message bhejn",                    RiskLevel.HIGH, 20, _p(app_name=_STR, person_name=_STR, message=_STR)),

    # ── Apps ───────────────────────────────────────────────────────────────
    ("open_notepad",        "Notepad kholna",                                   RiskLevel.LOW,  5,  _p()),
    ("open_calculator",     "Calculator kholna",                                RiskLevel.LOW,  5,  _p()),
    ("open_terminal",       "Terminal/Command Prompt kholna",                   RiskLevel.LOW,  5,  _p()),
    ("open_vscode",         "VS Code kholna",                                   RiskLevel.LOW,  5,  _p()),
    ("open_spotify",        "Spotify kholna",                                   RiskLevel.LOW,  5,  _p()),
    ("open_app",            "Koi bhi app kholna naam se",                       RiskLevel.LOW,  10, _p(app_name=_STR)),
    ("close_app",           "Koi bhi app band karna",                           RiskLevel.MEDIUM, 5, _p(app_name=_STR)),
    ("send_file_to_telegram","Telegram pe file bhejni",                         RiskLevel.MEDIUM, 30, _p(file_name=_STR)),

    # ── Weather ────────────────────────────────────────────────────────────
    ("get_weather",         "Mausam/weather check karna",                       RiskLevel.LOW,  15, _p(city=_STR)),

    # ── Timer / Reminder ───────────────────────────────────────────────────
    ("set_timer",           "Timer set karna (seconds mein)",                   RiskLevel.LOW,  5,  _p(seconds=_INT)),
    ("set_reminder",        "Reminder set karna",                               RiskLevel.LOW,  5,  _p(message=_STR, minutes=_INT)),
    ("list_timers",         "Active timers dikhana",                            RiskLevel.LOW,  5,  _p()),
    ("cancel_timer",        "Timer cancel karna",                               RiskLevel.LOW,  5,  _p(id=_STR)),

    # ── File Management ────────────────────────────────────────────────────
    ("create_file",         "Naya file banana",                                 RiskLevel.MEDIUM, 5,  _p(filename=_STR, content=_STR)),
    ("create_folder",       "Naya folder banana",                               RiskLevel.LOW,  5,   _p(foldername=_STR)),
    ("delete_file",         "File delete karna",                                RiskLevel.HIGH, 5,   _p(filename=_STR)),
    ("rename_file",         "File rename karna",                                RiskLevel.MEDIUM, 5, _p(old_name=_STR, new_name=_STR)),
    ("move_file",           "File move karna",                                  RiskLevel.MEDIUM, 5, _p(filename=_STR, destination=_STR)),
    ("copy_file",           "File copy karna",                                  RiskLevel.LOW,  5,   _p(filename=_STR, destination=_STR)),
    ("list_files",          "Folder ki files dikhana",                          RiskLevel.LOW,  10,  _p(folder=_STR)),
    ("open_file",           "File kholna",                                      RiskLevel.LOW,  10,  _p(filename=_STR)),
    ("search_file",         "File dhundna naam se",                             RiskLevel.LOW,  60,  _p(name=_STR, location=_STR)),
    ("search_and_open",     "File dhundh ke kholna",                            RiskLevel.LOW,  60,  _p(name=_STR)),
    ("compress_folder",     "Folder ko zip karna",                              RiskLevel.MEDIUM, 60, _p(folder_path=_STR)),
    ("extract_zip",         "Zip file extract karna",                           RiskLevel.MEDIUM, 30, _p(zip_path=_STR, extract_to=_STR)),

    # ── System Info ────────────────────────────────────────────────────────
    ("get_battery",         "Battery level check karna",                        RiskLevel.LOW,  5,  _p()),
    ("get_ram_usage",       "RAM usage check karna",                            RiskLevel.LOW,  5,  _p()),
    ("get_storage",         "Storage/disk usage check karna",                   RiskLevel.LOW,  5,  _p()),
    ("get_cpu_usage",       "CPU usage check karna",                            RiskLevel.LOW,  5,  _p()),
    ("get_wifi_status",     "WiFi status check karna",                          RiskLevel.LOW,  5,  _p()),
    ("get_system_info",     "Poora system info dekhna",                         RiskLevel.LOW,  5,  _p()),

    # ── Notes / Tasks ──────────────────────────────────────────────────────
    ("add_note",            "Note/todo add karna",                              RiskLevel.LOW,  5,  _p(text=_STR)),
    ("list_notes",          "Saare notes dikhana",                              RiskLevel.LOW,  5,  _p()),
    ("delete_note",         "Note delete karna",                                RiskLevel.MEDIUM, 5, _p(id=_STR)),
    ("complete_note",       "Note complete mark karna",                         RiskLevel.LOW,  5,  _p(id=_STR)),
    ("clear_notes",         "Saare notes clear karna",                          RiskLevel.HIGH, 5,  _p()),

    # ── Window Management ──────────────────────────────────────────────────
    ("snap_left",           "Window left side pe snap karna",                   RiskLevel.LOW,  5,  _p()),
    ("snap_right",          "Window right side pe snap karna",                  RiskLevel.LOW,  5,  _p()),
    ("maximize_window",     "Window maximize karna",                            RiskLevel.LOW,  5,  _p()),
    ("minimize_window",     "Window minimize karna",                            RiskLevel.LOW,  5,  _p()),
    ("minimize_all",        "Saari windows minimize karna",                     RiskLevel.LOW,  5,  _p()),
    ("switch_window",       "Alt+Tab — dusri window pe jana",                   RiskLevel.LOW,  5,  _p()),
    ("close_window",        "Current window band karna",                        RiskLevel.MEDIUM, 5, _p()),
    ("task_view",           "Task view / Win+Tab kholna",                       RiskLevel.LOW,  5,  _p()),

    # ── Browser Automation ─────────────────────────────────────────────────
    ("auto_search_and_play","Browser mein search karke video play karna",       RiskLevel.LOW,  60, _p(query=_STR)),
    ("auto_youtube_search", "YouTube pe search karna (Selenium)",               RiskLevel.LOW,  60, _p(query=_STR)),
    ("auto_play_first",     "First video play karna",                           RiskLevel.LOW,  30, _p()),
    ("auto_google_search",  "Google pe search karna (Selenium)",                RiskLevel.LOW,  60, _p(query=_STR)),
    ("auto_open_url",       "Browser mein URL kholna (Selenium)",               RiskLevel.LOW,  30, _p(url=_STR)),
    ("auto_click",          "Page pe element click karna",                      RiskLevel.MEDIUM, 15, _p(text=_STR)),
    ("auto_type",           "Page input mein type karna",                       RiskLevel.MEDIUM, 10, _p(text=_STR)),
    ("auto_scroll_down",    "Page scroll down karna",                           RiskLevel.LOW,  5,  _p()),
    ("auto_scroll_up",      "Page scroll up karna",                             RiskLevel.LOW,  5,  _p()),
    ("auto_go_back",        "Browser back button (Selenium)",                   RiskLevel.LOW,  5,  _p()),
    ("auto_close_browser",  "Browser band karna",                               RiskLevel.LOW,  10, _p()),
    ("browser_agent_task",  "Browser autonomous task — koi bhi web goal",       RiskLevel.MEDIUM, 120, _p(goal=_STR)),
    ("multi_browser_task",  "Multi-tab browser task (Playwright)",              RiskLevel.MEDIUM, 120, _p(goal=_STR)),

    # ── WhatsApp / Comms ───────────────────────────────────────────────────
    ("send_whatsapp",           "Phone number se WhatsApp message bhejn",       RiskLevel.HIGH, 30, _p(phone=_STR, message=_STR)),
    ("send_whatsapp_by_name",   "Naam se WhatsApp message bhejn",               RiskLevel.HIGH, 30, _p(name=_STR, message=_STR)),
    ("daily_briefing",          "Aaj ka daily briefing sunna",                  RiskLevel.LOW,  30, _p()),
    ("morning_briefing",        "Morning briefing — weather+crypto+fun fact",   RiskLevel.LOW,  30, _p()),

    # ── Vision ─────────────────────────────────────────────────────────────
    ("read_screen",         "Screen pe kya dikh raha hai — AI se puchna",       RiskLevel.LOW,  20, _p(query=_STR)),
    ("react_to_screen",     "Screen dekh ke react karna",                       RiskLevel.LOW,  20, _p(query=_STR)),

    # ── Gesture ────────────────────────────────────────────────────────────
    ("start_gesture",       "Gesture control shuru karna",                      RiskLevel.LOW,  5,  _p()),
    ("stop_gesture",        "Gesture control band karna",                       RiskLevel.LOW,  5,  _p()),

    # ── Market / Finance ───────────────────────────────────────────────────
    ("get_crypto_price",    "Crypto coin ki price dekhna",                      RiskLevel.LOW,  15, _p(coin=_STR)),
    ("get_stock_market",    "Indian stock market status dekhna",                RiskLevel.LOW,  15, _p()),
    ("get_news",            "Latest news dekhna",                               RiskLevel.LOW,  15, _p(topic=_STR)),
    ("get_gold_price",      "Gold ki price dekhna",                             RiskLevel.LOW,  15, _p()),

    # ── Personality / Memory ───────────────────────────────────────────────
    ("set_mode",            "Shweta ka mood/mode change karna",                 RiskLevel.LOW,  5,  _p(mode=_STR)),
    ("remember",            "User ki baat yaad rakhna (key-value)",             RiskLevel.LOW,  5,  _p(key=_STR, value=_STR)),
    ("remember_user_info",  "User fact ya info yaad rakhna",                    RiskLevel.LOW,  5,  _p(info=_STR)),
    ("get_memory",          "Stored memories dekhna",                           RiskLevel.LOW,  5,  _p()),
    ("health_reminders_on", "Health reminders chalu karna",                     RiskLevel.LOW,  5,  _p()),
    ("health_reminders_off","Health reminders band karna",                      RiskLevel.LOW,  5,  _p()),
    ("set_language",        "Language change karna",                            RiskLevel.LOW,  5,  _p(language=_STR)),
    ("get_usage_stats",     "Usage statistics dekhna",                          RiskLevel.LOW,  5,  _p()),
    ("change_style",        "Avatar ka outfit/style change karna",              RiskLevel.LOW,  5,  _p(style=_STR)),
    ("identify_music",      "Abhi jo gaana bajh raha hai uska naam batana",     RiskLevel.LOW,  10, _p()),

    # ── Spotify ────────────────────────────────────────────────────────────
    ("spotify_play_pause",  "Spotify play/pause karna",                         RiskLevel.LOW,  5,  _p()),
    ("spotify_next",        "Spotify next track",                               RiskLevel.LOW,  5,  _p()),
    ("spotify_previous",    "Spotify previous track",                           RiskLevel.LOW,  5,  _p()),
    ("spotify_now_playing", "Spotify pe abhi kya chal raha hai",                RiskLevel.LOW,  5,  _p()),
    ("spotify_play_song",   "Spotify pe song play karna",                       RiskLevel.LOW,  10, _p(query=_STR)),
    ("spotify_play_playlist","Spotify playlist play karna",                     RiskLevel.LOW,  10, _p(name=_STR)),
    ("spotify_mood",        "Mood ke according Spotify music lagana",           RiskLevel.LOW,  10, _p(mood=_STR)),
    ("spotify_volume",      "Spotify volume set karna",                         RiskLevel.LOW,  5,  _p(percent=_INT)),
    ("spotify_shuffle",     "Spotify shuffle on/off karna",                     RiskLevel.LOW,  5,  _p(on=_BOOL)),

    # ── Email ──────────────────────────────────────────────────────────────
    ("send_email",          "Email bhejna",                                     RiskLevel.HIGH, 30, _p(to=_STR, reason=_STR)),

    # ── TradingView ────────────────────────────────────────────────────────
    ("open_tradingview",     "TradingView pe chart kholna",                     RiskLevel.LOW,  15, _p(symbol=_STR)),
    ("draw_trend_line",      "Chart pe trend line banana",                      RiskLevel.LOW,  10, _p(start_x=_INT, start_y=_INT, end_x=_INT, end_y=_INT)),
    ("draw_horizontal_line", "Chart pe horizontal line banana",                 RiskLevel.LOW,  10, _p(y=_INT)),
    ("draw_rectangle",       "Chart pe rectangle banana",                       RiskLevel.LOW,  10, _p(start_x=_INT, start_y=_INT, end_x=_INT, end_y=_INT)),
    ("draw_fibonacci",       "Chart pe Fibonacci retracement banana",           RiskLevel.LOW,  10, _p(start_x=_INT, start_y=_INT, end_x=_INT, end_y=_INT)),
    ("mark_support_resistance","Support/resistance lines mark karna",           RiskLevel.LOW,  15, _p()),
    ("undo_drawing",         "Last drawing undo karna",                         RiskLevel.LOW,  5,  _p()),
    ("clear_drawings",       "Saari drawings clear karna",                      RiskLevel.MEDIUM, 5, _p()),
    ("change_symbol",        "Chart ka symbol change karna",                    RiskLevel.LOW,  10, _p(symbol=_STR)),
    ("change_timeframe",     "Chart ka timeframe change karna",                 RiskLevel.LOW,  10, _p(timeframe=_STR)),

    # ── Games ──────────────────────────────────────────────────────────────
    ("start_game",           "Ek game shuru karna",                             RiskLevel.LOW,  5,  _p(game=_STR)),
    ("play_turn",            "Game mein apni turn khełna",                      RiskLevel.LOW,  5,  _p(choice=_STR)),
]


def register_desktop_tools(dc: "DesktopController") -> None:
    """Register all DesktopController actions in the global tool registry.

    Called once at startup by the orchestrator with the shared DesktopController instance.
    """
    registered = 0
    for action, desc, risk, timeout, schema in _ACTION_META:
        # Create a closure capturing the action name and dc reference
        def _make_fn(a: str, _dc: "DesktopController"):
            def _fn(**params: Any) -> ToolResult:
                result = _dc.execute(a, params)
                return ToolResult.from_dc_result(result) if isinstance(result, dict) else ToolResult.ok(str(result))
            _fn.__name__ = a
            return _fn

        register_function(
            fn=_make_fn(action, dc),
            name=action,
            description=desc,
            risk_level=risk,
            timeout=timeout,
            json_schema=schema,
            category=_infer_category(action),
        )
        registered += 1

    import logging
    logging.getLogger(__name__).info(
        "[ToolRegistry] Registered %d desktop tools from DesktopController", registered
    )


def _infer_category(name: str) -> str:
    if name.startswith("spotify_"):
        return "music"
    if name.startswith("browser") or name.startswith("auto_") or name.startswith("media_"):
        return "browser"
    if name.startswith("get_") and name in ("get_weather", "get_news", "get_crypto_price",
                                             "get_stock_market", "get_gold_price"):
        return "info"
    if name.startswith("get_") and name in ("get_battery", "get_ram_usage", "get_storage",
                                             "get_cpu_usage", "get_wifi_status", "get_system_info"):
        return "system_info"
    if name in ("create_file", "create_folder", "delete_file", "rename_file", "move_file",
                "copy_file", "list_files", "open_file", "search_file", "search_and_open",
                "compress_folder", "extract_zip"):
        return "files"
    if name in ("send_whatsapp", "send_whatsapp_by_name", "send_email", "send_file_to_telegram",
                "send_social_message"):
        return "comms"
    if name.startswith("draw_") or name in ("open_tradingview", "mark_support_resistance",
                                            "undo_drawing", "clear_drawings", "change_symbol",
                                            "change_timeframe"):
        return "trading"
    if name in ("remember", "remember_user_info", "get_memory", "set_mode", "identify_music",
                "set_language", "get_usage_stats", "health_reminders_on", "health_reminders_off",
                "change_style"):
        return "memory"
    if name in ("read_screen", "react_to_screen", "start_gesture", "stop_gesture"):
        return "vision"
    if name in ("add_note", "list_notes", "delete_note", "complete_note", "clear_notes",
                "set_timer", "set_reminder", "list_timers", "cancel_timer",
                "daily_briefing", "morning_briefing", "start_game", "play_turn"):
        return "productivity"
    if name in ("volume_up", "volume_down", "volume_mute", "brightness_up", "brightness_down",
                "set_brightness", "lock_screen", "open_file_manager", "type_text",
                "copy_to_clipboard", "run_command", "sleep_pc", "shutdown_pc", "restart_pc",
                "empty_recycle_bin", "get_time", "get_date", "take_screenshot"):
        return "system"
    if name in ("snap_left", "snap_right", "maximize_window", "minimize_window", "minimize_all",
                "switch_window", "close_window", "task_view"):
        return "windows"
    if name in ("open_notepad", "open_calculator", "open_terminal", "open_vscode", "open_spotify",
                "open_app", "close_app", "open_youtube", "open_google", "open_website",
                "play_youtube", "send_file_to_telegram"):
        return "apps"
    return "general"
