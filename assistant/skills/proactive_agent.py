import logging
import threading
import time
import schedule

logger = logging.getLogger(__name__)

class ProactiveManager:
    """
    Background manager that periodically checks if there's anything important
    to notify the user about (weather, stock market, schedule).
    """

    def __init__(self, ai_brain, desktop_control, on_notify_callback):
        self.ai_brain = ai_brain
        self.desktop_control = desktop_control
        self.on_notify_callback = on_notify_callback
        self._running = False
        self._thread = None
        
        # Schedule the checks
        schedule.every(1).hours.do(self.check_proactive_events)
        
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ProactiveAgentThread")
        self._thread.start()
        logger.info("[ProactiveAgent] Started background notifications.")

    def stop(self):
        self._running = False
        
    def _run_loop(self):
        # We don't want to check right at startup (that's the daily briefing's job)
        # So we just run pending
        while self._running:
            schedule.run_pending()
            time.sleep(30)
            
    def check_proactive_events(self):
        """Called periodically to check for proactive notifications."""
        logger.info("[ProactiveAgent] Checking for proactive events...")
        try:
            # Let the AI brain decide if there's an alert based on current context
            # We construct a silent prompt
            prompt = (
                "You are Shweta, a professional and polite AI assistant. "
                "Check if there is something genuinely important to notify the user about right now "
                "(e.g. rain expected soon, a very large stock movement, an upcoming calendar reminder). "
                "If yes, reply with ONE short professional Hindi/Hinglish sentence — formal and helpful tone, "
                "no casual words like yaar/bhai/chal. Example: 'Aaj shaam baarish ki sambhavna hai.' "
                "If nothing urgent, reply ONLY with the word 'NONE'."
            )
            
            # Use ai_brain to think
            response = self.ai_brain.think(prompt, language_manager=self.desktop_control.language)
            reply = response.get("reply", "").strip()
            
            if reply and "none" not in reply.lower():
                logger.info(f"[ProactiveAgent] Found proactive notification: {reply}")
                self.on_notify_callback(reply)
            else:
                logger.info("[ProactiveAgent] No proactive notifications right now.")
                
        except Exception as e:
            logger.error(f"[ProactiveAgent] Error checking events: {e}")
