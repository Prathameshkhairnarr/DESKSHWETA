"""
Timer/Reminder Skill for Shweta AI Desktop Assistant.
Handles timers and reminders using threading.
"""

import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TimerManager:
    """Manages timers and reminders with threading."""

    def __init__(self, on_timer_complete: Optional[Callable] = None) -> None:
        """
        Initialize the timer manager.

        Args:
            on_timer_complete: Callback function when a timer completes.
                              Receives (timer_id, message) as arguments.
        """
        self._timers: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.on_timer_complete = on_timer_complete

    def set_timer(self, seconds: int) -> Dict[str, str]:
        """
        Set a countdown timer.

        Args:
            seconds: Duration in seconds.

        Returns:
            Result dictionary with timer ID.
        """
        timer_id = str(uuid.uuid4())[:8]
        message = f"Timer ({seconds} seconds) complete!"

        timer = threading.Timer(seconds, self._timer_callback, args=[timer_id, message])
        timer.daemon = True
        timer.start()

        with self._lock:
            self._timers[timer_id] = {
                "id": timer_id,
                "type": "timer",
                "seconds": seconds,
                "message": message,
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(seconds=seconds),
                "timer_obj": timer,
                "active": True
            }

        logger.info(f"Timer set: {timer_id} for {seconds} seconds.")

        # Format time for display
        if seconds >= 3600:
            time_str = f"{seconds // 3600} ghante {(seconds % 3600) // 60} minute"
        elif seconds >= 60:
            time_str = f"{seconds // 60} minute"
        else:
            time_str = f"{seconds} second"

        return {
            "status": "success",
            "message": f"Timer set kar diya — {time_str} ke liye.",
            "timer_id": timer_id
        }

    def set_reminder(self, message: str, minutes: int) -> Dict[str, str]:
        """
        Set a reminder with a custom message.

        Args:
            message: Reminder message.
            minutes: Minutes until reminder.

        Returns:
            Result dictionary with timer ID.
        """
        timer_id = str(uuid.uuid4())[:8]
        seconds = minutes * 60

        reminder_msg = f"Reminder: {message}"
        timer = threading.Timer(seconds, self._timer_callback, args=[timer_id, reminder_msg])
        timer.daemon = True
        timer.start()

        with self._lock:
            self._timers[timer_id] = {
                "id": timer_id,
                "type": "reminder",
                "seconds": seconds,
                "message": reminder_msg,
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(seconds=seconds),
                "timer_obj": timer,
                "active": True
            }

        logger.info(f"Reminder set: {timer_id} — '{message}' in {minutes} minutes.")
        return {
            "status": "success",
            "message": f"Reminder set kar diya — {minutes} minute baad yaad dilaaungi: {message}",
            "timer_id": timer_id
        }

    def list_timers(self) -> Dict[str, object]:
        """
        List all active timers and reminders.

        Returns:
            Result dictionary with list of active timers.
        """
        with self._lock:
            active_timers: List[Dict] = []
            now = datetime.now()

            for tid, info in self._timers.items():
                if info["active"]:
                    remaining = (info["expires_at"] - now).total_seconds()
                    if remaining > 0:
                        active_timers.append({
                            "id": tid,
                            "type": info["type"],
                            "message": info["message"],
                            "remaining_seconds": int(remaining)
                        })
                    else:
                        info["active"] = False

        if not active_timers:
            return {
                "status": "success",
                "message": "Koi active timer nahi hai.",
                "timers": []
            }

        timer_list = []
        for t in active_timers:
            remaining = t["remaining_seconds"]
            if remaining >= 60:
                time_str = f"{remaining // 60}m {remaining % 60}s"
            else:
                time_str = f"{remaining}s"
            timer_list.append(f"• [{t['id']}] {t['type']}: {time_str} baaki")

        message = "Active timers:\n" + "\n".join(timer_list)
        return {
            "status": "success",
            "message": message,
            "timers": active_timers
        }

    def cancel_timer(self, timer_id: str) -> Dict[str, str]:
        """
        Cancel a specific timer by ID.

        Args:
            timer_id: The timer ID to cancel.

        Returns:
            Result dictionary.
        """
        with self._lock:
            if timer_id in self._timers:
                timer_info = self._timers[timer_id]
                if timer_info["active"]:
                    timer_info["timer_obj"].cancel()
                    timer_info["active"] = False
                    logger.info(f"Timer cancelled: {timer_id}")
                    return {
                        "status": "success",
                        "message": f"Timer {timer_id} cancel kar diya."
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"Timer {timer_id} already complete ho chuka hai."
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Timer {timer_id} nahi mila."
                }

    def _timer_callback(self, timer_id: str, message: str) -> None:
        """
        Internal callback when a timer completes.

        Args:
            timer_id: The completed timer's ID.
            message: The timer/reminder message.
        """
        with self._lock:
            if timer_id in self._timers:
                self._timers[timer_id]["active"] = False

        logger.info(f"Timer completed: {timer_id} — {message}")

        if self.on_timer_complete:
            self.on_timer_complete(timer_id, message)

    def cancel_all(self) -> None:
        """Cancel all active timers."""
        with self._lock:
            for tid, info in self._timers.items():
                if info["active"]:
                    info["timer_obj"].cancel()
                    info["active"] = False
            logger.info("All timers cancelled.")
