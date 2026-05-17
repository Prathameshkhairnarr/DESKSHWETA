"""
Voice Input — Records 4 seconds, sends to Google STT.
Simple and reliable approach that works on Python 3.14.
"""

import json
import logging
import time
from typing import Optional

import numpy as np
import requests
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
RECORD_SECONDS = 3  # Short recording for fast response


class VoiceInput:
    """Simple reliable mic recording + Google STT."""

    def __init__(self) -> None:
        self.is_available: bool = False
        self._init()

    def _init(self) -> None:
        try:
            info = sd.query_devices(kind="input")
            if info:
                self.is_available = True
                logger.info(f"Microphone ready: {info['name']}")
        except Exception as e:
            logger.warning(f"Mic init failed: {e}")

    def listen(self) -> Optional[str]:
        """Record 4 seconds and send to Google STT."""
        if not self.is_available:
            return None

        try:
            logger.info(f"Recording {RECORD_SECONDS}s...")

            audio = sd.rec(
                int(RECORD_SECONDS * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16"
            )
            sd.wait()

            audio_array = audio.flatten()
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            logger.info(f"Done. RMS: {rms:.0f}")

            if rms < 80:
                logger.info("Too quiet.")
                return None

            # Send to Google STT
            return self._recognize(audio_array)

        except Exception as e:
            logger.error(f"Voice input error: {e}")
            return None

    def _recognize(self, audio: np.ndarray) -> Optional[str]:
        """Send raw PCM to Google Speech API."""
        try:
            pcm_data = audio.tobytes()
            url = (
                "http://www.google.com/speech-api/v2/recognize"
                "?client=chromium&lang=hi-IN&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
            )
            headers = {"Content-Type": f"audio/l16; rate={SAMPLE_RATE};"}

            resp = requests.post(url, data=pcm_data, headers=headers, timeout=8)
            if resp.status_code != 200:
                return None

            for line in resp.text.strip().split("\n"):
                try:
                    data = json.loads(line)
                    if "result" in data and data["result"]:
                        alts = data["result"][0].get("alternative", [])
                        if alts:
                            text = alts[0].get("transcript", "")
                            logger.info(f"Recognized: {text}")
                            return text
                except json.JSONDecodeError:
                    continue
            return None
        except Exception as e:
            logger.error(f"STT error: {e}")
            return None
