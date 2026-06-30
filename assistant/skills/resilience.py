"""
Resilience & Fault Tolerance Module for Shweta AI
Provides production-grade decorators for skills to handle failures gracefully.
Features:
- Auto-retries for transient network/API failures.
- Circuit Breaker to prevent hanging the system if a service is down.
- Graceful fallbacks so the app never crashes.
"""

import functools
import logging
import time
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)

# Simple in-memory state for circuit breakers
# Key: skill_name, Value: {"failures": int, "last_failure_time": float}
_circuit_breaker_state = {}

def resilient_skill(retries: int = 2, delay: float = 1.0, circuit_breaker_threshold: int = 3, circuit_breaker_cooldown: float = 60.0):
    """
    Decorator to make any skill function highly resilient.
    
    Args:
        retries: Number of times to retry before giving up.
        delay: Delay in seconds between retries.
        circuit_breaker_threshold: Number of consecutive failures before opening the circuit.
        circuit_breaker_cooldown: Time in seconds to wait before trying an open circuit again.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, str]:
            skill_name = func.__name__
            state = _circuit_breaker_state.get(skill_name, {"failures": 0, "last_failure_time": 0.0})
            
            # Check Circuit Breaker
            if state["failures"] >= circuit_breaker_threshold:
                time_since_failure = time.time() - state["last_failure_time"]
                if time_since_failure < circuit_breaker_cooldown:
                    logger.warning(f"Circuit Breaker OPEN for skill '{skill_name}'. Skipping execution.")
                    return {"status": "error", "message": f"'{skill_name}' skill abhi unavailable hai (Circuit Open). Kuch der baad try karein."}
                else:
                    # Cooldown period passed, entering HALF-OPEN state (will try once)
                    logger.info(f"Circuit Breaker HALF-OPEN for skill '{skill_name}'. Trying again...")

            last_exception = None
            for attempt in range(retries + 1):
                try:
                    # Execute the skill
                    result = func(*args, **kwargs)
                    
                    # If successful, reset circuit breaker
                    if state["failures"] > 0:
                        _circuit_breaker_state[skill_name] = {"failures": 0, "last_failure_time": 0.0}
                        
                    # Ensure result is always a dictionary with status
                    if not isinstance(result, dict):
                        result = {"status": "success", "message": str(result) if result else "Done."}
                    if "status" not in result:
                        result["status"] = "success"
                        
                    return result

                except Exception as e:
                    last_exception = e
                    logger.warning(f"Skill '{skill_name}' attempt {attempt + 1}/{retries + 1} failed: {e}")
                    if attempt < retries:
                        time.sleep(delay)
            
            # If all retries failed, update circuit breaker
            state["failures"] += 1
            state["last_failure_time"] = time.time()
            _circuit_breaker_state[skill_name] = state
            
            logger.error(f"Skill '{skill_name}' failed completely after {retries + 1} attempts. Exception: {last_exception}", exc_info=True)
            return {"status": "error", "message": f"Kuch technical issue aa gaya: {str(last_exception)[:80]}"}

        return wrapper
    return decorator
