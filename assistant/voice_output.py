"""
Voice Output with TTS Cache + Real-time Lip Sync.

Flow:
1. On startup: pre-generate MP3 for 22 common phrases (background thread)
2. On speak(): check cache first (instant) → fallback to edge-tts (1-2s delay)
3. Audio playback via sounddevice (numpy) — gives frame-by-frame amplitude for lip sync
4. After fresh generation: auto-cache short phrases for future use

Cache location: cache/tts_cache/
Filename: MD5(text.lower().strip()) + ".mp3"
"""

import asyncio
import hashlib
import logging
import math
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

from config import DEFAULT_LANGUAGE, PROJECT_ROOT

logger = logging.getLogger(__name__)

# --- Voice Configuration ---
VOICE_PRIMARY = "en-IN-NeerjaNeural"
VOICE_FALLBACK = "hi-IN-SwaraNeural"
RATE = "+30%"

# --- Cache Configuration ---
CACHE_DIR = PROJECT_ROOT / "cache" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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

# Max text length to auto-cache after fresh generation
AUTO_CACHE_MAX_LEN = 40


def _text_to_cache_path(text: str) -> Path:
    """Convert text to its cache file path using MD5 hash."""
    normalized = text.lower().strip()
    md5 = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{md5}.mp3"


def _is_cached(text: str) -> Optional[Path]:
    """Check if text has a cached MP3. Returns path if exists, None otherwise."""
    path = _text_to_cache_path(text)
    with _cache_lock:
        if path.exists() and path.stat().st_size > 500:
            return path
    return None


def _save_to_cache(text: str, mp3_path: str) -> None:
    """Copy an MP3 file into the cache."""
    try:
        cache_path = _text_to_cache_path(text)
        with _cache_lock:
            if not cache_path.exists():
                import shutil
                shutil.copy2(mp3_path, str(cache_path))
    except Exception:
        pass


# --- Pre-generation at startup ---

def prebuild_cache() -> None:
    """Pre-generate MP3 for all common phrases (runs in background thread)."""
    import edge_tts

    to_generate = []
    for phrase in CACHE_PHRASES:
        if not _is_cached(phrase):
            to_generate.append(phrase)

    if not to_generate:
        logger.info("[TTS Cache] All phrases already cached. Ready.")
        return

    logger.info(f"[TTS Cache] Generating {len(to_generate)} phrases...")

    async def _generate_all():
        for i in range(0, len(to_generate), 5):
            batch = to_generate[i:i+5]
            tasks = [_generate_one(phrase) for phrase in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _generate_one(phrase: str):
        try:
            cache_path = _text_to_cache_path(phrase)
            for voice in [VOICE_PRIMARY, VOICE_FALLBACK]:
                try:
                    communicate = edge_tts.Communicate(phrase, voice, rate=RATE)
                    await communicate.save(str(cache_path))
                    if cache_path.exists() and cache_path.stat().st_size > 500:
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[TTS Cache] Failed to cache '{phrase}': {e}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_generate_all())
        loop.close()
        logger.info("[TTS Cache] Ready.")
    except Exception as e:
        logger.warning(f"[TTS Cache] Pre-generation failed: {e}")


def _start_cache_warmup() -> None:
    """Start cache pre-generation in background thread (non-blocking)."""
    thread = threading.Thread(target=prebuild_cache, daemon=True)
    thread.start()


# --- Main Voice Output Class ---

class VoiceOutput:
    """
    Voice output with TTS cache + real-time lip sync.
    
    Uses soundfile (libsndfile) to decode MP3 → PCM numpy array.
    Uses sounddevice to play PCM while analyzing amplitude per frame for lip sync.
    No ffmpeg needed.
    """

    def __init__(self) -> None:
        self.is_speaking: bool = False
        self._lock = threading.Lock()
        self._edge_available: bool = False
        self._soundfile_available: bool = False
        self._sounddevice_available: bool = False
        self._lip_sync_callback = None

        try:
            import edge_tts
            self._edge_available = True
            logger.info("Edge-TTS initialized — using natural neural voices (FREE).")
        except ImportError:
            pass

        try:
            import soundfile
            self._soundfile_available = True
        except ImportError:
            logger.warning("soundfile not available — lip sync will use fallback.")

        try:
            import sounddevice
            self._sounddevice_available = True
        except ImportError:
            logger.warning("sounddevice not available for playback — using PowerShell.")

        # Start cache warmup in background
        _start_cache_warmup()

    def set_lip_sync_callback(self, callback) -> None:
        """
        Set a callback for lip sync. Called with volume (0.0-1.0) during playback.
        
        Args:
            callback: Function(volume: float) called ~30 times/sec during speech.
        """
        self._lip_sync_callback = callback

    def speak(self, text: str, language: Optional[str] = None, voice: Optional[str] = None, callback=None) -> None:
        """
        Speak text. Checks cache first (instant), falls back to live TTS.

        Args:
            text: Text to speak.
            language: Optional language override.
            voice: Optional Edge TTS voice name (e.g. 'mr-IN-AarohiNeural').
            callback: Called when speaking is done.
        """
        if not text:
            if callback:
                callback()
            return

        thread = threading.Thread(
            target=self._speak_thread,
            args=(text, callback, voice),
            daemon=True
        )
        thread.start()

    def _speak_thread(self, text: str, callback, voice: Optional[str] = None) -> None:
        """Internal speak thread — cache check → edge-tts → pyttsx3."""
        with self._lock:
            self.is_speaking = True
            try:
                # STEP 1: Check cache (instant playback) — skip cache if custom voice
                cached_path = _is_cached(text) if not voice else None
                if cached_path:
                    logger.debug(f"[TTS Cache] HIT: '{text[:30]}...'")
                    self._play_with_lip_sync(str(cached_path))
                elif self._edge_available:
                    # STEP 2: Generate fresh with edge-tts (with language-specific voice)
                    self._speak_edge(text, voice)
                else:
                    # STEP 3: Offline fallback
                    self._speak_pyttsx3(text)
            except Exception as e:
                logger.error(f"TTS error: {e}")
                try:
                    self._speak_pyttsx3(text)
                except Exception:
                    pass
            finally:
                self.is_speaking = False
                # Ensure mouth closes
                if self._lip_sync_callback:
                    try:
                        self._lip_sync_callback(0.0)
                    except Exception:
                        pass
                if callback:
                    callback()

    def _speak_edge(self, text: str, voice: Optional[str] = None) -> None:
        """Generate audio with edge-tts and play with lip sync."""
        import edge_tts

        # Build voice priority list: custom voice first, then defaults
        voices_to_try = []
        if voice:
            voices_to_try.append(voice)
        voices_to_try.extend([VOICE_PRIMARY, VOICE_FALLBACK])

        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            success = False
            for v in voices_to_try:
                try:
                    comm = edge_tts.Communicate(text, v, rate=RATE)
                    loop.run_until_complete(comm.save(tmp_path))
                    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
                        success = True
                        logger.info(f"[TTS] Using voice: {v}")
                        break
                except Exception:
                    continue

            loop.close()

            if success:
                self._play_with_lip_sync(tmp_path)

                # Auto-cache short phrases (only for default voice)
                if not voice and len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                    _save_to_cache(text, tmp_path)

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _play_with_lip_sync(self, filepath: str) -> None:
        """
        Play audio file with real-time lip sync.
        
        Strategy:
        1. Decode MP3/WAV → numpy PCM using soundfile
        2. Play via sounddevice with a callback that reports amplitude
        3. Lip sync callback gets real amplitude per audio frame
        
        Fallback: PowerShell playback + simulated lip sync
        """
        # Try to decode audio to PCM
        pcm_data = None
        sample_rate = 24000

        if self._soundfile_available:
            try:
                import soundfile as sf
                pcm_data, sample_rate = sf.read(filepath, dtype='float32')
                # Convert to mono if stereo
                if len(pcm_data.shape) > 1:
                    pcm_data = pcm_data.mean(axis=1)
                logger.debug(f"[LipSync] Decoded: {len(pcm_data)} samples @ {sample_rate}Hz")
            except Exception as e:
                logger.debug(f"[LipSync] soundfile decode failed: {e}")
                pcm_data = None

        if pcm_data is not None and self._sounddevice_available:
            # Best path: play with sounddevice + real-time lip sync
            self._play_sounddevice_with_lip_sync(pcm_data, sample_rate)
        else:
            # Fallback: PowerShell playback + simulated lip sync
            self._play_powershell(filepath)

    def _play_sounddevice_with_lip_sync(self, pcm_data: np.ndarray, sample_rate: int) -> None:
        """
        Play PCM audio via PowerShell while driving lip sync from actual amplitude.
        
        NOTE: We do NOT use sounddevice for playback (it conflicts with mic input).
        Instead: PowerShell plays the audio, and we analyze pcm_data in parallel for lip sync.
        """
        # Save PCM as temp WAV for PowerShell to play
        tmp_wav = tempfile.mktemp(suffix=".wav")
        try:
            import soundfile as sf
            sf.write(tmp_wav, pcm_data, sample_rate)
        except Exception as e:
            logger.error(f"Failed to write temp WAV: {e}")
            return

        # Start lip sync driver thread (analyzes pcm_data amplitude)
        lip_thread = None
        if self._lip_sync_callback:
            lip_thread = threading.Thread(
                target=self._drive_lip_sync_realtime,
                args=(pcm_data, sample_rate),
                daemon=True
            )
            lip_thread.start()

        # Play via PowerShell (does NOT block sounddevice/mic)
        try:
            ps_cmd = (
                f'Add-Type -AssemblyName PresentationCore;'
                f'$p=New-Object System.Windows.Media.MediaPlayer;'
                f'$p.Open([Uri]::new("{tmp_wav.replace(chr(92), "/")}"));'
                f'$p.Play();Start-Sleep -Milliseconds 300;'
                f'while($p.NaturalDuration.HasTimeSpan -eq $false){{Start-Sleep -Milliseconds 50}};'
                f'Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds - 100);'
                f'$p.Close()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=30
            )
        except Exception as e:
            logger.error(f"PowerShell WAV play error: {e}")
        finally:
            # Ensure lip sync stops
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass
            try:
                os.unlink(tmp_wav)
            except OSError:
                pass

    def _drive_lip_sync_realtime(self, pcm_data: np.ndarray, sample_rate: int) -> None:
        """
        Analyze PCM amplitude and drive lip sync at 30fps.
        Runs in parallel with sounddevice playback.
        
        Key: pcm_data is float32 (-1.0 to 1.0), so silence = near 0.0.
        """
        fps = 30
        samples_per_frame = sample_rate // fps
        total_frames = len(pcm_data) // samples_per_frame

        # Pre-compute RMS per frame
        rms_values = []
        for i in range(total_frames):
            start = i * samples_per_frame
            end = start + samples_per_frame
            chunk = pcm_data[start:end]
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            rms_values.append(rms)

        if not rms_values:
            return

        # Find the max RMS for normalization (adapt to this specific audio)
        max_rms = max(rms_values)
        if max_rms < 0.001:
            return  # Complete silence

        # Normalize and apply threshold
        # For float32 audio: silence is < 0.01, speech is 0.02-0.3 typically
        silence_threshold = max_rms * 0.08  # Below 8% of peak = silence

        volumes = []
        for rms in rms_values:
            if rms < silence_threshold:
                volumes.append(0.0)
            else:
                # Map silence_threshold..max_rms → 0.1..0.85
                normalized = (rms - silence_threshold) / (max_rms - silence_threshold)
                mapped = 0.1 + normalized * 0.75
                volumes.append(min(0.85, mapped))

        # Smooth with moving average (window=2) — removes single-frame spikes
        smoothed = []
        for i in range(len(volumes)):
            if i == 0:
                smoothed.append(volumes[i])
            else:
                smoothed.append(volumes[i - 1] * 0.3 + volumes[i] * 0.7)

        # Send to avatar at 30fps (synced with audio playback)
        frame_duration = 1.0 / fps
        prev_vol = 0.0

        for vol in smoothed:
            if not self.is_speaking:
                break

            # Extra lerp for buttery smooth movement
            lerped = prev_vol * 0.2 + vol * 0.8
            prev_vol = lerped

            try:
                self._lip_sync_callback(lerped)
            except Exception:
                break

            time.sleep(frame_duration)

        # Ensure mouth closes
        try:
            self._lip_sync_callback(0.0)
        except Exception:
            pass

    def _play_powershell(self, filepath: str) -> None:
        """Fallback: Play audio via PowerShell .NET MediaPlayer + simulated lip sync."""
        # Start simulated lip sync
        if self._lip_sync_callback:
            lip_thread = threading.Thread(
                target=self._simulate_lip_sync, args=(filepath,), daemon=True
            )
            lip_thread.start()

        try:
            ps_cmd = (
                f'Add-Type -AssemblyName PresentationCore;'
                f'$p=New-Object System.Windows.Media.MediaPlayer;'
                f'$p.Open([Uri]::new("{filepath.replace(chr(92), "/")}"));'
                f'$p.Play();Start-Sleep -Milliseconds 300;'
                f'while($p.NaturalDuration.HasTimeSpan -eq $false){{Start-Sleep -Milliseconds 50}};'
                f'Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds - 100);'
                f'$p.Close()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=30
            )
        except Exception as e:
            logger.error(f"PowerShell play error: {e}")

    def _simulate_lip_sync(self, filepath: str) -> None:
        """
        Simulated lip sync for when PCM decode is not available.
        Uses natural speech rhythm patterns.
        """
        try:
            file_size = os.path.getsize(filepath)
            duration_sec = max(0.8, (file_size * 8) / 48000.0)
        except Exception:
            duration_sec = 2.5

        # Wait for player startup
        time.sleep(0.32)

        fps = 30
        total_frames = int(duration_sec * fps)
        prev_vol = 0.0

        for frame in range(total_frames):
            if not self.is_speaking:
                break
            t = frame / fps

            # Natural speech: syllables at ~5Hz with word gaps
            syllable = abs(math.sin(t * 5.0 * math.pi))
            word_envelope = 0.5 + 0.5 * math.sin(t * 1.5 * math.pi)
            vol = syllable * word_envelope * 0.65

            # Word-gap silence
            if math.sin(t * 3.8) < -0.6:
                vol = 0.0

            # Smooth
            smoothed = prev_vol * 0.3 + vol * 0.7
            prev_vol = smoothed
            smoothed = max(0.0, min(0.75, smoothed))

            try:
                self._lip_sync_callback(smoothed)
            except Exception:
                break
            time.sleep(1.0 / fps)

    def _speak_pyttsx3(self, text: str) -> None:
        """Fallback offline TTS."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for voice in voices:
                if "zira" in voice.name.lower():
                    engine.setProperty("voice", voice.id)
                    break
            engine.setProperty("rate", 170)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            logger.error(f"pyttsx3 failed: {e}")

    def stop(self) -> None:
        """Stop speaking."""
        self.is_speaking = False
