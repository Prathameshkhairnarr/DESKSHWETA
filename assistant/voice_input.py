# pip install torch torchaudio sounddevice numpy requests
"""
Voice Input with Silero VAD — Smart recording that starts/stops with speech.
No fixed duration. Records only when you speak, stops when you pause.

Flow:
1. Load Silero VAD model once at startup
2. Open mic stream in 30ms chunks
3. Wait for speech (VAD confidence >= 0.45)
4. Record while speaking
5. Stop after 1.2s silence
6. Send to Google STT
"""

import base64
import json
import logging
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

# Google STT endpoint (same key as before)
GOOGLE_STT_URL = "https://speech.googleapis.com/v1p1beta1/speech:recognize"
GOOGLE_STT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"

# --- Module-level VAD model (loaded once) ---
_vad_model = None
_vad_utils = None


def _load_vad():
    """Load Silero VAD model once and cache it."""
    global _vad_model, _vad_utils
    if _vad_model is not None:
        return

    logger.info("Loading Silero VAD model...")
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        trust_repo=True
    )
    _vad_model = model
    _vad_utils = utils
    logger.info("Silero VAD loaded.")


class VoiceInput:
    """Smart voice input with VAD-based recording."""

    def __init__(self) -> None:
        self.is_available: bool = False
        self._init()

    def _init(self) -> None:
        """Check mic and load VAD model."""
        try:
            info = sd.query_devices(kind="input")
            if info:
                self.is_available = True
                logger.info(f"Microphone ready: {info['name']}")
                # Load VAD model at startup
                _load_vad()
            else:
                logger.warning("No input device found.")
        except Exception as e:
            logger.warning(f"Mic init failed: {e}")

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
        if not self.is_available or _vad_model is None:
            logger.warning("Mic or VAD not available.")
            return None

        try:
            audio_chunks = self._record_with_vad(on_listening)

            if audio_chunks is None:
                return None

            # Call processing callback (UI → orange/thinking)
            if on_processing:
                on_processing()

            # Convert float32 → int16 PCM bytes
            audio_float = np.concatenate(audio_chunks)
            audio_int16 = (audio_float * 32767).astype(np.int16)
            pcm_bytes = audio_int16.tobytes()

            logger.info(f"Recording done: {len(audio_float)/SAMPLE_RATE:.1f}s, sending to STT...")

            # Send to Google STT
            return self._google_stt(pcm_bytes)

        except Exception as e:
            logger.error(f"Voice input error: {e}")
            return None

    def _record_with_vad(self, on_listening: Optional[Callable] = None) -> Optional[list]:
        """
        Record audio using VAD to detect speech start/end.

        Returns:
            List of numpy float32 chunks, or None if no speech detected.
        """
        global _vad_model

        all_chunks = []
        speech_started = False
        silence_start = None
        record_start = time.time()
        speech_duration = 0.0

        # Reset VAD state
        _vad_model.reset_states()

        logger.info("Listening (VAD)...")

        # Use blocking reads in a loop (simpler, thread-safe)
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype='float32', blocksize=CHUNK_SAMPLES) as stream:
            while True:
                elapsed = time.time() - record_start

                # Hard cap
                if elapsed > MAX_RECORD_SEC:
                    logger.info("Max recording time reached.")
                    break

                # Read one chunk (30ms)
                chunk, overflowed = stream.read(CHUNK_SAMPLES)
                chunk_flat = chunk.flatten()

                # Run VAD on this chunk
                # Silero expects torch tensor of shape (chunk_samples,)
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
                    # Still collect audio (for context)
                    # Keep last 300ms of pre-speech audio
                    all_chunks.append(chunk_flat.copy())
                    if len(all_chunks) > 10:  # ~300ms buffer
                        all_chunks.pop(0)
                else:
                    # Recording speech
                    all_chunks.append(chunk_flat.copy())
                    speech_duration = elapsed - (record_start + 0)

                    if confidence >= VAD_THRESHOLD:
                        # Still speaking
                        silence_start = None
                    else:
                        # Silence detected
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= SILENCE_TIMEOUT:
                            # 1.2s of silence — done
                            logger.info(f"End of speech (silence: {SILENCE_TIMEOUT}s)")
                            break

        if not speech_started:
            return None

        # Check minimum speech duration (ignore blips < 300ms)
        total_audio = np.concatenate(all_chunks)
        duration = len(total_audio) / SAMPLE_RATE
        if duration < MIN_SPEECH_SEC:
            logger.info(f"Too short ({duration:.2f}s), ignoring.")
            return None

        return all_chunks

    def _google_stt(self, pcm_bytes: bytes) -> Optional[str]:
        """
        Send PCM audio to Google Speech-to-Text API.
        Tries hi-IN first, falls back to en-IN.

        Args:
            pcm_bytes: Raw int16 PCM audio bytes.

        Returns:
            Recognized text or None.
        """
        # Encode audio as base64
        audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")

        # Request body
        body = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": SAMPLE_RATE,
                "languageCode": "hi-IN",
                "alternativeLanguageCodes": ["en-IN"],
                "enableAutomaticPunctuation": False,
            },
            "audio": {
                "content": audio_b64
            }
        }

        try:
            url = f"{GOOGLE_STT_URL}?key={GOOGLE_STT_KEY}"
            resp = requests.post(url, json=body, timeout=10)

            if resp.status_code != 200:
                logger.error(f"Google STT HTTP {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()

            # Extract transcript
            results = data.get("results", [])
            if results:
                alternatives = results[0].get("alternatives", [])
                if alternatives:
                    text = alternatives[0].get("transcript", "")
                    if text:
                        logger.info(f"Recognized: {text}")
                        return text

            # Fallback: try en-IN only
            body["config"]["languageCode"] = "en-IN"
            body["config"].pop("alternativeLanguageCodes", None)

            resp2 = requests.post(url, json=body, timeout=10)
            if resp2.status_code == 200:
                data2 = resp2.json()
                results2 = data2.get("results", [])
                if results2:
                    alts2 = results2[0].get("alternatives", [])
                    if alts2:
                        text2 = alts2[0].get("transcript", "")
                        if text2:
                            logger.info(f"Recognized (en): {text2}")
                            return text2

            logger.info("Could not understand audio.")
            return None

        except requests.Timeout:
            logger.error("Google STT timeout.")
            return None
        except Exception as e:
            logger.error(f"STT error: {e}")
            return None
