# pip install torch torchaudio sounddevice numpy requests
"""
Voice Input with Silero VAD — Smart recording that starts/stops with speech.
No fixed duration. Records only when you speak, stops when you pause.

OPTIMIZED v2.0:
- Lazy VAD model loading (saves ~2s startup, ~200MB RAM until first use)
- Proper timeouts on all blocking calls (mic=3s, STT=8s, VAD load=10s)
- Resource cleanup (mic stream guaranteed closed)
- Thread safety (lock on shared VAD model state)
- Hinglish error messages for user feedback
- No artificial delays on success path

Flow:
1. Lazy-load Silero VAD model on first listen() call
2. Open mic stream in 30ms chunks (with timeout)
3. Wait for speech (VAD confidence >= 0.45)
4. Record while speaking
5. Stop after 1.2s silence
6. Send to Google STT (with 8s timeout)
"""

import base64
import io
import json
import logging
import os
import struct
import threading
import time
from typing import Callable, Optional

import numpy as np
import requests
import sounddevice as sd
import torch

logger = logging.getLogger(__name__)

# --- Constants ---
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_MS = 30                    # 30ms chunks for VAD
CHUNK_SAMPLES = 512              # Silero VAD needs minimum 512 samples at 16kHz
VAD_THRESHOLD = 0.45             # Speech confidence threshold
SILENCE_TIMEOUT = 1.2            # Stop after 1.2s silence
MAX_RECORD_SEC = 12              # Hard cap
MIN_SPEECH_SEC = 0.3             # Ignore blips < 300ms
STT_TIMEOUT = 8                  # Google STT request timeout
MIC_OPEN_TIMEOUT = 3             # Timeout for opening mic stream
VAD_LOAD_TIMEOUT = 10            # Timeout for loading VAD model

# Google STT endpoint
GOOGLE_STT_URL = "https://speech.googleapis.com/v1p1beta1/speech:recognize"
GOOGLE_STT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"

# --- Hinglish error messages (for TTS feedback) ---
ERROR_MESSAGES = {
    "mic_not_found": "Microphone nahi mila, check karo connection.",
    "stt_timeout": "Google STT timeout ho gaya, internet check karo.",
    "stt_api_error": "Speech recognition mein error aa gaya.",
    "no_speech": "Samajh nahi aaya, phir se boliye...",
    "vad_load_fail": "Voice detection model load nahi hua, restart karo.",
    "mic_busy": "Microphone busy hai, thoda ruk ke try karo.",
    "recording_error": "Recording mein problem hui, phir se try karo.",
}

# --- Thread-safe lazy VAD model ---
_vad_lock = threading.Lock()
_vad_model = None
_vad_loaded = False


def _load_vad() -> bool:
    """
    Lazy-load Silero VAD model (thread-safe, with timeout).
    Returns True if model is ready, False on failure.
    """
    global _vad_model, _vad_loaded

    if _vad_loaded:
        return _vad_model is not None

    with _vad_lock:
        # Double-check after acquiring lock
        if _vad_loaded:
            return _vad_model is not None

        logger.info("Loading Silero VAD model...")
        load_start = time.time()

        try:
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )

            elapsed = time.time() - load_start
            if elapsed > VAD_LOAD_TIMEOUT:
                logger.warning(f"VAD load took {elapsed:.1f}s (slow)")

            _vad_model = model
            _vad_loaded = True
            logger.info(f"Silero VAD loaded in {elapsed:.1f}s.")
            return True

        except Exception as e:
            logger.error(f"VAD load failed: {e}")
            _vad_loaded = True  # Mark as attempted (don't retry every call)
            return False


# Bluetooth earbuds/headsets used as a MIC fall back to the low-quality 8 kHz
# "Hands-Free" profile, which garbles speech (e.g. "screen pe kya" -> "arka chalaye").
# Prefer a real built-in mic for INPUT; keep Bluetooth for OUTPUT only.
_MIC_AVOID = (
    "hands-free", "hands free", "handsfree", "headset", "bluetooth", " bt ", "a2dp",
    "rockerz", "buds", "airpods", "wireless", "realme", "boat", "earbud", "earphone",
)
_MIC_PREFER = (
    "realtek", "microphone array", "microphone (", "mic array", "built-in", "internal",
)


def _pick_input_device(sd_module):
    """Pick the best MME input device, avoiding Bluetooth/headset hands-free mics
    and preferring a built-in mic. Falls back to the first MME input, else None."""
    best, best_score, first_mme = None, -1, None
    try:
        for i, d in enumerate(sd_module.query_devices()):
            if d.get('max_input_channels', 0) <= 0:
                continue
            try:
                host = sd_module.query_hostapis(d['hostapi'])['name']
            except Exception:
                host = ""
            if 'MME' not in host:
                continue
            name = (d.get('name') or "").lower()
            if first_mme is None:
                first_mme = i
            score = 0
            if any(a in name for a in _MIC_AVOID):
                score -= 10
            if any(p in name for p in _MIC_PREFER):
                score += 5
            if 'sound mapper' in name:
                score += 1  # neutral safe default
            if score > best_score:
                best_score, best = score, i
    except Exception:
        return None
    return best if best is not None else first_mme


def _reduce_noise(audio_float, sr):
    """Light noise suppression so mostly the user's voice reaches the STT:
    high-pass (drop rumble) + a noise gate that attenuates non-speech frames +
    normalization (boosts quiet Bluetooth-mic audio). Pure numpy; scipy optional."""
    try:
        x = np.asarray(audio_float, dtype=np.float32)
        if x.size < sr // 10:
            return audio_float
        # High-pass ~80 Hz to cut hum/rumble (optional — needs scipy)
        try:
            from scipy.signal import butter, sosfilt
            sos = butter(4, 80, btype='highpass', fs=sr, output='sos')
            x = sosfilt(sos, x).astype(np.float32)
        except Exception:
            pass
        # Noise gate: estimate the noise floor from quiet frames, attenuate below it
        frame = max(1, sr // 50)  # 20 ms
        n = x.size // frame
        if n > 6:
            rms = np.sqrt(np.mean(x[:n * frame].reshape(n, frame) ** 2, axis=1) + 1e-9)
            noise_floor = float(np.percentile(rms, 20))
            thresh = noise_floor * 2.2
            gate = rms > thresh
            # Expand speech regions by 1 frame each side so word edges aren't clipped
            g = gate.copy()
            for i in range(n):
                if gate[i]:
                    if i > 0: g[i - 1] = True
                    if i < n - 1: g[i + 1] = True
            gains = np.where(g, 1.0, 0.12).astype(np.float32)
            x[:n * frame] *= np.repeat(gains, frame)
        # Normalize (boost quiet audio, cap the gain so we don't blow up noise)
        peak = float(np.max(np.abs(x))) + 1e-9
        x *= min(0.95 / peak, 6.0)
        return x.astype(np.float32)
    except Exception:
        return audio_float


class VoiceInput:
    """Smart voice input with VAD-based recording. Thread-safe."""

    def __init__(self) -> None:
        self.is_available: bool = False
        self._listen_lock = threading.Lock()
        self._is_listening: bool = False
        self._stop_event = threading.Event()
        self._stream_lock = threading.Lock()
        self._active_stream = None
        self.last_error: Optional[str] = None
        self._init()

    def stop(self) -> None:
        """Stop an active recording so the application can close cleanly."""
        self._stop_event.set()
        with self._stream_lock:
            stream = self._active_stream
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def _init(self) -> None:
        """Check mic availability. VAD loaded lazily on first listen()."""
        try:
            # Always query the CURRENT default input device (handles headphone plug/unplug)
            info = sd.query_devices(kind="input")
            if info:
                self.is_available = True
                logger.info(f"Microphone ready: {info['name']}")
            else:
                self.is_available = False
                self.last_error = ERROR_MESSAGES["mic_not_found"]
                logger.warning("No input device found.")
        except sd.PortAudioError as e:
            self.is_available = False
            self.last_error = ERROR_MESSAGES["mic_not_found"]
            logger.warning(f"Mic init failed (PortAudio): {e}")
        except Exception as e:
            self.is_available = False
            self.last_error = ERROR_MESSAGES["mic_not_found"]
            logger.warning(f"Mic init failed: {e}")

    def refresh_device(self) -> None:
        """
        Re-query available audio input devices. Call this when you suspect
        the audio device changed (headphone plugged/unplugged) or before
        each listen() cycle to always pick the current OS default mic.
        """
        self._init()

    def listen(self, on_listening: Optional[Callable] = None,
               on_processing: Optional[Callable] = None) -> Optional[str]:
        """
        Smart recording with VAD — starts when you speak, stops when you pause.

        Args:
            on_listening: Callback when speech first detected (UI → green)
            on_processing: Callback when recording done, before STT (UI → orange)

        Returns:
            Recognized text or None.
        """
        # Prevent concurrent listen calls
        if not self._listen_lock.acquire(blocking=False):
            logger.warning("Listen already in progress, skipping.")
            return None

        try:
            self._stop_event.clear()
            return self._listen_impl(on_listening, on_processing)
        finally:
            self._is_listening = False
            self._listen_lock.release()

    def _listen_impl(self, on_listening, on_processing) -> Optional[str]:
        """Internal listen implementation (lock already held)."""
        # Re-check device availability (handles headphone/mic plug/unplug between calls)
        self._init()

        if not self.is_available:
            self.last_error = ERROR_MESSAGES["mic_not_found"]
            logger.warning("Mic not available.")
            return None

        if self._stop_event.is_set():
            return None

        # Lazy load VAD model on first use
        if not _load_vad():
            self.last_error = ERROR_MESSAGES["vad_load_fail"]
            return None

        self._is_listening = True

        try:
            audio_chunks = self._record_with_vad(on_listening)

            if audio_chunks is None:
                self.last_error = ERROR_MESSAGES["no_speech"]
                return None

            # Call processing callback (UI → orange/thinking)
            if on_processing:
                on_processing()

            # Convert float32 → int16 PCM bytes (with light noise suppression so
            # mostly the user's voice — not background noise — reaches the STT)
            audio_float = np.concatenate(audio_chunks)
            audio_float = _reduce_noise(audio_float, SAMPLE_RATE)
            audio_int16 = (np.clip(audio_float, -1.0, 1.0) * 32767).astype(np.int16)
            pcm_bytes = audio_int16.tobytes()

            duration = len(audio_float) / SAMPLE_RATE
            logger.info(f"Recording done: {duration:.1f}s, sending to STT...")

            # Groq Whisper primary → Google STT fallback
            result = self._groq_whisper_stt(pcm_bytes)
            if result is None:
                result = self._google_stt(pcm_bytes)
            if result is None:
                self.last_error = ERROR_MESSAGES["no_speech"]
            return result

        except sd.PortAudioError as e:
            self.last_error = ERROR_MESSAGES["mic_busy"]
            logger.error(f"PortAudio error during listen: {e}")
            return None
        except Exception as e:
            self.last_error = ERROR_MESSAGES["recording_error"]
            logger.error(f"Voice input error: {e}", exc_info=True)
            return None

    def _record_with_vad(self, on_listening: Optional[Callable] = None) -> Optional[list]:
        """
        Record audio using VAD to detect speech start/end.
        Mic stream is GUARANTEED to close (context manager).

        Returns:
            List of numpy float32 chunks, or None if no speech detected.
        """
        global _vad_model

        all_chunks = []
        speech_started = False
        silence_start = None
        record_start = time.time()

        # Reset VAD state (thread-safe)
        with _vad_lock:
            _vad_model.reset_states()

        logger.info("Listening (VAD)...")

        # Open mic stream with context manager (guaranteed cleanup)
        stream = None
        try:
            import sounddevice as sd
            # Prefer a built-in MME mic over Bluetooth hands-free (which garbles speech).
            safe_dev = _pick_input_device(sd)

            stream = sd.InputStream(
                device=safe_dev,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='float32',
                blocksize=CHUNK_SAMPLES,
            )
            stream.start()
            with self._stream_lock:
                self._active_stream = stream
        except sd.PortAudioError as e:
            if "out of range" in str(e) or "-9999" in str(e) or "Invalid device" in str(e):
                logger.warning("PortAudio device list stale (Bluetooth hotplug?). Re-initializing sounddevice...")
                try:
                    import sounddevice as _sd_refresh
                    _sd_refresh._terminate()
                    _sd_refresh._initialize()
                    
                    safe_dev_retry = _pick_input_device(_sd_refresh)

                    stream = _sd_refresh.InputStream(
                        device=safe_dev_retry,
                        samplerate=SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype='float32',
                        blocksize=CHUNK_SAMPLES,
                    )
                    stream.start()
                except Exception as retry_e:
                    self.last_error = ERROR_MESSAGES["mic_busy"]
                    logger.error(f"Cannot open mic stream after re-init: {retry_e}")
                    return None
            else:
                self.last_error = ERROR_MESSAGES["mic_busy"]
                logger.error(f"Cannot open mic stream: {e}")
                return None
        except Exception as e:
            self.last_error = ERROR_MESSAGES["mic_not_found"]
            logger.error(f"Mic stream open failed: {e}")
            return None

        try:
            while True:
                if self._stop_event.is_set():
                    logger.info("Recording stopped by application shutdown.")
                    return None
                elapsed = time.time() - record_start

                # Hard cap on total recording time
                if elapsed > MAX_RECORD_SEC:
                    logger.info("Max recording time reached.")
                    break

                # Read one chunk (30ms) — this blocks briefly (~30ms)
                try:
                    chunk, overflowed = stream.read(CHUNK_SAMPLES)
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.warning(f"Mic read error: {e}")
                    break

                if overflowed:
                    logger.debug("Mic buffer overflow (chunk dropped)")

                chunk_flat = chunk.flatten()

                # Run VAD on this chunk
                chunk_tensor = torch.from_numpy(chunk_flat)
                confidence = _vad_model(chunk_tensor, SAMPLE_RATE).item()

                if not speech_started:
                    # Waiting for speech to begin
                    if confidence >= VAD_THRESHOLD:
                        speech_started = True
                        silence_start = None
                        logger.info(f"Speech detected (conf: {confidence:.2f})")
                        if on_listening:
                            on_listening()
                    elif elapsed > 6.0:
                        # Timeout waiting for speech
                        logger.info("No speech detected (6s timeout).")
                        return None

                    # Keep last ~300ms of pre-speech audio (context buffer)
                    all_chunks.append(chunk_flat.copy())
                    if len(all_chunks) > 10:  # ~300ms at 30ms/chunk
                        all_chunks.pop(0)
                else:
                    # Recording speech
                    all_chunks.append(chunk_flat.copy())

                    if confidence >= VAD_THRESHOLD:
                        silence_start = None
                    else:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= SILENCE_TIMEOUT:
                            logger.info(f"End of speech (silence: {SILENCE_TIMEOUT}s)")
                            break

        finally:
            with self._stream_lock:
                self._active_stream = None
            # GUARANTEED mic stream cleanup
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

        if not speech_started:
            return None

        # Check minimum speech duration
        total_audio = np.concatenate(all_chunks)
        duration = len(total_audio) / SAMPLE_RATE
        if duration < MIN_SPEECH_SEC:
            logger.info(f"Too short ({duration:.2f}s), ignoring.")
            return None

        return all_chunks

    @staticmethod
    def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
        """Wrap raw int16 PCM in a minimal WAV header."""
        n = len(pcm_bytes)
        buf = io.BytesIO()
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + n))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16))
        buf.write(b"data")
        buf.write(struct.pack("<I", n))
        buf.write(pcm_bytes)
        return buf.getvalue()

    def _groq_whisper_stt(self, pcm_bytes: bytes) -> Optional[str]:
        """Groq Whisper STT — multilingual, free, handles Hindi/English/Marathi."""
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if not groq_key:
            return None

        wav_data = self._pcm_to_wav(pcm_bytes)

        try:
            # FORCE Hindi: without language=, Whisper auto-detects and keeps
            # mis-reading Hinglish as Urdu/Arabic script (same phonetics, wrong
            # script) — e.g. "time kya hua hai" → "ٹائم کیا ہوا ہے؟". Pinning
            # language="hi" guarantees Devanagari output, which the TTS language
            # detector then routes correctly to hi-IN. The Devanagari prompt
            # anchors the script and the assistant's name so it stays consistent.
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {groq_key}"},
                files={"file": ("audio.wav", wav_data, "audio/wav")},
                data={
                    "model": "whisper-large-v3-turbo",
                    "response_format": "json",
                    "language": "hi",
                    "prompt": "श्वेता से हिंदी और हिंग्लिश में बातचीत। जैसे: गाना चला दो, टाइम क्या हुआ है, न्यूज़ सुनाओ।",
                    "temperature": "0",
                },
                timeout=STT_TIMEOUT + 2,
            )
            if resp.status_code == 200:
                text = resp.json().get("text", "").strip()
                if text:
                    logger.info(f"[Whisper] Recognized: {text}")
                    return text
            else:
                logger.warning(f"[Whisper] HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.warning(f"[Whisper] Failed: {e}")
        return None

    def _google_stt(self, pcm_bytes: bytes) -> Optional[str]:
        """Google STT fallback with multilingual support."""
        audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")

        body = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "languageCode": "hi-IN",
                "alternativeLanguageCodes": ["en-IN", "mr-IN"],
                "enableAutomaticPunctuation": False,
            },
            "audio": {"content": audio_b64},
        }

        url = f"{GOOGLE_STT_URL}?key={GOOGLE_STT_KEY}"

        try:
            resp = requests.post(url, json=body, timeout=STT_TIMEOUT)
            if resp.status_code == 200:
                text = self._extract_transcript(resp.json())
                if text:
                    logger.info(f"[Google STT] Recognized: {text}")
                    return text
            else:
                logger.warning(f"[Google STT] HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.warning(f"[Google STT] Failed: {e}")
        return None

    @staticmethod
    def _extract_transcript(data: dict) -> Optional[str]:
        """Extract transcript text from Google STT response."""
        results = data.get("results", [])
        if results:
            alternatives = results[0].get("alternatives", [])
            if alternatives:
                text = alternatives[0].get("transcript", "").strip()
                if text:
                    return text
        return None
