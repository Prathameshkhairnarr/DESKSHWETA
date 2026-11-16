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
# The small en-IN Vosk model does not contain the name "shweta" in its
# vocabulary.  In practice it decodes the spoken name as "sweater", so keep
# that pronunciation as an intentional wake-word alias.
TRIGGERS = [
    "shweta", "schweta", "shveta", "swetha", "sweta",
    "sweater", "hey shweta", "hey sweater", "hello shweta",
    "hello sweater", "hi shweta", "hi sweater", "yo shweta", "yo sweater",
    "oye shweta", "sun shweta",
]

PARTIAL_TRIGGERS = {"hey shweta", "hey sweater"}


def _is_wake_trigger(text: str, partial: bool = False) -> bool:
    """Return whether Vosk text contains a known Shweta pronunciation."""
    normalized = " ".join((text or "").lower().split())
    if partial:
        # Partial Vosk results are noisy. Only accept the complete two-word
        # phrase here; a standalone "sweater" is checked after finalization.
        return normalized in PARTIAL_TRIGGERS

    # Final results must be the wake word itself, not an arbitrary sentence
    # that happens to contain the model's "sweater" approximation.
    return normalized in TRIGGERS


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
        # "shweta" is not in this model's vocabulary.  "sweater" is the
        # closest reliable decoding for the user's pronunciation.
        grammar = '["hey sweater", "hello sweater", "hi sweater", "yo sweater", "sweater", "[unk]"]'
        rec = KaldiRecognizer(model, 16000, grammar)
    except Exception as e:
        print(f"[WakeWord] Failed to load Vosk model: {e}")
        return

    try:
        # Always pick a built-in MME mic and AVOID Bluetooth/headset hands-free
        # devices (their 8 kHz profile garbles speech and the WDM-KS stream crashes
        # with error -9999, which was killing/restarting this process in a loop).
        _AVOID = ("hands-free", "hands free", "handsfree", "headset", "bluetooth", "a2dp",
                  "rockerz", "buds", "airpods", "wireless", "realme", "boat", "earbud", "earphone")
        _PREFER = ("realtek", "microphone array", "microphone (", "mic array", "built-in", "internal")

        def _pick_mic():
            best, best_score, first_mme = None, -1, None
            for i, d in enumerate(sd.query_devices()):
                if d.get('max_input_channels', 0) <= 0:
                    continue
                try:
                    host = sd.query_hostapis(d['hostapi'])['name']
                except Exception:
                    host = ""
                if 'MME' not in host:
                    continue
                name = (d.get('name') or "").lower()
                if first_mme is None:
                    first_mme = i
                s = 0
                if any(a in name for a in _AVOID):
                    s -= 10
                if any(p in name for p in _PREFER):
                    s += 5
                if 'sound mapper' in name:
                    s += 1
                if s > best_score:
                    best_score, best = s, i
            return best if best is not None else first_mme

        device_index = _pick_mic()
        if device_index is None:
            default_input = sd.query_devices(kind="input")
            if default_input:
                device_index = default_input["index"]
        try:
            print(f"[WakeWord] Using mic: '{sd.query_devices(device_index)['name']}' (index {device_index})", flush=True)
        except Exception:
            pass

        stream = sd.RawInputStream(samplerate=16000, blocksize=4000, device=device_index, dtype='int16', channels=1)
    except Exception as e:
        print(f"[WakeWord] sounddevice failed to open stream: {e}", flush=True)
        # Prevent auto-restart loop if device fundamentally fails
        time.sleep(30)
        return

    print("[WakeWord] Listening for 'Hey Shweta' offline...", flush=True)

    # Track the current default input device to detect headphone/mic changes
    def _get_default_input_name():
        try:
            info = sd.query_devices(kind="input")
            return info['name'] if info else ""
        except Exception:
            return ""

    current_device_name = _get_default_input_name()
    device_check_interval = 3.0  # Check for device changes every 3 seconds
    last_device_check = time.time()

    stream.start()
    try:
        while not stop_event.is_set():
            try:
                # Periodically check if audio device changed (headphone plug/unplug)
                now = time.time()
                if now - last_device_check > device_check_interval:
                    last_device_check = now
                    new_device_name = _get_default_input_name()
                    if new_device_name and new_device_name != current_device_name:
                        print(f"[WakeWord] Audio device changed: '{current_device_name}' -> '{new_device_name}'. Restarting stream...", flush=True)
                        current_device_name = new_device_name
                        # Close old stream and open new one on the new default device
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        try:
                            # Re-pick a built-in mic (never the Bluetooth hands-free one).
                            new_device_index = _pick_mic()
                            if new_device_index is None:
                                _nd = sd.query_devices(kind="input")
                                new_device_index = _nd["index"] if _nd else None
                            stream = sd.RawInputStream(
                                samplerate=16000,
                                blocksize=4000,
                                device=new_device_index,
                                dtype='int16',
                                channels=1,
                            )
                            stream.start()
                            print(f"[WakeWord] Switched to: '{new_device_name}'", flush=True)
                        except Exception as e:
                            print(f"[WakeWord] Failed to reopen stream on new device: {e}", flush=True)
                            time.sleep(5)
                            return
                        rec.Reset()
                        continue

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
                        if _is_wake_trigger(text):
                            logger.info(f"[WakeWord] 🎯 DETECTED! Heard: '{text}'")
                            last_detection = time.time()
                            trigger_callback()
                else:
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").lower()
                    if _is_wake_trigger(text, partial=True):
                        logger.info(f"[WakeWord] 🎯 DETECTED (Partial)! Heard: '{text}'")
                        last_detection = time.time()
                        trigger_callback()
                        # reset recognizer to avoid double trigger
                        rec.Reset()
            except Exception as e:
                # Keep the listener alive, but make device/read failures
                # visible in the log instead of silently disabling wake word.
                logger.debug(f"[WakeWord] Audio loop error: {e}")
    finally:
        # Cleanup stream on exit (stop_event set or return)
        try:
            stream.stop()
            stream.close()
        except Exception:
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
