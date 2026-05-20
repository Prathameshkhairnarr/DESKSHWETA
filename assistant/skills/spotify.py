"""
Spotify Deep Control for Shweta AI Desktop Assistant.

Hybrid approach:
1. Playback control → Spotify Desktop app via media keys (no Premium needed)
2. Search & Playlists → Spotify Web API via spotipy (needs SPOTIFY_CLIENT_ID/SECRET)
3. Mood-based playlists → Pre-defined + smart search

Setup:
- pip install spotipy
- Create app at https://developer.spotify.com/dashboard
- Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env
- Set redirect URI: http://localhost:8888/callback
"""

import logging
import os
import subprocess
import time
from typing import Dict, Optional

import pyautogui

logger = logging.getLogger(__name__)

# --- Spotify Desktop App Path ---
SPOTIFY_PATH = os.environ.get(
    "SPOTIFY_PATH",
    r"C:\Users\sai\AppData\Roaming\Spotify\Spotify.exe"
)

# --- Mood-based playlist mapping (Spotify URIs) ---
# These are popular public playlists — replace with your own if needed
MOOD_PLAYLISTS = {
    "happy": {
        "name": "Happy Hits",
        "query": "happy hits hindi bollywood",
        "uri": "spotify:playlist:37i9dQZF1DXdPec7aLTmlC",  # Happy Hits!
    },
    "sad": {
        "name": "Sad Songs",
        "query": "sad hindi songs heartbreak",
        "uri": "spotify:playlist:37i9dQZF1DX7gIoKXt0gmx",  # Sad Songs
    },
    "chill": {
        "name": "Chill Vibes",
        "query": "chill lofi relax study",
        "uri": "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6",  # Chill Hits
    },
    "coding": {
        "name": "Coding Mode",
        "query": "lofi coding focus beats",
        "uri": "spotify:playlist:37i9dQZF1DX5trt9i14X7j",  # Coding Mode
    },
    "workout": {
        "name": "Workout",
        "query": "workout gym motivation hindi",
        "uri": "spotify:playlist:37i9dQZF1DX76Wlfdnj7AP",  # Beast Mode
    },
    "party": {
        "name": "Party",
        "query": "party bollywood dance hits",
        "uri": "spotify:playlist:37i9dQZF1DX0XUfTFmNBRM",  # Bollywood Party
    },
    "romantic": {
        "name": "Romantic",
        "query": "romantic hindi love songs",
        "uri": "spotify:playlist:37i9dQZF1DX7gIoKXt0gmx",  # Romance
    },
    "focus": {
        "name": "Deep Focus",
        "query": "deep focus concentration instrumental",
        "uri": "spotify:playlist:37i9dQZF1DWZeKCadgRdKQ",  # Deep Focus
    },
    "sleep": {
        "name": "Sleep",
        "query": "sleep calm peaceful night",
        "uri": "spotify:playlist:37i9dQZF1DWZd79rJ6a7lp",  # Sleep
    },
}

# --- Spotipy client (lazy init) ---
_sp_client = None
_sp_available = False


def _init_spotipy():
    """Initialize Spotipy client with OAuth (lazy, one-time)."""
    global _sp_client, _sp_available

    if _sp_client is not None:
        return _sp_available

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            logger.info("[Spotify] No API keys — using desktop control only.")
            _sp_available = False
            return False

        scope = (
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing "
            "playlist-read-private "
            "playlist-read-collaborative"
        )

        _sp_client = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=scope,
            cache_path=os.path.join(os.path.dirname(__file__), "..", "..", ".spotify_cache"),
            open_browser=True,
        ))
        _sp_available = True
        logger.info("[Spotify] API connected!")
        return True

    except ImportError:
        logger.warning("[Spotify] spotipy not installed. Using desktop control only.")
        _sp_available = False
        return False
    except Exception as e:
        logger.warning(f"[Spotify] Init failed: {e}")
        _sp_available = False
        return False


# ============================================================
# DESKTOP CONTROL (works without Premium/API)
# ============================================================

def _ensure_spotify_open() -> bool:
    """Make sure Spotify desktop app is running."""
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            if "spotify" in win.title.lower():
                return True
    except Exception:
        pass

    # Try to open Spotify
    try:
        if os.path.exists(SPOTIFY_PATH):
            subprocess.Popen([SPOTIFY_PATH])
            time.sleep(3)
            return True
        else:
            # Try via Start Menu
            subprocess.Popen(["cmd", "/c", "start", "spotify:"], shell=True)
            time.sleep(3)
            return True
    except Exception as e:
        logger.error(f"Cannot open Spotify: {e}")
        return False


def _focus_spotify() -> bool:
    """Bring Spotify window to foreground."""
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            if "spotify" in win.title.lower() and win.title.strip():
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.3)
                return True
    except Exception:
        pass
    return False


def spotify_play_pause() -> Dict[str, str]:
    """Toggle play/pause on Spotify."""
    try:
        # Try API first
        if _init_spotipy() and _sp_client:
            try:
                playback = _sp_client.current_playback()
                if playback and playback.get("is_playing"):
                    _sp_client.pause_playback()
                    return {"status": "success", "message": "Spotify pause kar diya."}
                else:
                    _sp_client.start_playback()
                    return {"status": "success", "message": "Spotify play kar diya."}
            except Exception:
                pass

        # Fallback: media key
        pyautogui.press("playpause")
        return {"status": "success", "message": "Play/Pause toggled."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_next() -> Dict[str, str]:
    """Skip to next track."""
    try:
        if _init_spotipy() and _sp_client:
            try:
                _sp_client.next_track()
                time.sleep(0.5)
                track = _get_current_track()
                if track:
                    return {"status": "success", "message": f"Next: {track}"}
            except Exception:
                pass

        pyautogui.press("nexttrack")
        return {"status": "success", "message": "Next track."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_previous() -> Dict[str, str]:
    """Go to previous track."""
    try:
        if _init_spotipy() and _sp_client:
            try:
                _sp_client.previous_track()
                time.sleep(0.5)
                track = _get_current_track()
                if track:
                    return {"status": "success", "message": f"Previous: {track}"}
            except Exception:
                pass

        pyautogui.press("prevtrack")
        return {"status": "success", "message": "Previous track."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_now_playing() -> Dict[str, str]:
    """Get currently playing track info."""
    try:
        if _init_spotipy() and _sp_client:
            playback = _sp_client.current_playback()
            if playback and playback.get("item"):
                item = playback["item"]
                name = item.get("name", "Unknown")
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                is_playing = "▶️" if playback.get("is_playing") else "⏸️"
                progress_ms = playback.get("progress_ms", 0)
                duration_ms = item.get("duration_ms", 0)
                progress = f"{progress_ms // 60000}:{(progress_ms // 1000) % 60:02d}"
                duration = f"{duration_ms // 60000}:{(duration_ms // 1000) % 60:02d}"
                return {
                    "status": "success",
                    "message": f"{is_playing} {name} — {artists} ({progress}/{duration})"
                }
            else:
                return {"status": "success", "message": "Kuch nahi chal raha Spotify pe."}

        # Without API — try window title
        try:
            import pygetwindow as gw
            for win in gw.getAllWindows():
                if "spotify" in win.title.lower() and " - " in win.title:
                    return {"status": "success", "message": f"▶️ {win.title}"}
        except Exception:
            pass

        return {"status": "success", "message": "Spotify info available nahi hai. API keys set karo."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_play_song(query: str) -> Dict[str, str]:
    """Search and play a specific song on Spotify."""
    try:
        if _init_spotipy() and _sp_client:
            results = _sp_client.search(q=query, type="track", limit=1)
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                track = tracks[0]
                name = track["name"]
                artist = track["artists"][0]["name"]
                uri = track["uri"]
                try:
                    _sp_client.start_playback(uris=[uri])
                    return {"status": "success", "message": f"Playing: {name} — {artist}"}
                except Exception:
                    # Premium required — open in Spotify app
                    _open_spotify_uri(uri)
                    time.sleep(2)
                    return {"status": "success", "message": f"Opening: {name} — {artist}"}
            else:
                return {"status": "error", "message": f"'{query}' nahi mila Spotify pe."}

        # Without API — search on YouTube instead
        from assistant.skills.browser import play_youtube
        return play_youtube(query)
    except Exception as e:
        # Final fallback — YouTube
        try:
            from assistant.skills.browser import play_youtube
            return play_youtube(query)
        except Exception:
            return {"status": "error", "message": str(e)}


def spotify_play_playlist(playlist_name: str) -> Dict[str, str]:
    """Play a playlist by name or mood."""
    try:
        # Check mood playlists first
        mood_key = playlist_name.lower().strip()
        mood_match = MOOD_PLAYLISTS.get(mood_key)

        if mood_match:
            return _play_mood_playlist(mood_match)

        # Search for playlist by name via API
        if _init_spotipy() and _sp_client:
            results = _sp_client.search(q=playlist_name, type="playlist", limit=1)
            playlists = results.get("playlists", {}).get("items", [])
            if playlists:
                pl = playlists[0]
                name = pl["name"]
                uri = pl["uri"]
                try:
                    _sp_client.start_playback(context_uri=uri)
                    return {"status": "success", "message": f"Playing playlist: {name}"}
                except Exception:
                    # Premium required — open URI in app
                    _open_spotify_uri(uri)
                    time.sleep(2)
                    return {"status": "success", "message": f"Opening playlist: {name}"}

        # Fallback: play on YouTube
        from assistant.skills.browser import play_youtube
        return play_youtube(f"{playlist_name} playlist")
    except Exception as e:
        # Final fallback — YouTube
        try:
            from assistant.skills.browser import play_youtube
            return play_youtube(f"{playlist_name} playlist")
        except Exception:
            return {"status": "error", "message": str(e)}


def spotify_mood(mood: str) -> Dict[str, str]:
    """Play music based on mood."""
    mood_lower = mood.lower().strip()

    # Map common mood words to playlist keys
    mood_map = {
        "happy": "happy", "khush": "happy", "mast": "happy", "party": "party",
        "sad": "sad", "dukhi": "sad", "udaas": "sad", "heartbreak": "sad",
        "chill": "chill", "relax": "chill", "calm": "chill", "shanti": "chill",
        "coding": "coding", "code": "coding", "programming": "coding", "focus": "focus",
        "workout": "workout", "gym": "workout", "exercise": "workout",
        "romantic": "romantic", "love": "romantic", "pyaar": "romantic",
        "sleep": "sleep", "neend": "sleep", "sone": "sleep",
        "study": "focus", "padhai": "focus", "concentrate": "focus",
    }

    playlist_key = mood_map.get(mood_lower, "chill")
    mood_data = MOOD_PLAYLISTS.get(playlist_key, MOOD_PLAYLISTS["chill"])

    return _play_mood_playlist(mood_data)


def spotify_volume(percent: int) -> Dict[str, str]:
    """Set Spotify volume (0-100)."""
    try:
        percent = max(0, min(100, int(percent)))
        if _init_spotipy() and _sp_client:
            try:
                _sp_client.volume(percent)
                return {"status": "success", "message": f"Spotify volume {percent}% set."}
            except Exception:
                pass

        # Fallback: system volume
        return {"status": "success", "message": "Spotify volume API ke bina set nahi ho sakta. System volume use karo."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_shuffle(on: bool = True) -> Dict[str, str]:
    """Toggle shuffle mode."""
    try:
        if _init_spotipy() and _sp_client:
            _sp_client.shuffle(on)
            state = "ON" if on else "OFF"
            return {"status": "success", "message": f"Shuffle {state}."}

        return {"status": "error", "message": "Shuffle ke liye Spotify API chahiye."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def spotify_repeat(mode: str = "track") -> Dict[str, str]:
    """Set repeat mode: track, context (playlist), off."""
    try:
        if _init_spotipy() and _sp_client:
            _sp_client.repeat(mode)
            return {"status": "success", "message": f"Repeat: {mode}."}

        return {"status": "error", "message": "Repeat ke liye Spotify API chahiye."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# HELPERS
# ============================================================

def _get_current_track() -> Optional[str]:
    """Get current track name (API only)."""
    try:
        if _sp_client:
            playback = _sp_client.current_playback()
            if playback and playback.get("item"):
                item = playback["item"]
                return f"{item['name']} — {item['artists'][0]['name']}"
    except Exception:
        pass
    return None


def _play_mood_playlist(mood_data: dict) -> Dict[str, str]:
    """Play a mood-based playlist."""
    try:
        # Try API playback first
        if _init_spotipy() and _sp_client:
            try:
                _sp_client.start_playback(context_uri=mood_data["uri"])
                _sp_client.shuffle(True)
                return {"status": "success", "message": f"Playing: {mood_data['name']} 🎵"}
            except Exception:
                pass

        # Fallback: open URI in Spotify app
        _open_spotify_uri(mood_data["uri"])
        return {"status": "success", "message": f"Opening: {mood_data['name']} 🎵"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _open_spotify_uri(uri: str) -> None:
    """Open a Spotify URI in the desktop app."""
    try:
        subprocess.Popen(["cmd", "/c", "start", "", uri], shell=True)
    except Exception:
        try:
            os.startfile(uri)
        except Exception:
            pass
