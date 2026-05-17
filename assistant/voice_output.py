"""
Voice Output — Hybrid approach for speed.
Short replies (<50 chars): pyttsx3 (INSTANT, 0 delay)
Long replies: Edge TTS streaming (natural voice, slight delay)
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import threading
from typing import Optional

from config import DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)

VOICE_PRIMARY = "en-IN-NeerjaNeural"
VOICE_FALLBACK = "hi-IN-SwaraNeural"

# Threshold: below this use instant offline TTS
INSTANT_THRESHOLD = 60


class VoiceOutput:
    """Hybrid TTS — instant for short, streaming for long."""

    def __init__(self) -> None:
        self.is_speaking: bool = False
        self._lock = threading.Lock()
        self._edge_available: bool = False
        self._pyttsx3_engine = None

        # Init pyttsx3 for instant responses
        try:
            import pyttsx3
            self._pyttsx3_engine = pyttsx3.init()
            voices = self._pyttsx3_engine.getProperty("voices")
            for v in voices:
                if "zira" in v.name.lower():
                    self._pyttsx3_engine.setProperty("voice", v.id)
                    break
            self._pyttsx3_engine.setProperty("rate", 180)
            self._pyttsx3_engine.setProperty("volume", 1.0)
        except Exception:
            pass

        try:
            import edge_tts
            self._edge_available = True
            logger.info("Edge-TTS initialized — using natural neural voices (FREE).")
        except ImportError:
            pass

    def speak(self, text: str, language: Optional[str] = None, callback=None) -> None:
        """Speak text — instant for short, streaming for long."""
        if not text:
            if callback:
                callback()
            return

        thread = threading.Thread(
            target=self._speak_thread,
            args=(text, callback),
            daemon=True
        )
        thread.start()

    def _speak_thread(self, text: str, callback) -> None:
        with self._lock:
            self.is_speaking = True
            try:
                if self._edge_available:
                    # Always use Edge TTS (natural voice)
                    self._speak_edge(text)
                else:
                    self._speak_pyttsx3(text)
            except Exception as e:
                logger.error(f"TTS error: {e}")
                try:
                    self._speak_pyttsx3(text)
                except Exception:
                    pass
            finally:
                self.is_speaking = False
                if callback:
                    callback()

    def _speak_pyttsx3(self, text: str) -> None:
        """Instant offline TTS — zero network delay."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for v in voices:
                if "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", 180)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            logger.error(f"pyttsx3 error: {e}")

    def _speak_edge(self, text: str) -> None:
        """Edge TTS for longer, natural sounding responses."""
        import edge_tts

        tmp_path = tempfile.mktemp(suffix=".mp3")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            for voice in [VOICE_PRIMARY, VOICE_FALLBACK]:
                try:
                    comm = edge_tts.Communicate(text, voice, rate="+30%", pitch="+0Hz")
                    loop.run_until_complete(comm.save(tmp_path))
                    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
                        break
                except Exception:
                    continue

            loop.close()

            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 500:
                self._play_audio(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _play_audio(self, filepath: str) -> None:
        """Play MP3 via PowerShell."""
        try:
            ps_cmd = (
                f'Add-Type -AssemblyName PresentationCore;'
                f'$p=New-Object System.Windows.Media.MediaPlayer;'
                f'$p.Open([Uri]::new("{filepath.replace(chr(92), "/")}"));'
                f'$p.Play();Start-Sleep -Milliseconds 300;'
                f'while($p.NaturalDuration.HasTimeSpan -eq $false){{Start-Sleep -Milliseconds 50}};'
                f'Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds - 100);'
                f'$p.Close()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, timeout=30
            )
        except Exception as e:
            logger.error(f"Play error: {e}")

    def stop(self) -> None:
        self.is_speaking = False
