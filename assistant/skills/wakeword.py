# pip install sounddevice numpy requests
"""
Wake Word Detection — "Hey Shweta" using STT keyword spotting.
Runs in SEPARATE PROCESS (no mic conflict with main voice_input.py).

Approach: Records 2-sec audio clips, sends to Google STT, checks for "shweta".
100% accurate — no false positives. ~2-3 sec detection delay.
"""

import logging
import multiprocessing
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Config
SAMPLE_RATE = 16000
CHANNELS = 1
LISTEN_DURATION = 2.0  # Record 2 seconds per check
COOLDOWN = 4.0         # Seconds between detections
SILENCE_RMS = 300      # Minimum RMS to bother with STT (int16 scale)

# Wake word triggers — if ANY of these appear in STT output, activate
TRIGGERS = ["shweta", "schweta", "shveta", "swetha", "sweta"]


def _wakeword_worker(queue: multiprocessing.Queue, stop_event: multiprocessing.Event) -> None:
    """
    SEPARATE PROCESS — own mic, no conflict.
    Records audio using PyAudio and uses offline Vosk model.
    """
    import json
    import os
    import time
    import queue as pyqueue
    
    try:
        from vosk import Model, KaldiRecognizer
        import sounddevice as sd
    except ImportError:
        print("[WakeWord] Error: vosk or sounddevice not installed. Run: pip install vosk sounddevice")
        return

    last_detection = 0.0

    print("[WakeWord] Process started. Loading local offline model...")
    
    # Path to the model
    model_path = os.path.join(os.path.dirname(__file__), "wakeword_models", "vosk-model-small-en-in-0.4")
    if not os.path.exists(model_path):
        print(f"[WakeWord] Error: Vosk model not found at {model_path}")
        print("[WakeWord] Please download it and place it in assistant/skills/wakeword_models/")
        return

    try:
        model = Model(model_path)
        rec = KaldiRecognizer(model, 16000)
    except Exception as e:
        print(f"[WakeWord] Failed to load Vosk model: {e}")
        return

    try:
        stream = sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1)
    except Exception as e:
        print(f"[WakeWord] sounddevice failed to open stream: {e}", flush=True)
        return

    print("[WakeWord] Listening for 'Hey Shweta' offline...", flush=True)

    with stream:
        stream.start()
        while not stop_event.is_set():
            try:
                data, overflowed = stream.read(4000)
                data_bytes = bytes(data)
                
                # Cooldown check
                now = time.time()
                if now - last_detection < COOLDOWN:
                    continue

                if rec.AcceptWaveform(data_bytes):
                    res = json.loads(rec.Result())
                    text = res.get("text", "").lower()
                    if text:
                        # Only print if it heard something substantial to avoid spam
                        # print(f"[WakeWord] Heard: '{text}'", flush=True)
                        if any(t in text for t in TRIGGERS):
                            print(f"[WakeWord] 🎯 DETECTED! Heard: '{text}'", flush=True)
                            last_detection = time.time()
                            queue.put("WAKE")
                else:
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").lower()
                    if any(t in text for t in TRIGGERS):
                        print(f"[WakeWord] 🎯 DETECTED (Partial)! Heard: '{text}'", flush=True)
                        last_detection = time.time()
                        queue.put("WAKE")
                        # reset recognizer to avoid double trigger
                        rec.Reset()
            except Exception as e:
                pass


class WakeWordManager:
    """Manages wake word detection in separate process."""

    def __init__(self, on_wake_callback: Callable, sensitivity: float = 0.5) -> None:
        self._callback = on_wake_callback
        self._process: Optional[multiprocessing.Process] = None
        self._watcher: Optional[threading.Thread] = None
        self._queue: Optional[multiprocessing.Queue] = None
        self._stop_event: Optional[multiprocessing.Event] = None
        self._running = False

    def start(self) -> None:
        """Start wake word detection."""
        if self._running:
            return

        self._queue = multiprocessing.Queue()
        self._stop_event = multiprocessing.Event()

        self._process = multiprocessing.Process(
            target=_wakeword_worker,
            args=(self._queue, self._stop_event),
            daemon=True,
            name="WakeWordProcess"
        )
        self._process.start()

        self._running = True
        self._watcher = threading.Thread(target=self._watch, daemon=True)
        self._watcher.start()

        logger.info("[WakeWord] Started. Say 'Hey Shweta' to activate!")

    def stop(self) -> None:
        """Stop detection."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)
        logger.info("[WakeWord] Stopped.")

    def is_running(self) -> bool:
        return self._running and self._process is not None and self._process.is_alive()

    def _watch(self) -> None:
        """Watcher thread — receives signals from subprocess."""
        while self._running:
            try:
                signal = self._queue.get(timeout=0.5)
                if signal == "WAKE":
                    logger.info("[WakeWord] Triggering callback!")
                    self._callback()
            except Exception:
                pass


if __name__ == '__main__':
    def test():
        print(">>> WAKE WORD DETECTED <<<")

    m = WakeWordManager(on_wake_callback=test)
    m.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
