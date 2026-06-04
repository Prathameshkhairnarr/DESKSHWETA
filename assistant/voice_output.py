"""
Voice Output with TTS Cache + Real-time Lip Sync.

OPTIMIZED v2.0:
- Interruptible playback (stop current audio, start new immediately)
- Edge-TTS with 6s timeout + 1 retry before pyttsx3 fallback
- LRU cache with size limit (max 500 files / 100MB)
- Cache integrity check (skip corrupt/empty files)
- Lip sync thread as daemon with exception handling + timeout join
- Pre-cache with per-phrase timeout (5s max, non-blocking)
- Proper resource cleanup (temp files, audio device)
- No artificial delays on success path

Flow:
1. On startup: pre-generate MP3 for 22 common phrases (background, non-blocking)
2. On speak(): check cache (instant) → edge-tts (with timeout) → pyttsx3
3. Audio playback via winsound with real-time lip sync at 30fps
4. Interruptible: new speak() stops current audio immediately
"""

import asyncio
import hashlib
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# --- Voice Configuration ---
VOICE_PRIMARY = "en-IN-NeerjaNeural"
VOICE_FALLBACK = "hi-IN-SwaraNeural"
RATE = "+35%"

# --- Cache Configuration ---
CACHE_DIR = PROJECT_ROOT / "cache" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_MAX_FILES = 500          # Max cached MP3 files
CACHE_MAX_SIZE_MB = 100        # Max total cache size in MB
CACHE_MIN_FILE_SIZE = 500      # Minimum valid MP3 size in bytes
AUTO_CACHE_MAX_LEN = 40        # Max text length to auto-cache
EDGE_TTS_TIMEOUT = 6           # Seconds before falling back to pyttsx3
PRECACHE_PHRASE_TIMEOUT = 5    # Max seconds per phrase during pre-cache

# Lock for thread-safe cache access
_cache_lock = threading.Lock()

# Pre-defined phrases to cache at startup
CACHE_PHRASES = [
    "theek hai", "ho gaya", "ji haan", "nahi kar sakta",
    "samajh nahi aaya", "ek second", "koshish kar raha hoon",
    "done", "sorry, kuch gadbad ho gayi", "haan bolo",
    "file mil gayi", "file nahi mili", "app open kar diya",
    "volume badha diya", "volume kam kar diya", "screenshot le liya",
    "timer set ho gaya", "reminder set ho gaya", "note save ho gaya",
    "shweta sun rahi hoon", "band kar diya", "chal raha hoon",
]


# ============================================================
# Cache Utilities
# ============================================================

def _text_to_cache_path(text: str) -> Path:
    """Convert text to its cache file path using MD5 hash."""
    normalized = text.lower().strip()
    md5 = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{md5}.mp3"


def _is_cached(text: str) -> Optional[Path]:
    """Check if text has a valid cached MP3. Returns path or None."""
    path = _text_to_cache_path(text)
    with _cache_lock:
        if path.exists():
            size = path.stat().st_size
            if size > CACHE_MIN_FILE_SIZE:
                # Update access time for LRU tracking
                try:
                    os.utime(path, None)
                except OSError:
                    pass
                return path
            else:
                # Corrupt/empty file — delete it
                try:
                    path.unlink()
                except OSError:
                    pass
    return None


def _save_to_cache(text: str, mp3_path: str) -> None:
    """Copy an MP3 file into the cache with LRU eviction."""
    try:
        cache_path = _text_to_cache_path(text)
        with _cache_lock:
            if not cache_path.exists():
                # Check if we need to evict
                _evict_if_needed()
                shutil.copy2(mp3_path, str(cache_path))
    except Exception as e:
        logger.debug(f"[Cache] Save failed: {e}")


def _evict_if_needed() -> None:
    """LRU eviction: remove oldest files if cache exceeds limits."""
    try:
        files = list(CACHE_DIR.glob("*.mp3"))
        if len(files) < CACHE_MAX_FILES:
            # Check size
            total_size = sum(f.stat().st_size for f in files)
            if total_size < CACHE_MAX_SIZE_MB * 1024 * 1024:
                return

        # Sort by access time (oldest first)
        files.sort(key=lambda f: f.stat().st_atime)

        # Remove oldest 20% to avoid frequent eviction
        remove_count = max(1, len(files) // 5)
        for f in files[:remove_count]:
            try:
                f.unlink()
            except OSError:
                pass

        logger.info(f"[Cache] Evicted {remove_count} old files.")
    except Exception as e:
        logger.debug(f"[Cache] Eviction error: {e}")


def _get_cache_stats() -> dict:
    """Get cache statistics."""
    try:
        files = list(CACHE_DIR.glob("*.mp3"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "files": len(files),
            "size_mb": round(total_size / (1024 * 1024), 1),
            "max_files": CACHE_MAX_FILES,
            "max_size_mb": CACHE_MAX_SIZE_MB,
        }
    except Exception:
        return {"files": 0, "size_mb": 0}


# ============================================================
# Pre-cache at startup (background, non-blocking)
# ============================================================

def prebuild_cache() -> None:
    """Pre-generate MP3 for common phrases. Per-phrase timeout. Non-blocking."""
    try:
        import edge_tts
    except ImportError:
        logger.warning("[TTS Cache] edge_tts not installed, skipping pre-cache.")
        return

    to_generate = [p for p in CACHE_PHRASES if not _is_cached(p)]

    if not to_generate:
        logger.info("[TTS Cache] All phrases already cached. Ready.")
        return

    logger.info(f"[TTS Cache] Generating {len(to_generate)} phrases...")

    async def _generate_one(phrase: str):
        cache_path = _text_to_cache_path(phrase)
        try:
            comm = edge_tts.Communicate(phrase, VOICE_PRIMARY, rate=RATE)
            await asyncio.wait_for(comm.save(str(cache_path)), timeout=PRECACHE_PHRASE_TIMEOUT)
            if cache_path.exists() and cache_path.stat().st_size > CACHE_MIN_FILE_SIZE:
                return
        except asyncio.TimeoutError:
            logger.debug(f"[TTS Cache] Timeout for '{phrase}', skipping.")
        except Exception:
            pass
        # Try fallback voice
        try:
            comm = edge_tts.Communicate(phrase, VOICE_FALLBACK, rate=RATE)
            await asyncio.wait_for(comm.save(str(cache_path)), timeout=PRECACHE_PHRASE_TIMEOUT)
        except Exception:
            pass

    async def _generate_all():
        for i in range(0, len(to_generate), 5):
            batch = to_generate[i:i+5]
            tasks = [_generate_one(p) for p in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_generate_all())
        loop.close()
        logger.info("[TTS Cache] Ready.")
    except Exception as e:
        logger.warning(f"[TTS Cache] Pre-generation failed: {e}")


def _start_cache_warmup() -> None:
    """Start cache pre-generation in background (non-blocking, daemon)."""
    thread = threading.Thread(target=prebuild_cache, daemon=True, name="TTS-PreCache")
    thread.start()


# ============================================================
# Main Voice Output Class
# ============================================================

class VoiceOutput:
    """
    Voice output with TTS cache + real-time lip sync.
    Interruptible: new speak() stops current audio immediately.
    """

    def __init__(self) -> None:
        self.is_speaking: bool = False
        self._speak_lock = threading.Lock()
        self._interrupt_event = threading.Event()
        self._edge_available: bool = False
        self._soundfile_available: bool = False
        self._sounddevice_available: bool = False
        self._lip_sync_callback: Optional[Callable] = None
        self._current_thread: Optional[threading.Thread] = None

        try:
            import edge_tts
            self._edge_available = True
            logger.info("Edge-TTS initialized — using natural neural voices (FREE).")
        except ImportError:
            logger.warning("edge_tts not installed. Using pyttsx3 only.")

        try:
            import soundfile
            self._soundfile_available = True
        except ImportError:
            logger.warning("soundfile not available — lip sync will use fallback.")

        try:
            import sounddevice
            self._sounddevice_available = True
        except ImportError:
            logger.warning("sounddevice not available for playback.")

        # Start cache warmup in background (non-blocking)
        _start_cache_warmup()

    def set_lip_sync_callback(self, callback: Callable) -> None:
        """Set callback for lip sync. Called with volume (0.0-1.0) at ~30fps."""
        self._lip_sync_callback = callback

    def speak(self, text: str, language: Optional[str] = None,
              voice: Optional[str] = None, callback: Optional[Callable] = None) -> None:
        """
        Speak text. Interrupts any current speech first.
        Checks cache (instant) → edge-tts (with timeout) → pyttsx3.
        """
        if not text:
            if callback:
                callback()
            return

        # Interrupt current speech if any
        self._interrupt()

        thread = threading.Thread(
            target=self._speak_thread,
            args=(text, callback, voice),
            daemon=True,
            name="TTS-Speak"
        )
        self._current_thread = thread
        thread.start()

    def stop(self) -> None:
        """Stop speaking immediately."""
        self._interrupt()

    def speak_reaction(self, text: str, intensity: str = "normal") -> None:
        """Speak reaction with Edge-TTS custom rate. No ElevenLabs."""
        if not text:
            return
        self._interrupt()
        thread = threading.Thread(
            target=self._speak_reaction_impl,
            args=(text, intensity),
            daemon=True,
            name="TTS-Reaction"
        )
        self._current_thread = thread
        thread.start()

    def _speak_reaction_impl(self, text: str, intensity: str) -> None:
        """Speak reaction — Edge-TTS with fast rate → pyttsx3 fallback."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            if self._edge_available:
                if intensity == "normal":
                    if text.isupper() or text.startswith("AAA"):
                        intensity = "screaming"
                    elif any(w in text.upper() for w in ["ARRE", "BHAI", "RUKO"]):
                        intensity = "panicking"
                    elif "..." in text:
                        intensity = "exhausted"
                rate_map = {"calm": "+15%", "normal": "+35%", "surprised": "+50%",
                            "panicking": "+65%", "screaming": "+80%", "exhausted": "+5%", "relieved": "+20%"}
                rate = rate_map.get(intensity, "+35%")
                if self._speak_edge_rate(text, rate):
                    return
            self._speak_pyttsx3(text)
        except Exception:
            try:
                self._speak_pyttsx3(text)
            except Exception:
                pass
        finally:
            self.is_speaking = False
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass

    def _speak_edge_rate(self, text: str, rate: str) -> bool:
        """Edge-TTS with custom rate."""
        import edge_tts
        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                comm = edge_tts.Communicate(text, VOICE_PRIMARY, rate=rate)
                loop.run_until_complete(asyncio.wait_for(comm.save(tmp_path), timeout=EDGE_TTS_TIMEOUT))
            finally:
                loop.close()
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                self._play_with_lip_sync(tmp_path)
                return True
        except Exception as e:
            logger.debug(f"[TTS] Reaction edge failed: {e}")
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
        return False

    def _interrupt(self) -> None:
        """Signal current speech to stop."""
        if self.is_speaking:
            self._interrupt_event.set()
            self.is_speaking = False
            if self._current_thread and self._current_thread.is_alive():
                self._current_thread.join(timeout=0.5)
            self._interrupt_event.clear()
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass

    def _speak_thread(self, text: str, callback: Optional[Callable],
                      voice: Optional[str] = None) -> None:
        """Internal speak thread — cache → edge-tts (with retry) → pyttsx3."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            text = self._add_natural_pauses(text)
            cached_path = _is_cached(text) if not voice else None
            if cached_path:
                self._play_with_lip_sync(str(cached_path))
            elif self._edge_available:
                if not self._speak_edge_with_retry(text, voice):
                    self._speak_pyttsx3(text)
            else:
                self._speak_pyttsx3(text)
        except Exception as e:
            logger.error(f"TTS error: {e}")
            try:
                self._speak_pyttsx3(text)
            except Exception:
                pass
        finally:
            self.is_speaking = False
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass
            if callback:
                callback()

    def _speak_edge_with_retry(self, text: str, voice: Optional[str] = None) -> bool:
        """Generate audio with edge-tts. Retry once on failure."""
        import edge_tts
        target_voice = voice or VOICE_PRIMARY
        tmp_path = tempfile.mktemp(suffix=".mp3")
        for attempt in range(2):
            if self._interrupt_event.is_set():
                return True
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    use_voice = target_voice if attempt == 0 else VOICE_FALLBACK
                    comm = edge_tts.Communicate(text, use_voice, rate=RATE)
                    loop.run_until_complete(asyncio.wait_for(comm.save(tmp_path), timeout=EDGE_TTS_TIMEOUT))
                finally:
                    loop.close()
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    self._play_with_lip_sync(tmp_path)
                    if not voice and len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, tmp_path)
                    return True
            except asyncio.TimeoutError:
                logger.warning(f"[TTS] Edge-TTS timeout (attempt {attempt+1})")
            except Exception as e:
                logger.warning(f"[TTS] Edge-TTS failed (attempt {attempt+1}): {e}")
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass
            if attempt == 0:
                time.sleep(1.0)
        return False

    def _add_natural_pauses(self, text: str) -> str:
        """Add natural speech pauses for more human-like TTS."""
        text = text.replace(", ", "... ")
        text = text.replace("! ", "!... ")
        text = text.replace("? ", "?... ")
        for word in [" toh ", " lekin ", " par ", " aur "]:
            text = text.replace(word, f"...{word}")
        return text

    def _play_with_lip_sync(self, mp3_path: str) -> None:
        """
        Speak using ElevenLabs API (most emotional TTS).
        Uses Aria voice — expressive young female.
        Returns True if successful.
        """
        import requests as req

        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            # Try loading from .env
            try:
                from config import PROJECT_ROOT
                env_file = PROJECT_ROOT / ".env"
                if env_file.exists():
                    for line in env_file.read_text().splitlines():
                        if line.startswith("ELEVENLABS_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass

        if not api_key:
            return False

        # Hindi female voice — expressive, emotional
        # "Indian Hindi Voice" from ElevenLabs library
        voice_id = "2F1KINpxsttim2WfMbVs"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.3,        # Low = more expressive/dramatic
                "similarity_boost": 0.75,
                "style": 0.8,            # High = more emotional style
                "use_speaker_boost": True,
            }
        }

        tmp_path = tempfile.mktemp(suffix=".mp3")

        try:
            resp = req.post(url, headers=headers, json=payload, timeout=6)

            if resp.status_code == 200:
                with open(tmp_path, "wb") as f:
                    f.write(resp.content)

                if os.path.getsize(tmp_path) > 500:
                    self._play_with_lip_sync(tmp_path)
                    logger.info(f"[TTS] ElevenLabs reaction: '{text[:30]}...'")
                    return True

            elif resp.status_code == 401:
                logger.warning("[TTS] ElevenLabs API key invalid.")
            elif resp.status_code == 429:
                logger.info("[TTS] ElevenLabs quota exceeded, using Edge-TTS.")
            else:
                logger.debug(f"[TTS] ElevenLabs HTTP {resp.status_code}")

        except req.Timeout:
            logger.debug("[TTS] ElevenLabs timeout.")
        except Exception as e:
            logger.debug(f"[TTS] ElevenLabs error: {e}")
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

        return False

    def _interrupt(self) -> None:
        """Signal current speech to stop."""
        if self.is_speaking:
            self._interrupt_event.set()
            self.is_speaking = False
            # Give current thread a moment to notice
            if self._current_thread and self._current_thread.is_alive():
                self._current_thread.join(timeout=0.5)
            self._interrupt_event.clear()
            # Close mouth
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass

    def _speak_thread(self, text: str, callback: Optional[Callable],
                      voice: Optional[str] = None) -> None:
        """Internal speak thread — cache → edge-tts (with retry) → pyttsx3."""
        self.is_speaking = True
        self._interrupt_event.clear()

        try:
            text = self._add_natural_pauses(text)

            # STEP 1: Check cache (instant playback) — skip if custom voice
            cached_path = _is_cached(text) if not voice else None
            if cached_path:
                self._play_with_lip_sync(str(cached_path))
            elif self._edge_available:
                # STEP 2: Edge-TTS with timeout + 1 retry
                if not self._speak_edge_with_retry(text, voice):
                    # STEP 3: Fallback to pyttsx3
                    self._speak_pyttsx3(text)
            else:
                # No Edge-TTS available
                self._speak_pyttsx3(text)

        except Exception as e:
            logger.error(f"TTS error: {e}")
            try:
                self._speak_pyttsx3(text)
            except Exception:
                pass
        finally:
            self.is_speaking = False
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass
            if callback:
                callback()

    def _speak_edge_with_retry(self, text: str, voice: Optional[str] = None) -> bool:
        """
        Generate audio with edge-tts. Retry once on failure.
        Hard timeout: EDGE_TTS_TIMEOUT seconds.
        Returns True if successful, False if should fallback to pyttsx3.
        """
        import edge_tts

        target_voice = voice or VOICE_PRIMARY
        tmp_path = tempfile.mktemp(suffix=".mp3")

        for attempt in range(2):  # Max 2 attempts
            if self._interrupt_event.is_set():
                return True  # Interrupted, don't fallback

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    use_voice = target_voice if attempt == 0 else VOICE_FALLBACK
                    comm = edge_tts.Communicate(text, use_voice, rate=RATE)
                    loop.run_until_complete(
                        asyncio.wait_for(comm.save(tmp_path), timeout=EDGE_TTS_TIMEOUT)
                    )
                finally:
                    loop.close()

                # Verify file is valid
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    # Play it
                    self._play_with_lip_sync(tmp_path)

                    # Auto-cache short phrases (default voice only)
                    if not voice and len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, tmp_path)

                    return True

            except asyncio.TimeoutError:
                logger.warning(f"[TTS] Edge-TTS timeout (attempt {attempt+1})")
            except Exception as e:
                logger.warning(f"[TTS] Edge-TTS failed (attempt {attempt+1}): {e}")
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass

            # Only retry once with backoff (1s) — only on failure path
            if attempt == 0:
                time.sleep(1.0)

        return False  # Both attempts failed

    def _add_natural_pauses(self, text: str) -> str:
        """Add natural speech pauses for more human-like TTS."""
        text = text.replace(", ", "... ")
        text = text.replace("! ", "!... ")
        text = text.replace("? ", "?... ")
        for word in [" toh ", " lekin ", " par ", " aur "]:
            text = text.replace(word, f"...{word}")
        return text

    def _play_with_lip_sync(self, mp3_path: str) -> None:
        """
        Play MP3 file with real-time lip sync analysis.
        Interruptible via _interrupt_event.
        Uses sounddevice for playback + parallel RMS analysis at 30fps.
        Falls back to winsound if sounddevice unavailable.
        """
        if self._interrupt_event.is_set():
            return

        try:
            if self._soundfile_available and self._sounddevice_available:
                self._play_sounddevice(mp3_path)
            else:
                self._play_winsound(mp3_path)
        except Exception as e:
            logger.warning(f"[TTS] Playback error, trying winsound: {e}")
            try:
                self._play_winsound(mp3_path)
            except Exception as e2:
                logger.error(f"[TTS] All playback failed: {e2}")

    def _play_sounddevice(self, mp3_path: str) -> None:
        """Play via sounddevice with real-time lip sync."""
        import soundfile as sf
        import sounddevice as sd_play

        try:
            data, samplerate = sf.read(mp3_path, dtype='float32')
        except Exception as e:
            logger.warning(f"[TTS] Cannot decode MP3: {e}, trying winsound")
            self._play_winsound(mp3_path)
            return

        if self._interrupt_event.is_set():
            return

        # Mono conversion if stereo
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        # Start playback (non-blocking)
        try:
            sd_play.play(data, samplerate, blocking=False)
        except Exception as e:
            logger.warning(f"[TTS] sounddevice play failed: {e}")
            self._play_winsound(mp3_path)
            return

        # Lip sync analysis at ~30fps while audio plays
        if self._lip_sync_callback:
            self._run_lip_sync(data, samplerate)
        else:
            # No lip sync — just wait for playback to finish
            duration = len(data) / samplerate
            self._wait_interruptible(duration)

        # Stop playback (in case of interrupt)
        try:
            sd_play.stop()
        except Exception:
            pass

    def _run_lip_sync(self, data: np.ndarray, samplerate: int) -> None:
        """
        Analyze RMS amplitude at 30fps and send to lip sync callback.
        Runs in current thread (already in background speak thread).
        Interruptible via _interrupt_event.
        """
        fps = 30
        frame_samples = samplerate // fps
        total_frames = len(data) // frame_samples
        frame_duration = 1.0 / fps

        # Pre-compute RMS for all frames
        rms_values = []
        for i in range(total_frames):
            start = i * frame_samples
            end = start + frame_samples
            frame = data[start:end]
            rms = np.sqrt(np.mean(frame ** 2))
            rms_values.append(rms)

        # Normalize RMS values
        max_rms = max(rms_values) if rms_values else 1.0
        if max_rms < 0.001:
            max_rms = 1.0

        # Play frames in real-time
        start_time = time.time()
        for i, rms in enumerate(rms_values):
            if self._interrupt_event.is_set():
                break

            # Normalize to 0.0-1.0 range
            volume = min(1.0, (rms / max_rms) * 1.5)

            # Apply threshold (ignore very quiet)
            if volume < 0.05:
                volume = 0.0

            # Smooth (simple low-pass)
            try:
                self._lip_sync_callback(volume)
            except Exception:
                break

            # Wait for next frame (sync with real-time playback)
            target_time = start_time + (i + 1) * frame_duration
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                # Use interrupt event wait instead of time.sleep for responsiveness
                if self._interrupt_event.wait(timeout=sleep_time):
                    break

        # Close mouth
        if self._lip_sync_callback:
            try:
                self._lip_sync_callback(0.0)
            except Exception:
                pass

    def _play_winsound(self, mp3_path: str) -> None:
        """
        Fallback playback via subprocess (ffplay/mpv) or winsound.
        winsound only supports WAV, so we convert or use alternative.
        """
        if self._interrupt_event.is_set():
            return

        try:
            # Try using Windows Media Player COM or subprocess
            # winsound.PlaySound only works with WAV, so use subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

            # Try ffplay (comes with ffmpeg)
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path],
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for playback, checking for interrupt
            while proc.poll() is None:
                if self._interrupt_event.is_set():
                    proc.terminate()
                    return
                time.sleep(0.1)

        except FileNotFoundError:
            # ffplay not available — try powershell
            try:
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command",
                     f'(New-Object Media.SoundPlayer "{mp3_path}").PlaySync()'],
                    startupinfo=startupinfo,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                while proc.poll() is None:
                    if self._interrupt_event.is_set():
                        proc.terminate()
                        return
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"[TTS] winsound fallback failed: {e}")
        except Exception as e:
            logger.error(f"[TTS] Playback subprocess error: {e}")

    def _wait_interruptible(self, duration: float) -> None:
        """Wait for duration, but break immediately if interrupted."""
        self._interrupt_event.wait(timeout=duration)

    def _speak_pyttsx3(self, text: str) -> None:
        """Offline TTS fallback using pyttsx3."""
        if self._interrupt_event.is_set():
            return

        try:
            import pyttsx3
            engine = pyttsx3.init()

            # Match Edge-TTS settings as closely as possible
            engine.setProperty('rate', 200)  # ~+35% from default 150
            engine.setProperty('volume', 0.9)

            # Try to use a female voice
            voices = engine.getProperty('voices')
            for v in voices:
                if 'female' in v.name.lower() or 'zira' in v.name.lower():
                    engine.setProperty('voice', v.id)
                    break

            engine.say(text)
            engine.runAndWait()
            engine.stop()

        except Exception as e:
            logger.error(f"[TTS] pyttsx3 failed: {e}")

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        try:
            self._interrupt()
        except Exception:
            pass
