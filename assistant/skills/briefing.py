"""
Daily Briefing Skill — Time, weather, battery, notes in one go.
"""

import logging
from datetime import datetime
from typing import Dict

import psutil

from assistant.skills.weather import get_weather
from assistant.skills.notes import _load_notes
from config import DEFAULT_CITY

logger = logging.getLogger(__name__)


def daily_briefing() -> Dict[str, str]:
    """Get a complete daily briefing — time, weather, battery, pending notes."""
    try:
        parts = []

        # Time & Date
        now = datetime.now()
        parts.append(f"🕐 {now.strftime('%I:%M %p')}, {now.strftime('%d %B %Y, %A')}")

        # Weather
        try:
            weather = get_weather(DEFAULT_CITY)
            if weather["status"] == "success":
                parts.append(f"🌤 {weather['message']}")
        except Exception:
            pass

        # Battery
        try:
            battery = psutil.sensors_battery()
            if battery:
                plug = "charging" if battery.power_plugged else "not charging"
                parts.append(f"🔋 Battery: {battery.percent}% ({plug})")
        except Exception:
            pass

        # Pending notes
        try:
            notes = _load_notes()
            pending = [n for n in notes if not n.get("done")]
            if pending:
                parts.append(f"📝 {len(pending)} pending notes:")
                for n in pending[:3]:
                    parts.append(f"   • {n['text']}")
                if len(pending) > 3:
                    parts.append(f"   ... aur {len(pending) - 3} aur")
            else:
                parts.append("📝 Koi pending note nahi hai.")
        except Exception:
            pass

        msg = "\n".join(parts)
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}
