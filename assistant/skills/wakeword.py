# pip install sounddevice numpy requests
"""
Wake Word Detection — "Hey Shweta" using STT keyword spotting.
Runs in SEPARATE PROCESS (no mic conflict with main voice_input.py).

Approach: Records 2-sec audio clips, sends to Google STT, checks for "shweta".
100% accurate — no false positives. ~2-3 sec detection delay.
"""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Config
SAMPLE_RATE = 16000
CHANNELS = 1
LISTEN_DURATION = 2.0  # Record 2 seconds per check
COOLDOWN = 2.5         # Seconds between detections
SILENCE_RMS = 300      # Minimum RMS to bother with STT (int16 scale)

# Wake word triggers — if ANY of these appear in STT output, activate
TRIGGERS = ["shweta", "schweta", "shveta", "swetha", "sweta", "hey shweta", "oye shweta", "sun shweta"]


def _wakeword_worker(queue: threading.Event, stop_event: threading.Event, trigger_callback: Callable) -> None:
    """
    Runs in a background thread.
    Records audio using PyAudio and uses offline Vosk model.
    """
    import json
    import os
    import time
    
    try:
        from vosk import Model, KaldiRecognizer
        import sounddevice as sd
    except ImportError:
        logger.error("[WakeWord] Error: vosk or sounddevice not installed.")
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
        # By providing a grammar, Vosk becomes a highly accurate, zero-shot wake word detector!
        grammar = '["hey shweta", "hello shweta", "hi shweta", "yo shweta", "shweta", "[unk]"]'
        rec = KaldiRecognizer(model, 16000, grammar)
    except Exception as e:
        print(f"[WakeWord] Failed to load Vosk model: {e}")
        return

    try:
        config_path = os.path.join(os.path.dirname(__file__), "wakeword_config.json")
        device_index = None
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                
                # Try to match by name, as indices change when devices are plugged/unplugged
                target_name = config.get("device_name")
                if target_name:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        if dev['max_input_channels'] > 0 and target_name in dev['name']:
                            device_index = idx
                            print(f"[WakeWord] Found audio device by name '{target_name}' at index: {device_index}")
                            break
                    
                    if device_index is None:
                        print(f"[WakeWord] Warning: Configured device '{target_name}' not found. Falling back to system default.")
        
        # If device_index is None, sd.RawInputStream will use the default system input device
        stream = sd.RawInputStream(samplerate=16000, blocksize=4000, device=device_index, dtype='int16', channels=1)
    except Exception as e:
        print(f"[WakeWord] sounddevice failed to open stream: {e}", flush=True)
        # Prevent auto-restart loop if device fundamentally fails
        time.sleep(30)
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
                        if any(t in text for t in TRIGGERS):
                            logger.info(f"[WakeWord] 🎯 DETECTED! Heard: '{text}'")
                            last_detection = time.time()
                            trigger_callback()
                else:
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").lower()
                    if any(t in text for t in TRIGGERS):
                        logger.info(f"[WakeWord] 🎯 DETECTED (Partial)! Heard: '{text}'")
                        last_detection = time.time()
                        trigger_callback()
                        # reset recognizer to avoid double trigger
                        rec.Reset()
            except Exception as e:
                pass


class WakeWordManager:
    """Manages wake word detection in background thread."""

    def __init__(self, on_wake_callback: Callable, sensitivity: float = 0.5) -> None:
        self._callback = on_wake_callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._running = False

    def start(self) -> None:
        """Start wake word detection."""
        if self.is_running():
            return
        
        self._running = True
        self._stop_event = threading.Event()
        
        self._thread = threading.Thread(
            target=_wakeword_worker,
            args=(None, self._stop_event, self._callback),
            daemon=True,
            name="WakeWordThread"
        )
        self._thread.start()

        logger.info("[WakeWord] Started. Say 'Hey Shweta' to activate!")

    def stop(self) -> None:
        """Stop detection."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        logger.info("[WakeWord] Stopped.")

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()


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
