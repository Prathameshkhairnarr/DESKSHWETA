"""
Usage Pattern Learning for Shweta.
Tracks what user does and when, learns preferences, suggests actions.
AI gets this context to personalize responses.
"""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PATTERNS_FILE = PROJECT_ROOT / "usage_patterns.json"


class UsageLearner:
    """Tracks and learns user's usage patterns. Feeds context to AI."""

    def __init__(self) -> None:
        self.patterns: Dict = {
            "hourly_actions": {},
            "frequent_queries": [],
            "total_actions": {},
            "favorite_songs": [],
            "favorite_apps": [],
            "mood_history": [],       # last 10 moods
            "conversation_topics": [], # what user talks about
            "user_habits": {},        # {"morning_music": True, "night_owl": True}
            "last_updated": ""
        }
        self._load()

    def _load(self) -> None:
        if PATTERNS_FILE.exists():
            try:
                data = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
                # Merge with defaults (in case new fields added)
                for key in self.patterns:
                    if key in data:
                        self.patterns[key] = data[key]
            except Exception:
                pass

    def _save(self) -> None:
        try:
            self.patterns["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            PATTERNS_FILE.write_text(
                json.dumps(self.patterns, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def track(self, action: str, query: str = "") -> None:
        """Track an action with timestamp."""
        hour = datetime.now().strftime("%H")

        # Track hourly patterns
        if hour not in self.patterns["hourly_actions"]:
            self.patterns["hourly_actions"][hour] = {}
        hourly = self.patterns["hourly_actions"][hour]
        hourly[action] = hourly.get(action, 0) + 1

        # Track total actions
        total = self.patterns["total_actions"]
        total[action] = total.get(action, 0) + 1

        # Track frequent queries
        if query and len(query) > 2:
            self.patterns["frequent_queries"].append(query)
            self.patterns["frequent_queries"] = self.patterns["frequent_queries"][-100:]

        # Track favorite songs
        if action in ("play_youtube", "spotify_play_song") and query:
            if query not in self.patterns["favorite_songs"]:
                self.patterns["favorite_songs"].append(query)
                self.patterns["favorite_songs"] = self.patterns["favorite_songs"][-20:]

        # Track favorite apps
        if action in ("open_app", "open_spotify", "open_vscode", "open_notepad"):
            app = query or action.replace("open_", "")
            if app and app not in self.patterns["favorite_apps"]:
                self.patterns["favorite_apps"].append(app)
                self.patterns["favorite_apps"] = self.patterns["favorite_apps"][-10:]

        # Detect habits
        hour_int = int(hour)
        if action in ("play_youtube", "spotify_mood", "spotify_play_song"):
            if 5 <= hour_int <= 9:
                self.patterns["user_habits"]["morning_music"] = True
            elif 22 <= hour_int or hour_int <= 2:
                self.patterns["user_habits"]["night_owl"] = True

        self._save()

    def track_mood(self, emotion: str) -> None:
        """Track user's emotional patterns."""
        entry = {"emotion": emotion, "time": datetime.now().strftime("%H:%M"), "date": datetime.now().strftime("%Y-%m-%d")}
        self.patterns["mood_history"].append(entry)
        self.patterns["mood_history"] = self.patterns["mood_history"][-20:]
        self._save()

    def track_topic(self, user_text: str) -> None:
        """Track what user talks about (for personalization)."""
        # Extract key topics from user input
        words = user_text.lower().split()
        topics = [w for w in words if len(w) > 4 and w not in ("kaise", "kahan", "batao", "karo", "kholo", "bajao")]
        if topics:
            self.patterns["conversation_topics"].extend(topics[:2])
            self.patterns["conversation_topics"] = self.patterns["conversation_topics"][-50:]
            self._save()

    def get_ai_context(self) -> str:
        """
        Get user pattern context for AI prompt.
        This makes Shweta feel like she KNOWS the user.
        """
        parts = []

        # Favorite songs
        songs = self.patterns.get("favorite_songs", [])[-5:]
        if songs:
            parts.append(f"User ke fav songs: {', '.join(songs)}")

        # Favorite apps
        apps = self.patterns.get("favorite_apps", [])[-5:]
        if apps:
            parts.append(f"User ke fav apps: {', '.join(apps)}")

        # Current time habits
        hour = int(datetime.now().strftime("%H"))
        hourly = self.patterns.get("hourly_actions", {}).get(datetime.now().strftime("%H"), {})
        if hourly:
            top = max(hourly, key=hourly.get)
            parts.append(f"Is time user usually: {top}")

        # Mood pattern
        moods = self.patterns.get("mood_history", [])[-5:]
        if moods:
            recent_moods = [m["emotion"] for m in moods]
            common_mood = Counter(recent_moods).most_common(1)
            if common_mood:
                parts.append(f"User ka recent mood: mostly {common_mood[0][0]}")

        # Habits
        habits = self.patterns.get("user_habits", {})
        if habits.get("night_owl"):
            parts.append("User night owl hai (raat ko active)")
        if habits.get("morning_music"):
            parts.append("User subah music sunna pasand karta hai")

        # Total usage
        total = self.patterns.get("total_actions", {})
        if total:
            total_count = sum(total.values())
            parts.append(f"Total interactions: {total_count}")

        return "\n".join(parts) if parts else ""

    def get_suggestion(self) -> Optional[str]:
        """Get a proactive suggestion based on current time patterns."""
        hour = datetime.now().strftime("%H")
        hourly = self.patterns.get("hourly_actions", {}).get(hour, {})

        if not hourly:
            return None

        top_action = max(hourly, key=hourly.get)
        count = hourly[top_action]

        if count >= 3:
            suggestions = {
                "play_youtube": "Sun, tu is time usually YouTube chalata hai — kuch lagaun?",
                "get_weather": "Weather check karun? Tu roz is time puchta hai",
                "open_spotify": "Music lagaun? Tera usual time hai",
                "open_notepad": "Notepad kholu? Tu is time notes leta hai usually",
                "get_news": "News sunni hai? Roz is time dekhta hai tu",
                "spotify_mood": "Chill music lagaun? Tera mood time hai",
            }
            return suggestions.get(top_action)

        return None

    def get_stats(self) -> Dict[str, str]:
        """Get usage statistics."""
        total = self.patterns.get("total_actions", {})
        if not total:
            return {"status": "success", "message": "Abhi koi pattern nahi hai. Thoda use kar, seekh jaungi!"}

        top = sorted(total.items(), key=lambda x: x[1], reverse=True)[:5]
        lines = ["Tere top actions:"]
        for action, count in top:
            lines.append(f"  • {action}: {count} baar")

        queries = self.patterns.get("frequent_queries", [])
        if queries:
            common = Counter(queries).most_common(3)
            lines.append("\nFrequent searches:")
            for q, c in common:
                lines.append(f"  • '{q}' ({c} baar)")

        songs = self.patterns.get("favorite_songs", [])[-5:]
        if songs:
            lines.append(f"\nFav songs: {', '.join(songs)}")

        return {"status": "success", "message": "\n".join(lines)}
