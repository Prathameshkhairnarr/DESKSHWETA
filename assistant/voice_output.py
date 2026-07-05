"""
Voice Output with TTS Cache + Real-time Lip Sync.

PRODUCTION v3.0:
- Sarvam AI TTS as PRIMARY voice (real Indian female voice via bulbul:v3)
- Edge-TTS as FALLBACK (if Sarvam fails or no API key)
- pyttsx3 as LAST RESORT offline fallback
- Interruptible playback (stop current audio, start new immediately)
- LRU cache with size limit (max 500 files / 100MB)
- Cache integrity check (skip corrupt/empty files)
- Lip sync thread as daemon with exception handling + timeout join
- Pre-cache with per-phrase timeout (5s max, non-blocking)
- Proper resource cleanup (temp files, audio device)
- No artificial delays on success path

Flow:
1. On startup: pre-generate MP3 for 22 common phrases (background, non-blocking)
2. On speak(): check cache (instant) → Sarvam AI → edge-tts (with timeout) → pyttsx3
3. Audio playback via sounddevice with real-time lip sync at 30fps
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
VOICE_PRIMARY = "en-IN-NeerjaNeural"   # Edge-TTS primary (fallback)
VOICE_FALLBACK = "hi-IN-SwaraNeural"   # Edge-TTS fallback
RATE = "+35%"

# --- Sarvam AI TTS Configuration (PRIMARY) ---
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_MODEL = "bulbul:v3"             # Best Indian language TTS model
SARVAM_SPEAKER = "ritu"                # Fast/Energetic Female Hindi voice
SARVAM_LANGUAGE = "hi-IN"              # Hindi (supports en-IN, ta-IN, te-IN, etc.)
SARVAM_TIMEOUT = 8                     # Seconds before falling back to Edge-TTS
SARVAM_PACE = 1.15                     # Slightly faster than default for natural feel

# --- Amazon Polly TTS Configuration (Premium Free Tier) ---
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
POLLY_VOICE_ID = "Kajal"               # Indian Female Neural Voice (hi-IN)
POLLY_ENGINE = "neural"                # High-quality neural engine

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
    # Don't pre-cache with Edge-TTS if we are using Sarvam (we don't want mixed voices)
    if SARVAM_API_KEY:
        logger.info("[TTS Cache] Sarvam AI active. Skipping Edge-TTS pre-cache.")
        return

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
        self._sarvam_available: bool = False
        self._edge_available: bool = False
        self._soundfile_available: bool = False
        self._sounddevice_available: bool = False
        self._lip_sync_callback: Optional[Callable] = None
        self._current_thread: Optional[threading.Thread] = None

        # --- Sarvam AI TTS (PRIMARY — real Indian voice) ---
        if SARVAM_API_KEY:
            try:
                from sarvamai import SarvamAI
                self._sarvam_client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
                self._sarvam_available = True
                logger.info(f"[TTS] ✅ Sarvam AI initialized — using '{SARVAM_SPEAKER}' voice (PRIMARY).")
            except ImportError:
                logger.warning("[TTS] sarvamai SDK not installed. Run: pip install sarvamai")
                self._sarvam_client = None
            except Exception as e:
                logger.warning(f"[TTS] Sarvam AI init failed: {e}")
                self._sarvam_client = None
        
        self._polly_client = None
        self._polly_available = False
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_REGION:
            try:
                import boto3
                self._polly_client = boto3.client(
                    "polly",
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION
                )
                self._polly_available = True
                logger.info(f"[TTS] Amazon Polly initialized — using '{POLLY_VOICE_ID}' voice (PRIMARY).")
            except Exception as e:
                logger.warning(f"[TTS] Polly init failed: {e}")

        # --- Edge TTS (FALLBACK - free, neural voices) ---
        try:
            import edge_tts
            self._edge_available = False  # TEMPORARILY DISABLED
            logger.info("[TTS] Edge-TTS initialized but temporarily disabled.")
        except ImportError:
            logger.warning("[TTS] edge_tts not installed. Using pyttsx3 only.")

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
        Priority: cache (instant) → Sarvam AI → Edge-TTS → pyttsx3.
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
        """Speak reaction — Sarvam AI (with custom pace) → Polly → Edge-TTS → pyttsx3."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            # Try Sarvam AI first
            if self._sarvam_available:
                # Adjust pace based on intensity
                pace_map = {"calm": 1.0, "normal": SARVAM_PACE, "surprised": 1.35,
                            "panicking": 1.45, "screaming": 1.5, "exhausted": 0.9, "relieved": 1.1}
                custom_pace = pace_map.get(intensity, SARVAM_PACE)
                
                # Check text for implicit intensity
                if intensity == "normal":
                    if text.isupper() or text.startswith("AAA"):
                        custom_pace = 1.5
                    elif any(w in text.upper() for w in ["ARRE", "BHAI", "RUKO"]):
                        custom_pace = 1.45
                    elif "..." in text:
                        custom_pace = 0.9
                
                if self._speak_sarvam(text, pace=custom_pace):
                    return

            # Try Amazon Polly second
            if self._polly_available:
                if self._speak_polly(text):
                    return

            # Fallback to Edge-TTS
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

    def _speak_polly(self, text: str) -> bool:
        """
        Generate audio with Amazon Polly (Premium Neural Voice).
        Uses SSML to speed up the speaking rate to 115% and increase pitch to sound younger.
        Returns True if successful.
        """
        if not self._polly_client or self._interrupt_event.is_set():
            return False
            
        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            # Escape XML characters for SSML
            safe_text = text.replace("&", "and").replace("<", "").replace(">", "")
            ssml_text = f'<speak><prosody rate="115%">{safe_text}</prosody></speak>'
            
            response = self._polly_client.synthesize_speech(
                Text=ssml_text,
                TextType="ssml",
                OutputFormat="mp3",
                VoiceId=POLLY_VOICE_ID,
                Engine=POLLY_ENGINE,
                LanguageCode="hi-IN"
            )
            
            if "AudioStream" in response:
                with open(tmp_path, "wb") as f:
                    f.write(response["AudioStream"].read())
                    
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    self._play_with_lip_sync(tmp_path)
                    
                    if len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, tmp_path)
                        
                    logger.info(f"[TTS] ✅ AWS Polly spoke: '{text[:40]}...'")
                    return True
            return False
        except Exception as e:
            logger.warning(f"[TTS] AWS Polly failed: {e} — falling back")
            return False
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _speak_thread(self, text: str, callback: Optional[Callable],
                      voice: Optional[str] = None) -> None:
        """Internal speak thread — cache → Polly → Sarvam → edge-tts → pyttsx3."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            text = self._add_natural_pauses(text)

            # STEP 1: Check cache (instant playback) — skip if custom voice
            cached_path = _is_cached(text) if not voice else None
            if cached_path:
                self._play_with_lip_sync(str(cached_path))
            # STEP 1.5: Try Sarvam AI (Energetic young Indian female voice — HIGHEST PRIORITY)
            elif self._sarvam_available:
                if not self._speak_sarvam(text):
                    # Sarvam failed → fallback to Amazon Polly
                    if self._polly_available:
                        if not self._speak_polly(text):
                            if self._edge_available:
                                if not self._speak_edge_with_retry(text, voice):
                                    self._speak_pyttsx3(text)
                            else:
                                self._speak_pyttsx3(text)
                    elif self._edge_available:
                        if not self._speak_edge_with_retry(text, voice):
                            self._speak_pyttsx3(text)
                    else:
                        self._speak_pyttsx3(text)
            # STEP 2: Try Amazon Polly (Premium Neural Voice — PRIMARY FALLBACK)
            elif self._polly_available:
                if not self._speak_polly(text):
                    if self._edge_available:
                        if not self._speak_edge_with_retry(text, voice):
                            self._speak_pyttsx3(text)
                    else:
                        self._speak_pyttsx3(text)
            # STEP 3: Edge-TTS with timeout + 1 retry
            elif self._edge_available:
                if not self._speak_edge_with_retry(text, voice):
                    self._speak_pyttsx3(text)
            else:
                # STEP 4: Last resort — pyttsx3 offline
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

    def _speak_sarvam(self, text: str, pace: Optional[float] = None) -> bool:
        """
        Generate audio with Sarvam AI API (Premium Indian TTS).
        Returns True if successful, False if failed/fallback needed.
        """
        if not self._sarvam_client or self._interrupt_event.is_set():
            return False

        # Clean text to fix Hinglish pronunciation issues (like 'bajke' -> 'baj kar')
        text = self._clean_for_tts(text)

        tmp_path = tempfile.mktemp(suffix=".wav")
        try:
            from sarvamai.play import save

            use_pace = pace if pace is not None else SARVAM_PACE

            response = self._sarvam_client.text_to_speech.convert(
                text=text,
                target_language_code=SARVAM_LANGUAGE,
                model=SARVAM_MODEL,
                speaker=SARVAM_SPEAKER,
                pace=use_pace,
            )

            # Save audio to temp file
            save(response, tmp_path)

            # Verify file is valid
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                self._play_with_lip_sync(tmp_path)

                # Auto-cache short phrases
                if len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                    _save_to_cache(text, tmp_path)

                logger.info(f"[TTS] ✅ Sarvam AI spoke: '{text[:40]}...'")
                return True
            else:
                logger.warning("[TTS] Sarvam AI returned empty/invalid audio.")
                return False

        except Exception as e:
            logger.warning(f"[TTS] Sarvam AI failed: {e} — falling back to Edge-TTS")
            return False
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

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

    def _clean_for_tts(self, text: str) -> str:
        """Fix known Hinglish pronunciation issues for Sarvam AI / TTS."""
        replacements = {
            "bajke": "baj kar",
            "bajker": "baj kar",
            "bje": "baje",
            "kya": "kyaa",
            "hu": "hoon",
            "ha": "haan",
            "nhi": "nahi",
            "mai": "main",
            "rha": "raha",
            "rhi": "rahi",
            "kr": "kar",
            "kyu": "kyun",
            "0": "shunya", "1": "ek", "2": "do", "3": "teen", "4": "chaar",
            "5": "paanch", "6": "chhah", "7": "saat", "8": "aath", "9": "nau"
        }
        
        # Simple word boundary replacement
        words = text.split()
        cleaned_words = []
        for w in words:
            # Handle punctuation attached to words
            clean_w = w.lower().strip(".,!?\"'")
            if clean_w in replacements:
                # Replace but keep original casing/punctuation if possible (simplified here)
                w = w.lower().replace(clean_w, replacements[clean_w])
            cleaned_words.append(w)
            
        return " ".join(cleaned_words)

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
