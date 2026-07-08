import logging
import os
import tempfile
import time
import io

try:
    import soundcard as sc
    import soundfile as sf
    from ShazamAPI.algorithm import SignatureGenerator
    from ShazamAPI.api import Shazam
    from pydub import AudioSegment
except ImportError:
    sc = None
    sf = None
    Shazam = None

logger = logging.getLogger(__name__)

def recognize_audio(file_path: str) -> str:
    if not Shazam:
        return "Shazam API is not installed properly."
    try:
        audio_bytes = open(file_path, 'rb').read()
        
        # Manually load WAV with format='wav' to bypass ffmpeg WinError 2
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format='wav')
        audio = audio.set_sample_width(2)
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        
        signature_generator = SignatureGenerator()
        signature_generator.feed_input(audio.get_array_of_samples())
        signature_generator.MAX_TIME_SECONDS = 8
        if audio.duration_seconds > 12 * 3:
            signature_generator.samples_processed += 16000 * (int(audio.duration_seconds / 16) - 6)

        signature = signature_generator.get_next_signature()
        if not signature:
            return "Mujhe koi gaana samajh nahi aaya, shayad aawaz clear nahi hai."

        shazam = Shazam(b'')
        res = shazam.sendRecognizeRequest(signature)
        
        if 'track' in res:
            track = res['track']
            title = track.get("title", "Unknown Title")
            subtitle = track.get("subtitle", "Unknown Artist")
            return f"Yeh gaana hai: '{title}' by {subtitle}!"
        else:
            return "Mujhe koi gaana samajh nahi aaya, aawaz clear nahi hai."
            
    except Exception as e:
        logger.error(f"Shazam API bypass error: {e}")
        return "Main abhi gaana identify nahi kar pa rahi hu, kuch error aaya hai."

def identify_now_playing(duration: int = 6) -> str:
    if not sc or not sf:
        return "Audio recording libraries installed nahi hain (soundcard/soundfile missing)."
    
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
            
        temp_dir = tempfile.gettempdir()
        temp_wav = os.path.join(temp_dir, f"shweta_shazam_{int(time.time())}.wav")
        samplerate = 48000
        
        logger.info(f"Recording {duration}s of audio for Shazam from: {loopback_mic.name}")
        with loopback_mic.recorder(samplerate=samplerate) as mic:
            data = mic.record(numframes=samplerate * duration)
            sf.write(temp_wav, data, samplerate)
            
        logger.info("Audio recorded, sending to Shazam API...")
        
        result = recognize_audio(temp_wav)
        
        try:
            os.remove(temp_wav)
        except Exception:
            pass
            
        return result
        
    except Exception as e:
        logger.error(f"Error recording audio for Shazam: {e}")
        return "Audio record karte waqt kuch gadbad ho gayi."
