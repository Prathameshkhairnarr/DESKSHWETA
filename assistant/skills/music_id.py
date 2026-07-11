import logging
import os
import time

try:
    import soundcard as sc
    from ShazamAPI.algorithm import SignatureGenerator
    from ShazamAPI.api import Shazam
    import numpy as np
except ImportError:
    sc = None
    Shazam = None
    np = None

logger = logging.getLogger(__name__)

def identify_now_playing(duration: int = 6) -> str:
    if not sc or not Shazam or not np:
        return "Audio recording libraries installed nahi hain (soundcard/ShazamAPI missing)."
    
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass
        
    try:
        mics = sc.all_microphones(include_loopback=True)
        if not mics:
            return "Mujhe koi audio device nahi mili."
        
        default_speaker = sc.default_speaker().name
        loopback_mic = None
        for mic in mics:
            if mic.isloopback and default_speaker in mic.name:
                loopback_mic = mic
                break
        
        if not loopback_mic:
            for mic in mics:
                if mic.isloopback:
                    loopback_mic = mic
                    break
                    
        if not loopback_mic:
            return "System audio record karne ka access nahi hai (Loopback missing)."
            
        logger.info(f"Recording {duration}s of audio for Shazam from: {loopback_mic.name}")
        
        # Record raw audio
        data = loopback_mic.record(samplerate=16000, numframes=16000 * duration)
        
        # Convert stereo to mono by averaging channels
        if len(data.shape) > 1 and data.shape[1] > 1:
            data = data.mean(axis=1)
            
        # Convert float32 to int16 (which Shazam requires)
        data_int16 = (data * 32767).astype(np.int16)
        
        logger.info("Audio recorded, generating signature...")
        # Feed directly to SignatureGenerator (bypassing pydub/ffmpeg entirely)
        signature_generator = SignatureGenerator()
        signature_generator.feed_input(data_int16.tolist())
        signature_generator.MAX_TIME_SECONDS = duration + 2
        
        signature = signature_generator.get_next_signature()
        if not signature:
            return "Mujhe koi gaana samajh nahi aaya, shayad aawaz clear nahi hai."

        logger.info("Sending to Shazam API...")
        shazam = Shazam(b'')
        res = shazam.sendRecognizeRequest(signature)
        
        if 'track' in res:
            track = res['track']
            title = track.get("title", "Unknown Title")
            subtitle = track.get("subtitle", "Unknown Artist")
            return f"Yeh gaana hai: '{title}' by {subtitle}!"
        else:
            return "Mujhe koi gaana samajh nahi aaya, shayad yeh list me nahi hai."
            
    except Exception as e:
        logger.error(f"Shazam API bypass error: {e}")
        return "Main abhi gaana identify nahi kar pa rahi hu, kuch error aaya hai."
