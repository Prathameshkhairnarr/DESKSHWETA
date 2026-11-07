"""
Voice Output with TTS Cache + Real-time Lip Sync.

PRODUCTION v5.0:
- Amazon Polly GENERATIVE as PRIMARY (Kajal — emotionally engaged, human-like)
- Amazon Polly Neural as FALLBACK (if generative unavailable in region)
- pyttsx3 as LAST RESORT offline fallback
- Interruptible playback (stop current audio, start new immediately)
- LRU cache with size limit (max 500 files / 100MB)
- Cache integrity check (skip corrupt/empty files)
- Lip sync thread as daemon with exception handling + timeout join
- Proper resource cleanup (temp files, audio device)
- No artificial delays on success path

Voice Quality:
- Polly Generative engine uses billion-parameter transformer model
- Produces emotionally engaged, assertive, colloquial speech
- Kajal (hi-IN) is bilingual — speaks Hinglish naturally without robotic tone
- No need for heavy SSML — the model handles emotion/pacing/breathing automatically

Flow:
1. On speak(): check cache (instant) → Polly Generative → Polly Neural → pyttsx3
2. Audio playback via pygame/sounddevice with real-time lip sync at 30fps
3. Interruptible: new speak() stops current audio immediately
"""

import hashlib
import logging
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

# --- Murf Falcon 2.1 TTS Configuration (PRIMARY — Pooja Conversational hi-IN) ---
MURF_API_KEY = os.environ.get("MURF_API_KEY", "")
MURF_VOICE_ID = "Pooja"                 # Pooja — natural conversational Indian female
MURF_STYLE = "Conversational"          # Conversational style
MURF_MODEL = "falcon-2.1"              # Murf Falcon 2.1 ultra-low latency model (<100ms)
MURF_LOCALE = "hi-IN"                  # Hindi (India) proper Hindi pronunciation
MURF_PITCH = 0                         # Natural pitch
MURF_FORMAT = "MP3"
MURF_SAMPLE_RATE = 44100.0             # Murf high-quality rate
MURF_FALCON_ENDPOINTS = [
    "https://in.api.murf.ai/v1/speech/stream",      # India low-latency endpoint
    "https://global.api.murf.ai/v1/speech/stream",  # Global router endpoint
]

# --- Amazon Polly TTS Configuration (FALLBACK) ---
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
POLLY_VOICE_ID = "Aditi"               # Indian Female Voice (Aditi) — Polly fallback
POLLY_ENGINE = "standard"              # Standard engine (Aditi supports standard engine)
POLLY_LANGUAGE = "hi-IN"               # hi-IN for proper Hindi/Hinglish pronunciation

# Area 4 fix: use raw PCM instead of mp3.
# Polly generative only supports SampleRate=16000 for Kajal/hi-IN (22050 and 24000
# both throw InvalidSampleRateException). mp3 has no explicit SampleRate param, so
# Polly chooses internally (likely 22050) while pygame was inited at 24000 — the
# mismatch makes audio play ~9% too fast, raising pitch and sounding tinny/robotic.
# PCM + WAV = exact lossless samples at a known rate → zero resampling artifacts.
POLLY_SAMPLE_RATE = 16000              # Only valid rate for Kajal generative
PYGAME_MIXER_FREQ = 16000              # Must match POLLY_SAMPLE_RATE exactly

# --- Voice Character Tuning ---
# Polly Kajal generative voice is ALREADY a natural young Indian female voice.
# Pitch shifting makes it sound robotic/unnatural ("cute robot"). Setting to 0
# lets the raw Polly output play as-is — the most human-like result.
# If you want a SLIGHT feminization (barely noticeable), try 0.5 max.
# Used by BOTH engine paths so switching generative<->neural stays consistent:
#   - Generative path: applied as post-processing via librosa.effects.pitch_shift (n_steps).
#   - Neural path: converted to an equivalent SSML <prosody pitch="+X%"> value.
VOICE_PITCH_SEMITONES = 0.0            # 0 = natural Polly voice, no artificial pitch shift
# Perceptual mapping: each semitone ≈ +6% pitch in SSML terms (2^(1/12) - 1 ≈ 5.95%).
VOICE_PITCH_SSML_PERCENT = round((2 ** (VOICE_PITCH_SEMITONES / 12.0) - 1) * 100)

# --- Cache Configuration ---
CACHE_DIR = PROJECT_ROOT / "cache" / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_MAX_FILES = 500          # Max cached MP3 files
CACHE_MAX_SIZE_MB = 100        # Max total cache size in MB
CACHE_MIN_FILE_SIZE = 500      # Minimum valid MP3 size in bytes
AUTO_CACHE_MAX_LEN = 40        # Max text length to auto-cache

# Cache signature: any change to voice/engine/language/pitch invalidates ALL old
# cache entries automatically (they hash to different keys and become unreachable).
# This is the permanent fix for "greeting sounds like a different voice" — stale audio
# from a previous engine can never be matched again.
CACHE_ENGINE_SIGNATURE = f"murf:falcon2.1:{MURF_VOICE_ID}:{MURF_LOCALE}:{MURF_STYLE}:pitch{MURF_PITCH}"

# Common phrases to pre-cache at startup (saves Murf credits — spoken from cache instantly).
PRECACHE_PHRASES = [
    "हाँ बोल", "हाँ बोलो", "ठीक है", "हो गया", "कर दिया",
    "एक सेकंड", "रुक जा", "हो गया भाई", "डन", "रेडी हूँ",
    "हाँ कर रही हूँ", "समझ गई", "मस्त हूँ भाई, तू बता",
    "क्या हाल है", "बता क्या करना है", "सॉरी समझ नहीं आया",
    "फिर से बोल", "कुछ और", "ठीक है कर दिया", "अरे यार, कितना सन्नाटा है...",
]

# Lock for thread-safe cache access
_cache_lock = threading.Lock()


# ============================================================
# Cache Utilities
# ============================================================

def _text_to_cache_path(text: str) -> Path:
    """
    Convert text to its cache file path using MD5 hash.
    The hash includes the engine/voice/language/pitch signature so that audio
    generated by a different engine (or different voice tuning) NEVER collides
    with the current one — this guarantees voice consistency across sessions.
    """
    normalized = text.lower().strip()
    keyed = f"{CACHE_ENGINE_SIGNATURE}|{normalized}"
    md5 = hashlib.md5(keyed.encode("utf-8")).hexdigest()
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
    """
    Copy an MP3 file into the cache with LRU eviction.
    Also writes a tiny sidecar .meta file recording WHICH engine/voice produced
    the audio, so this class of "voice mismatch" bug is auditable and can never be
    reintroduced silently.
    """
    try:
        cache_path = _text_to_cache_path(text)
        with _cache_lock:
            if not cache_path.exists():
                # Check if we need to evict
                _evict_if_needed()
                shutil.copy2(mp3_path, str(cache_path))
                # Sidecar: record the exact engine signature + source text.
                try:
                    meta_path = cache_path.with_suffix(".meta")
                    meta_path.write_text(
                        f"{CACHE_ENGINE_SIGNATURE}\n{text.strip()}",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                logger.debug(f"[Cache] Saved '{text[:30]}' [{CACHE_ENGINE_SIGNATURE}]")
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
                # Remove the matching sidecar too
                f.with_suffix(".meta").unlink(missing_ok=True)
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
        self._murf_available: bool = False
        self._polly_available: bool = False
        self._soundfile_available: bool = False
        self._sounddevice_available: bool = False
        self._lip_sync_callback: Optional[Callable] = None
        self._current_thread: Optional[threading.Thread] = None

        # --- Murf Falcon 2.1 TTS (PRIMARY — Pooja Conversational) ---
        self._murf_client = None
        if MURF_API_KEY:
            try:
                from murf import Murf
                self._murf_client = Murf(api_key=MURF_API_KEY)
                self._murf_available = True
                logger.info(f"[TTS] Murf Falcon 2.1 initialized — voice '{MURF_VOICE_ID}' style '{MURF_STYLE}' locale '{MURF_LOCALE}' (PRIMARY).")
            except Exception as e:
                logger.warning(f"[TTS] Murf init failed: {e}")
        else:
            logger.warning("[TTS] MURF_API_KEY not set — Murf disabled, using Polly.")

        # --- Amazon Polly TTS (FALLBACK) ---
        self._polly_client = None
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
                logger.info(f"[TTS] Amazon Polly initialized — '{POLLY_VOICE_ID}' voice (FALLBACK).")
            except Exception as e:
                logger.warning(f"[TTS] Polly init failed: {e}")
        else:
            logger.warning("[TTS] AWS credentials not set. Polly fallback unavailable.")

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

        # Pre-cache common phrases in background (saves Murf credits — one-time)
        threading.Thread(target=self._prebuild_cache, daemon=True, name="TTS-Precache").start()

    def set_lip_sync_callback(self, callback: Callable) -> None:
        """Set callback for lip sync. Called with volume (0.0-1.0) at ~30fps."""
        self._lip_sync_callback = callback

    def speak(self, text: str, language: Optional[str] = None,
              voice: Optional[str] = None, callback: Optional[Callable] = None) -> None:
        """
        Speak text. Interrupts any current speech first.
        Priority: cache (instant) → Polly Generative → Polly Neural → pyttsx3.
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
        """Speak reaction with Polly. Falls back to pyttsx3 if Polly unavailable."""
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
        """Speak reaction — cache → Murf (Alia) → Polly → pyttsx3."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            cached_path = _is_cached(text)
            if cached_path:
                self._play_with_lip_sync(str(cached_path))
                return
            if self._murf_available and self._speak_murf(text):
                return
            # Polly disabled (robotic) — skip to pyttsx3
            # if self._polly_available and self._speak_polly(text):
            #     return
            # Last resort fallback
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

    def _interrupt(self) -> None:
        """Signal current speech to stop."""
        if self.is_speaking:
            self._interrupt_event.set()
            self.is_speaking = False
            # Stop pygame if it's playing
            try:
                import pygame
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception:
                pass
            if self._current_thread and self._current_thread.is_alive():
                self._current_thread.join(timeout=1.0)
            self._interrupt_event.clear()
            if self._lip_sync_callback:
                try:
                    self._lip_sync_callback(0.0)
                except Exception:
                    pass

    @staticmethod
    def _safe_delete_temp(path: str) -> None:
        """Safely delete a temp file, ignoring errors."""
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass

    def _speak_polly(self, text: str) -> bool:
        """
        Generate audio with Amazon Polly Generative Engine.
        OutputFormat=pcm at 16000Hz → written as WAV → zero resampling artifacts.
        Area 1: logs engine/voice/region before EVERY call so silent fallbacks are visible.
        """
        if not self._polly_client or self._interrupt_event.is_set():
            return False

        # Area 1: log exactly what we're sending before the call
        logger.info(
            f"[TTS] Polly request → engine={POLLY_ENGINE}  voice={POLLY_VOICE_ID}"
            f"  lang={POLLY_LANGUAGE}  region={AWS_REGION}"
        )

        # Area 4: WAV temp file (PCM wrapped in WAV header for soundfile/pygame)
        tmp_path = tempfile.mktemp(suffix=".wav")
        try:
            clean_text = self._prepare_text_for_polly(text)
            ssml_text  = self._build_polly_ssml(clean_text)

            logger.debug(f"[TTS] Polly IN  : {text!r}")
            logger.debug(f"[TTS] Polly SSML: {ssml_text!r}")
            response = self._polly_client.synthesize_speech(
                Text=ssml_text,
                TextType="ssml",
                OutputFormat="pcm",          # Area 4: raw PCM, no lossy re-encode
                SampleRate=str(POLLY_SAMPLE_RATE),  # Area 4: 16000, only valid rate
                VoiceId=POLLY_VOICE_ID,
                Engine=POLLY_ENGINE,
                LanguageCode=POLLY_LANGUAGE,
            )

            if "AudioStream" in response:
                # Wrap raw PCM bytes in a proper WAV container so soundfile/pygame
                # can read the sample rate without guessing
                import wave
                pcm_bytes = response["AudioStream"].read()
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)                  # 16-bit
                    wf.setframerate(POLLY_SAMPLE_RATE)
                    wf.writeframes(pcm_bytes)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    play_path = self._pitch_shift_audio(tmp_path, n_steps=VOICE_PITCH_SEMITONES)
                    self._play_with_lip_sync(play_path)

                    if len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, play_path)

                    logger.info(f"[TTS] Polly Generative spoke: '{text[:50]}'")
                    self._safe_delete_temp(tmp_path)
                    if play_path != tmp_path:
                        self._safe_delete_temp(play_path)
                    return True
            return False

        except Exception as e:
            error_str = str(e)
            # Area 1: always log the full exception — never swallow silently
            logger.error(f"[TTS] Polly {POLLY_ENGINE} FAILED (engine={POLLY_ENGINE}, "
                         f"voice={POLLY_VOICE_ID}, region={AWS_REGION}): {e}")
            if "ValidationException" in error_str or "not supported" in error_str.lower() \
                    or "InvalidSampleRate" in error_str:
                logger.warning("[TTS] Falling back to Polly neural engine.")
                return self._speak_polly_neural_fallback(text)
            return False
        finally:
            self._safe_delete_temp(tmp_path)

    def _speak_polly_neural_fallback(self, text: str) -> bool:
        """
        Fallback to Polly neural engine.
        Area 1: logs engine before call.
        Area 3: adds clause/sentence SSML breaks (neural supports full prosody SSML).
        Area 4: PCM 16kHz WAV — same as generative path, zero resampling.
        """
        if not self._polly_client or self._interrupt_event.is_set():
            return False

        logger.info(
            f"[TTS] Polly request → engine=neural  voice={POLLY_VOICE_ID}"
            f"  lang=hi-IN  region={AWS_REGION}"
        )

        tmp_path = tempfile.mktemp(suffix=".wav")
        try:
            clean = self._prepare_text_for_polly(text)
            # Area 3: neural supports full SSML prosody — add clause/sentence breaks
            ssml_text = self._build_neural_ssml(clean)

            logger.debug(f"[TTS] Polly Neural SSML: {ssml_text!r}")

            response = self._polly_client.synthesize_speech(
                Text=ssml_text,
                TextType="ssml",
                OutputFormat="pcm",
                SampleRate=str(POLLY_SAMPLE_RATE),
                VoiceId=POLLY_VOICE_ID,
                Engine="neural",
                LanguageCode="hi-IN",
            )

            if "AudioStream" in response:
                import wave
                pcm_bytes = response["AudioStream"].read()
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(POLLY_SAMPLE_RATE)
                    wf.writeframes(pcm_bytes)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    self._play_with_lip_sync(tmp_path)
                    if len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, tmp_path)
                    logger.info(f"[TTS] Polly Neural spoke: '{text[:50]}'")
                    self._safe_delete_temp(tmp_path)
                    return True
            return False
        except Exception as e:
            logger.error(f"[TTS] Polly neural FAILED (voice={POLLY_VOICE_ID}, "
                         f"region={AWS_REGION}): {e}")
            return False
        finally:
            self._safe_delete_temp(tmp_path)

    def _prepare_text_for_polly(self, text: str) -> str:
        """
        Prepare text for Polly generative engine.
        - Clean Hinglish shorthand for proper pronunciation
        - Remove emojis/markdown that TTS can't handle
        - Expand abbreviations
        - Make text flow naturally for speech
        """
        import re
        
        # Remove emojis and special characters that TTS can't pronounce
        text = re.sub(r'[📁📄💬🗣⏰⚠️🔋💾🖥️💿📝🕐🌤📈📉🥇🥈🔔✅❌🎵🎶🔍💡🤖👋🙏😊😂🥺😭😤🤔💪🎉🔥⭐🌟✨]', '', text)
        text = re.sub(r'[*_~`#\[\]]', '', text)  # Remove markdown formatting
        
        # Expand tech abbreviations for pronunciation
        polly_abbr = {
            "PC": "P C",
            "GB": "G B",
            "MB": "M B",
            "KB": "K B",
            "CPU": "C P U",
            "RAM": "raam",
            "WiFi": "why fy",
            "USB": "U S B",
            "PDF": "P D F",
            "URL": "U R L",
            "AI": "A I",
            "OK": "okay",
            "ok": "okay",
            "vs": "versus",
            "etc": "etcetera",
            "min": "minute",
            "sec": "second",
            "hr": "hour",
            "hrs": "hours",
        }
        
        for abbr, expanded in polly_abbr.items():
            # Only replace if it's a standalone word (not part of another word)
            text = re.sub(r'\b' + re.escape(abbr) + r'\b', expanded, text)
        
        # Fix Hinglish shorthand → proper spoken form
        text = self._clean_for_tts(text)
        
        # Remove repeated punctuation (AI sometimes does "..." or "!!!")
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        
        # Clean multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def _build_polly_ssml(self, text: str) -> str:
        """
        Build SSML for Polly Generative engine.

        IMPORTANT: The generative engine handles ALL prosody (pacing, emotion,
        sentence breaks, breathing) automatically from the raw text. Adding
        <s> tags forces prosody resets between fragments which makes short
        sentences sound robotic/disconnected (the greeting bug). Just wrap in
        <speak> and let the engine handle natural flow on its own.
        """
        # Escape XML characters
        text = text.replace("&", "and").replace("<", "").replace(">", "")
        return f'<speak>{text}</speak>'

    def _build_neural_ssml(self, text: str) -> str:
        """
        Area 3: Build prosody-rich SSML for the neural engine fallback.
        Neural engine does NOT auto-handle pacing like generative does — without
        explicit SSML breaks, all sentences run together at the same flat tone.
        This adds clause-level pauses (commas → 150ms) and sentence-level pauses
        (. ! ? → 350ms) so the delivery sounds natural and alive.
        """
        import re
        # Escape XML characters
        text = text.replace("&", "and").replace("<", "").replace(">", "")

        # Insert break after commas/semicolons (clause pause)
        text = re.sub(r',\s*', ', <break time="150ms"/> ', text)
        text = re.sub(r';\s*', '; <break time="150ms"/> ', text)

        # Insert break after sentence-ending punctuation
        text = re.sub(r'\.\s+', '. <break time="350ms"/> ', text)
        text = re.sub(r'!\s+', '! <break time="350ms"/> ', text)
        text = re.sub(r'\?\s+', '? <break time="350ms"/> ', text)

        # Clean up any doubled spaces from the substitutions
        text = re.sub(r'  +', ' ', text).strip()

        return f'<speak>{text}</speak>'

    def _pitch_shift_audio(self, audio_path: str, n_steps: float = VOICE_PITCH_SEMITONES) -> str:
        """
        Formant/duration-preserving pitch shift using librosa (phase vocoder).

        This REPLACES the old naive np.interp resample — the root cause of Bug 2
        (mangled / unclear pronunciation). The old method reduced the sample count and
        played it back at the same sample rate, which shifts pitch AND tempo together
        and deforms consonants/formants, smearing word boundaries. It ALSO shortened
        the audio ~10%, throwing lip-sync out near the end.

        librosa.effects.pitch_shift uses a phase vocoder: it keeps DURATION identical
        (lip-sync stays aligned to the last frame) and shifts ONLY perceived pitch, so
        speech stays crisp and correctly pronounced.

        Args:
            audio_path: Path to input audio file (mp3/wav).
            n_steps: Pitch shift in SEMITONES. Positive = higher (younger/feminine).

        Returns:
            Path to the pitched WAV file, or the original path if no shift is applied.
        """
        # No shift requested -> return clean original untouched
        if not n_steps:
            return audio_path
        try:
            import soundfile as sf

            data, sr = sf.read(audio_path, dtype='float32')
            # Mono conversion (Polly output is already mono, but stay safe)
            if data.ndim > 1:
                data = data.mean(axis=1)

            try:
                import librosa
                # Phase-vocoder pitch shift: duration preserved, frequency shifted.
                pitched = librosa.effects.pitch_shift(y=data, sr=sr, n_steps=float(n_steps))
                pitched = np.asarray(pitched, dtype=np.float32)
            except Exception as e:
                # librosa missing/failed -> do NOT fall back to the destructive resample.
                # Returning the clean original (natural Kajal pitch) is always better than
                # smearing the pronunciation.
                logger.warning(f"[TTS] librosa pitch shift unavailable ({e}); using natural pitch.")
                return audio_path

            pitched_path = audio_path.replace('.mp3', '_pitched.wav')
            if pitched_path == audio_path:  # input wasn't .mp3
                pitched_path = audio_path + '_pitched.wav'
            sf.write(pitched_path, pitched, sr)
            return pitched_path
        except Exception as e:
            logger.debug(f"[TTS] Pitch shift failed: {e} — using original")
            return audio_path

    def _speak_thread(self, text: str, callback: Optional[Callable],
                      voice: Optional[str] = None) -> None:
        """Internal speak thread — cache → Murf (Alia) → Polly → pyttsx3.

        The `voice` arg (passed by main.py from the language manager) is IGNORED
        for engine selection — we always use the configured Murf/Polly voice so the
        cache is actually used (previously a truthy `voice` skipped the cache,
        burning credits on every reply)."""
        self.is_speaking = True
        self._interrupt_event.clear()
        try:
            # STEP 1: Check cache (instant, zero API cost) — ALWAYS check now
            cached_path = _is_cached(text)
            if cached_path:
                self._play_with_lip_sync(str(cached_path))
            # STEP 2: Murf Falcon 2.1 (PRIMARY — Pooja Conversational)
            elif self._murf_available and self._speak_murf(text):
                pass
            # STEP 3: Amazon Polly disabled — sounds robotic; skip to pyttsx3
            # elif self._polly_available and self._speak_polly(text):
            #     pass
            # STEP 4: Last resort — pyttsx3 offline
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

    def _speak_murf(self, text: str) -> bool:
        """
        Generate audio with Murf Falcon 2.1 (Pooja, Conversational).
        - If text is Hindi/Hinglish: sends Devanagari Hindi with locale="hi-IN" for proper authentic pronunciation.
        - If text is pure English: sends clean English with locale="en-IN" (natural Indian English accent).
        Uses ultra-low latency streaming (<100ms) with regional failover.
        Caches short phrases to save credits. Returns True on success.
        """
        if not MURF_API_KEY or self._interrupt_event.is_set():
            return False

        import re
        import requests
        from assistant.hinglish_to_devanagari import to_devanagari

        clean = self._strip_for_tts(text)
        if not clean.strip():
            return False

        # Detect whether text is Hindi / Hinglish or pure English
        has_devanagari = len(re.findall(r'[\u0900-\u097F]', clean)) >= 2
        hinglish_markers = {
            "haan", "nahi", "nahin", "kya", "kaise", "kaisi", "kaisa", "hai", "hain", "hoon", "hun",
            "tha", "thi", "the", "kar", "karo", "karna", "raha", "rahi", "rahe", "bhai", "yaar",
            "theek", "thik", "bol", "bolo", "bata", "batao", "chal", "chalo", "shweta", "mujhe",
            "tujhe", "tera", "teri", "tere", "mera", "meri", "mere", "aap", "aapka", "aapki",
            "kaun", "kahan", "kyun", "kyu", "accha", "achha", "mast", "badhiya", "ruk", "suno",
            "sun", "dekh", "dekho", "samajh", "aaya", "aayi", "gaya", "gayi", "ho", "hum", "ab",
            "karenge", "baje", "gana", "gaana", "sunao", "chalao"
        }
        words = set(re.findall(r'[a-zA-Z]+', clean.lower()))
        is_hindi = has_devanagari or bool(words & hinglish_markers)

        if has_devanagari:
            payload_text = clean
            payload_locale = "hi-IN"
        elif is_hindi:
            payload_text = to_devanagari(clean)
            payload_locale = "hi-IN"
        else:
            payload_text = clean
            payload_locale = "en-IN"

        logger.info(f"[TTS] Murf Falcon 2.1 request → voice={MURF_VOICE_ID} locale={payload_locale} | {payload_text[:45]!r}")

        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            headers = {
                "api-key": MURF_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "voiceId": MURF_VOICE_ID,
                "style": MURF_STYLE,
                "model": MURF_MODEL,
                "locale": payload_locale,
                "text": payload_text,
                "format": MURF_FORMAT,
            }

            audio_bytes = None
            for endpoint in MURF_FALCON_ENDPOINTS:
                try:
                    resp = requests.post(endpoint, headers=headers, json=payload, timeout=8)
                    if resp.status_code == 200 and len(resp.content) > CACHE_MIN_FILE_SIZE:
                        audio_bytes = resp.content
                        break
                    else:
                        logger.warning(f"[TTS] Murf Falcon endpoint {endpoint} status {resp.status_code}: {resp.text[:120]}")
                except Exception as ep_err:
                    logger.debug(f"[TTS] Murf Falcon endpoint {endpoint} failed: {ep_err}")

            # Secondary fallback: Murf SDK generate()
            if not audio_bytes and self._murf_client:
                try:
                    res = self._murf_client.text_to_speech.generate(
                        text=payload_text,
                        voice_id=MURF_VOICE_ID,
                        style=MURF_STYLE,
                        locale=payload_locale,
                        model_version="GEN2",
                        format=MURF_FORMAT,
                        sample_rate=MURF_SAMPLE_RATE,
                        pitch=MURF_PITCH,
                    )
                    audio_url = getattr(res, "audio_file", None) or getattr(res, "audioFile", None)
                    if audio_url:
                        import urllib.request
                        urllib.request.urlretrieve(audio_url, tmp_path)
                        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                            with open(tmp_path, "rb") as f:
                                audio_bytes = f.read()
                except Exception as sdk_err:
                    logger.debug(f"[TTS] Murf SDK fallback failed: {sdk_err}")

            if audio_bytes:
                with open(tmp_path, "wb") as f:
                    f.write(audio_bytes)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > CACHE_MIN_FILE_SIZE:
                    self._play_with_lip_sync(tmp_path)
                    # Cache short phrases so they never hit the API again (credit saver)
                    if len(text.strip()) <= AUTO_CACHE_MAX_LEN:
                        _save_to_cache(text, tmp_path)
                    logger.info(f"[TTS] Murf Falcon 2.1 spoke: '{text[:50]}'")
                    self._safe_delete_temp(tmp_path)
                    return True

            return False
        except Exception as e:
            logger.error(f"[TTS] Murf Falcon 2.1 FAILED (voice={MURF_VOICE_ID}): {e} — falling back to Polly")
            return False
        finally:
            self._safe_delete_temp(tmp_path)

    def _prebuild_cache(self) -> None:
        """Pre-generate common phrases once at startup so they play from cache
        instantly and never consume Murf credits during conversation."""
        if not MURF_API_KEY:
            return
        import requests
        headers = {"api-key": MURF_API_KEY, "Content-Type": "application/json"}
        for phrase in PRECACHE_PHRASES:
            if self._interrupt_event.is_set():
                break
            if _is_cached(phrase):
                continue
            try:
                clean = self._strip_for_tts(phrase)
                payload = {
                    "voiceId": MURF_VOICE_ID,
                    "style": MURF_STYLE,
                    "model": MURF_MODEL,
                    "locale": MURF_LOCALE,
                    "text": clean,
                    "format": MURF_FORMAT,
                }
                for endpoint in MURF_FALCON_ENDPOINTS:
                    try:
                        resp = requests.post(endpoint, headers=headers, json=payload, timeout=8)
                        if resp.status_code == 200 and len(resp.content) > CACHE_MIN_FILE_SIZE:
                            tmp = tempfile.mktemp(suffix=".mp3")
                            with open(tmp, "wb") as f:
                                f.write(resp.content)
                            _save_to_cache(phrase, tmp)
                            self._safe_delete_temp(tmp)
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[TTS] Precache skip '{phrase}': {e}")
        logger.info("[TTS] Common phrases pre-cached (credit saver ready).")

    def _strip_for_tts(self, text: str) -> str:
        """Remove emojis/markdown/extra punctuation and expand acronyms before TTS (Murf)."""
        import re
        text = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]', '', text)
        text = re.sub(r'[*_~`#\[\]]', '', text)

        # Expand abbreviations and tech terms to Devanagari phonetics so Murf hi-IN never says "paa"
        murf_abbr = {
            "PC": "पीसी", "pc": "पीसी", "P.C.": "पीसी", "p.c.": "पीसी",
            "AI": "एआई", "ai": "एआई", "A.I.": "एआई", "a.i.": "एआई",
            "WiFi": "वाई-फ़ाई", "wifi": "वाई-फ़ाई", "Wi-Fi": "वाई-फ़ाई", "wi-fi": "वाई-फ़ाई",
            "TV": "टीवी", "tv": "टीवी", "T.V.": "टीवी",
            "OK": "ओके", "ok": "ओके", "okay": "ओके",
            "CPU": "सीपीयू", "cpu": "सीपीयू", "GPU": "जीपीयू", "gpu": "जीपीयू",
            "RAM": "रैम", "ram": "रैम", "ROM": "रोम", "rom": "रोम",
            "USB": "यूएसबी", "usb": "यूएसबी", "PDF": "पीडीएफ", "pdf": "पीडीएफ",
            "URL": "यूआरएल", "url": "यूआरएल",
            "GB": "जीबी", "gb": "जीबी", "MB": "एमबी", "mb": "एमबी", "KB": "केबी", "kb": "केबी",
            "YouTube": "यूट्यूब", "youtube": "यूट्यूब", "Google": "गूगल", "google": "गूगल",
            "Chrome": "क्रोम", "chrome": "क्रोम", "Spotify": "स्पॉटिफ़ाई", "spotify": "स्पॉटिफ़ाई",
            "WhatsApp": "व्हाट्सएप", "whatsapp": "व्हाट्सएप",
        }
        for abbr, expanded in murf_abbr.items():
            text = re.sub(r'\b' + re.escape(abbr) + r'\b', expanded, text)

        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _clean_for_tts(self, text: str) -> str:
        """
        Area 2: Normalize Hinglish text for Polly hi-IN generative voice.

        Strategy — keep ONE consistent Roman script (no Devanagari mixing):
        Polly's hi-IN generative engine reads Romanized Hinglish natively.
        Any Devanagari insertion creates script-boundary micro-pauses.
        We ONLY fix words Polly demonstrably mispronounces in Roman form:
          • Texting shorthand (nhi → nahi, kr → kar …)
          • Joined words (hogya → ho gaya, krdiya → kar diya …)
          • Common spelling variants Polly reads with English phonetics
          • Proper nouns / names spelled phonetically so Polly stresses
            the right syllable (Shweta → Shveta so Polly doesn't say "Shoo-weta")

        indic-transliteration library CANNOT be used here — its ITRANS scheme
        is for Sanskrit scholars, not Hinglish Roman. Test showed:
          "Shweta" → ष्वेत  (completely wrong)
          "Namaste" → णमस्ते  (wrong N consonant)
        The manual dict below is the correct production approach.
        """
        roman_fixes = {
            # ── texting shorthand ──────────────────────────────────────────
            "nhi":   "nahi",   "nyi":   "nahi",   "ni":    "nahi",
            "kr":    "kar",    "krna":  "karna",  "krke":  "kar ke",
            "krdo":  "kar do", "krdiya":"kar diya",
            "hu":    "hoon",   "hn":    "haan",   "ha":    "haan",
            "rha":   "raha",   "rhi":   "rahi",   "rhe":   "rahe",
            "gya":   "gaya",   "gyi":   "gayi",   "gye":   "gaye",
            "hogya": "ho gaya","hogyi": "ho gayi",
            "mt":    "mat",    "tb":    "tab",    "sb":    "sab",
            "kb":    "kab",    "kyu":   "kyun",   "q":     "kyun",
            "kaha":  "kahaan",
            # ── pronunciation fixes (Polly reads wrong in Roman) ───────────
            "acha":  "achha",  "accha": "achha",
            "thik":  "theek",  "thk":   "theek",
            "bajke": "baj kar","baje":  "baj gaye",
            "theek": "theek",  "haan":  "haan",   "nahi":  "nahi",
            "main":  "main",   "hoon":  "hoon",   "kar":   "kar",
            "bata":  "bata",   "bol":   "bol",    "sun":   "sun",
            "dekh":  "dekh",   "chal":  "chal",   "ruk":   "ruk",
            "aao":   "aao",    "jao":   "jao",    "karo":  "karo",
            "bolo":  "bolo",   "suno":  "suno",   "dekho": "dekho",
            "chalo": "chalo",  "ruko":  "ruko",   "aana":  "aana",
            "karna": "karna",  "bolna": "bolna",  "sunna": "sunna",
            "dekhna":"dekhna", "chalna":"chalna",
            "kya":   "kya",    "kaisa": "kaisa",  "kaise": "kaise",
            "kyun":  "kyun",   "kahan": "kahan",  "kab":   "kab",
            "kaun":  "kaun",   "kitna": "kitna",
            "bahut": "bahut",  "thoda": "thoda",  "zyada": "zyada",
            "sab":   "sab",    "kuch":  "kuch",   "abhi":  "abhi",
            "phir":  "phir",   "bas":   "bas",    "toh":   "toh",
            "aur":   "aur",    "lekin": "lekin",  "par":   "par",
            "agar":  "agar",   "warna": "warna",  "tabhi": "tabhi",
            # ── proper nouns — phonetic spelling so Polly stresses correctly ─
            # "Shweta" → Polly reads as "Shoo-weta" (w treated as English).
            # "Shveta" makes it say "Shve-ta" closer to correct Hindi stress.
            "shweta":  "Shveta",   "Shweta":  "Shveta",
            "prathamesh": "Prathaamesh",
            "aryan":   "Aryan",
            # ── tech / brand words ──────────────────────────────────────────
            "wifi":    "wai fai",  "WiFi":   "wai fai",
            "youtube": "yoo tyoob","YouTube": "yoo tyoob",
            "spotify": "Spotify",  "chrome":  "Chrome",
            "whatsapp":"WhatsApp",
        }

        words = text.split()
        result_words = []

        for w in words:
            prefix = ""
            suffix = ""
            while w and w[0] in '.,!?"\'-([{':
                prefix += w[0]
                w = w[1:]
            while w and w[-1] in '.,!?"\'-)]}.':
                suffix = w[-1] + suffix
                w = w[:-1]

            if not w:
                result_words.append(prefix + suffix)
                continue

            # Case-insensitive lookup, but prefer the exact-case entry first
            fixed = roman_fixes.get(w) or roman_fixes.get(w.lower())
            if fixed:
                # Only apply capitalization preservation for single-word replacements.
                # Multi-word phonetic replacements (e.g. "wai fai", "yoo tyoob") and
                # already-correct-case entries (e.g. "Shveta") stay exactly as written.
                if " " not in fixed and not fixed[0].isupper() and w[0].isupper():
                    fixed = fixed[0].upper() + fixed[1:]
                result_words.append(prefix + fixed + suffix)
            else:
                result_words.append(prefix + w + suffix)

        return " ".join(result_words)

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
            if self._soundfile_available:
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
        """
        Play audio file with real-time lip sync.
        Uses pygame.mixer for reliable playback (sounddevice cuts audio on some systems).
        Lip sync analysis runs in parallel using soundfile data.
        """
        import soundfile as sf

        # Load audio data for lip sync analysis
        lip_data = None
        lip_sr = None
        try:
            lip_data, lip_sr = sf.read(mp3_path, dtype='float32')
            if len(lip_data.shape) > 1:
                lip_data = lip_data.mean(axis=1)
        except Exception as e:
            logger.debug(f"[TTS] Could not read audio for lip sync: {e}")

        if self._interrupt_event.is_set():
            return

        # Reinit mixer to match THIS file's actual sample rate (Murf=44100, Polly=16000).
        # A fixed mixer rate that doesn't match the file plays it at the wrong speed/pitch.
        # Reading lip_sr from the file and matching it = zero speed/pitch artifacts.
        # Re-init each time also picks up output device changes (headphone plug/unplug).
        file_sr = int(lip_sr) if lip_sr else PYGAME_MIXER_FREQ
        try:
            import pygame
            cur = pygame.mixer.get_init()
            if cur is None or cur[0] != file_sr:
                if cur is not None:
                    pygame.mixer.quit()
                pygame.mixer.init(frequency=file_sr, size=-16, channels=1, buffer=2048)

            pygame.mixer.music.load(mp3_path)
            pygame.mixer.music.play()

            # Run lip sync in parallel with playback
            if self._lip_sync_callback and lip_data is not None:
                self._run_lip_sync(lip_data, lip_sr)

            # Wait for pygame to finish playing (poll with interrupt check)
            while pygame.mixer.music.get_busy():
                if self._interrupt_event.is_set():
                    pygame.mixer.music.stop()
                    return
                time.sleep(0.05)

        except ImportError:
            # pygame not available — fall back to sounddevice
            logger.warning("[TTS] pygame not available, using sounddevice fallback")
            self._play_sounddevice_fallback(mp3_path, lip_data, lip_sr)
        except Exception as e:
            logger.warning(f"[TTS] pygame playback failed: {e}, trying sounddevice")
            self._play_sounddevice_fallback(mp3_path, lip_data, lip_sr)

    def _play_sounddevice_fallback(self, mp3_path: str, data=None, samplerate=None) -> None:
        """Fallback to sounddevice if pygame unavailable."""
        import soundfile as sf
        import sounddevice as sd_play

        if data is None:
            try:
                data, samplerate = sf.read(mp3_path, dtype='float32')
                if len(data.shape) > 1:
                    data = data.mean(axis=1)
            except Exception as e:
                logger.warning(f"[TTS] Cannot decode audio: {e}, trying winsound")
                self._play_winsound(mp3_path)
                return

        if self._interrupt_event.is_set():
            return

        try:
            sd_play.play(data, samplerate, blocking=False)
        except Exception as e:
            logger.warning(f"[TTS] sounddevice play failed: {e}")
            self._play_winsound(mp3_path)
            return

        if self._lip_sync_callback:
            self._run_lip_sync(data, samplerate)

        if not self._interrupt_event.is_set():
            try:
                sd_play.wait()
            except Exception:
                pass
        else:
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

        if total_frames == 0:
            return

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

        # Play frames in real-time (synced with audio playback)
        start_time = time.time()
        lip_sync_failed = False

        for i, rms in enumerate(rms_values):
            if self._interrupt_event.is_set():
                break

            # Normalize to 0.0-1.0 range
            volume = min(1.0, (rms / max_rms) * 1.5)

            # Apply threshold (ignore very quiet)
            if volume < 0.05:
                volume = 0.0

            # Send to lip sync callback (don't break on exception — audio must continue)
            if not lip_sync_failed:
                try:
                    self._lip_sync_callback(volume)
                except Exception:
                    lip_sync_failed = True  # Stop trying lip sync but keep waiting for audio

            # Wait for next frame (sync with real-time playback)
            target_time = start_time + (i + 1) * frame_duration
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                if self._interrupt_event.wait(timeout=sleep_time):
                    break

        # Close mouth
        if self._lip_sync_callback and not lip_sync_failed:
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
