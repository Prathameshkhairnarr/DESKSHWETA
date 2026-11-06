import threading
import logging
import time

logger = logging.getLogger(__name__)

class AudioHub:
    """Singleton manager for microphone access to prevent hardware conflicts."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AudioHub, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.current_owner = None
        self._hub_lock = threading.Lock()
        self._mic_released_cond = threading.Condition(self._hub_lock)
        self.preempt_requested = False

    def acquire_mic(self, owner: str, timeout: float = 3.0) -> bool:
        """Acquire the mic. Preempts 'wakeword' if needed."""
        with self._hub_lock:
            if self.current_owner == owner:
                return True
            
            if self.current_owner == "wakeword" and owner != "wakeword":
                logger.info(f"[AudioHub] {owner} needs mic. Preempting wakeword...")
                self.preempt_requested = True
                
                # Wait for wakeword to release it
                start_time = time.time()
                while self.current_owner == "wakeword":
                    if time.time() - start_time > timeout:
                        logger.error("[AudioHub] Timeout waiting for wakeword to release mic.")
                        return False
                    self._mic_released_cond.wait(timeout=0.5)
                    
            if self.current_owner is not None:
                logger.warning(f"[AudioHub] Mic conflict! {owner} tried to acquire but {self.current_owner} holds it.")
                return False
                
            self.current_owner = owner
            self.preempt_requested = False
            logger.info(f"[AudioHub] Mic granted to: {owner}")
            return True

    def release_mic(self, owner: str):
        """Release the microphone."""
        with self._hub_lock:
            if self.current_owner == owner:
                self.current_owner = None
                self.preempt_requested = False
                logger.info(f"[AudioHub] Mic released by: {owner}")
                self._mic_released_cond.notify_all()
            else:
                logger.warning(f"[AudioHub] {owner} tried to release mic but it is held by {self.current_owner}")

    def should_yield(self, owner: str) -> bool:
        """Check if current owner should yield the mic."""
        with self._hub_lock:
            return self.current_owner == owner and self.preempt_requested

    def wait_for_mic(self, timeout=None):
        """Block until the mic is free."""
        with self._hub_lock:
            if self.current_owner is None:
                return True
            self._mic_released_cond.wait(timeout)
            return self.current_owner is None
