"""
Wake Word Detection — "Hey Shweta" activates listening.
Uses continuous low-power mic monitoring + Google STT for wake word.
"""

import logging
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
WAKE_WORDS = ["hey shweta", "he shweta", "shweta", "hey swetha", "श्वेता"]


class WakeWordDetector:
    """Listens continuously for wake word "Hey Shweta"."""

    def __init__(self, on_wake: Optional[Callable] = None) -> None:
        """
        Args:
            on_wake: Callback when wake word detected.
        """
        self.on_wake = on_wake
        self._running = False
        self._thread = None

    def start(self) -> None:
        """Start wake word detection in background."""
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("Wake word detection started — say 'Hey Shweta'!")

    def stop(self) -> None:
        """Stop wake word detection."""
        self._running = False

    def _listen_loop(self) -> None:
        """Continuously listen for wake word."""
        import json
        import requests

        while self._running:
            try:
                # Record 2 seconds of audio
                audio = sd.rec(int(2 * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                               channels=1, dtype="int16")
                sd.wait()

                # Check if there's speech (not silence)
                rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
                if rms < 150:
                    continue  # Too quiet, skip

                # Send to Google STT
                pcm_data = audio.flatten().tobytes()
                url = (
                    "http://www.google.com/speech-api/v2/recognize"
                    "?client=chromium&lang=hi-IN&key=AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
                )
                headers = {"Content-Type": f"audio/l16; rate={SAMPLE_RATE};"}

                resp = requests.post(url, data=pcm_data, headers=headers, timeout=5)
                if resp.status_code != 200:
                    continue

                # Parse response
                text = ""
                for line in resp.text.strip().split("\n"):
                    try:
                        data = json.loads(line)
                        if "result" in data and data["result"]:
                            alts = data["result"][0].get("alternative", [])
                            if alts:
                                text = alts[0].get("transcript", "").lower()
                    except json.JSONDecodeError:
                        continue

                # Check for wake word
                if text and any(wake in text for wake in WAKE_WORDS):
                    logger.info(f"Wake word detected: '{text}'")
                    if self.on_wake:
                        self.on_wake()
                    # Wait a bit before listening again (avoid double trigger)
                    time.sleep(3)

            except Exception as e:
                logger.debug(f"Wake word loop error: {e}")
                time.sleep(1)
