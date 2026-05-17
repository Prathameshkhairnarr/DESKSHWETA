"""
Gesture Control — Hand gestures via webcam using MediaPipe new API.
Uses HandLandmarker for finger detection.

Gestures:
- 5 fingers (open palm) = Play/Pause
- 0 fingers (fist) = Mute
- 2 fingers (peace) = Next track
- 1 finger (index up) = Stop gesture control
- 3 fingers = Volume Up
- 4 fingers = Volume Down
"""

import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from config import PROJECT_ROOT

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = PROJECT_ROOT / "hand_landmarker.task"


def _ensure_model() -> bool:
    """Download hand landmarker model if not present."""
    if MODEL_PATH.exists():
        return True
    try:
        logger.info("Downloading hand landmarker model...")
        urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
        logger.info("Model downloaded.")
        return True
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        return False


class GestureController:
    """Webcam hand gesture recognition."""

    def __init__(self, on_gesture: Optional[Callable] = None) -> None:
        self.on_gesture = on_gesture
        self._running = False
        self._thread = None

    def start(self) -> dict:
        if self._running:
            return {"status": "success", "message": "Gesture control already on hai."}

        if not _ensure_model():
            return {"status": "error", "message": "Hand model download nahi ho paya."}

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Gesture control started.")
        return {"status": "success", "message": "Gesture control on! Haath dikhao camera ke saamne."}

    def stop(self) -> dict:
        self._running = False
        logger.info("Gesture control stopped.")
        return {"status": "success", "message": "Gesture control band kar diya."}

    def _run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            import numpy as np

            # Setup HandLandmarker
            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
            RunningMode = mp.tasks.vision.RunningMode

            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            landmarker = HandLandmarker.create_from_options(options)

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Camera not available.")
                self._running = False
                return

            last_gesture = ""
            last_time = 0
            cooldown = 1.5

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    break

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Convert to MediaPipe Image
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_image)

                gesture = None
                if result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    fingers = self._count_fingers(landmarks)
                    gesture = self._fingers_to_gesture(fingers)

                if gesture and gesture != last_gesture:
                    now = time.time()
                    if now - last_time > cooldown:
                        last_gesture = gesture
                        last_time = now
                        if self.on_gesture:
                            self.on_gesture(gesture)
                        logger.info(f"Gesture: {gesture}")

                # Small delay to reduce CPU usage
                time.sleep(0.05)

            cap.release()
            landmarker.close()
            self._running = False

        except Exception as e:
            logger.error(f"Gesture error: {e}")
            self._running = False

    def _count_fingers(self, landmarks) -> int:
        """Count raised fingers from hand landmarks."""
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]

        count = 0

        # Thumb (x comparison)
        if landmarks[tips[0]].x < landmarks[pips[0]].x:
            count += 1

        # Other fingers (y comparison — tip above pip)
        for i in range(1, 5):
            if landmarks[tips[i]].y < landmarks[pips[i]].y:
                count += 1

        return count

    def _fingers_to_gesture(self, fingers: int) -> Optional[str]:
        """Map finger count to gesture name."""
        mapping = {
            5: "play_pause",
            0: "mute",
            2: "next",
            3: "volume_up",
            4: "volume_down",
        }
        return mapping.get(fingers)
