# record_wakeword.py
# Seedha D:\Shweeta ai desk assistant\ mein rakh aur run kar
# pip install sounddevice scipy numpy

import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
import os, time, sys

# ── Config ──────────────────────────────────────────────────────
WAKE_WORD      = "Hey Shweta"
TOTAL_SAMPLES  = 50          # 50 samples kaafi hain openWakeWord ke liye
RECORD_SECS    = 2.0         # har sample 2 second ka
SAMPLE_RATE    = 16000
SILENCE_THRESH = 0.01        # isse kam volume = recording missed (too quiet)
OUTPUT_DIR     = "assistant/skills/wakeword_models/training_samples/positive"
# ────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_volume(audio):
    return np.abs(audio).mean()

def record_one(index):
    """Record one sample, return (audio, volume)"""
    audio = sd.rec(
        int(SAMPLE_RATE * RECORD_SECS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32'
    )
    sd.wait()
    volume = get_volume(audio)
    return audio, volume

def save_sample(audio, index):
    path = os.path.join(OUTPUT_DIR, f"hey_shweta_{index:03d}.wav")
    audio_int16 = (audio * 32767).astype(np.int16)
    wav.write(path, SAMPLE_RATE, audio_int16)
    return path

def draw_volume_bar(volume):
    """Visual volume bar — confirms audio captured"""
    bar_len = int(volume * 1000)
    bar_len = min(bar_len, 40)
    bar = "█" * bar_len + "░" * (40 - bar_len)
    label = "TOO QUIET ⚠️ " if volume < SILENCE_THRESH else "GOOD ✓      "
    print(f"  Volume: [{bar}] {label}")

def main():
    print("=" * 55)
    print(f"  Shweta Wake Word Recorder")
    print(f"  Bolna hai: \"{WAKE_WORD}\"")
    print(f"  Total samples: {TOTAL_SAMPLES}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 55)
    print()
    print("  Tips:")
    print("  - Mic se 30-40cm door raho")
    print("  - Clearly bolo, rush mat karo")
    print("  - Alag speed mein bolo (kabhi slow, kabhi normal)")
    print("  - 'TOO QUIET' aaye toh louder bolo ya mic check karo")
    print()

    saved = 0
    skipped = 0
    i = 0

    while saved < TOTAL_SAMPLES:
        i += 1
        print(f"  [{saved + 1:02d}/{TOTAL_SAMPLES}] 3 second mein bolo '{WAKE_WORD}'...")
        
        # Countdown
        for c in [3, 2, 1]:
            print(f"         {c}...", end="\r")
            time.sleep(0.6)
        
        print(f"  🎙️  AB BOLO!                    ")
        audio, volume = record_one(saved)
        
        # Visual feedback
        draw_volume_bar(volume)
        
        if volume < SILENCE_THRESH:
            print(f"  ⚠️  Bahut quiet tha — yeh sample skip kar raha hoon\n")
            skipped += 1
            # Don't increment saved — retry this sample
            time.sleep(0.5)
            continue
        
        path = save_sample(audio, saved)
        print(f"  💾 Saved: hey_shweta_{saved:03d}.wav\n")
        saved += 1
        time.sleep(0.4)

    print("=" * 55)
    print(f"  ✅ Done! {saved} samples saved.")
    if skipped > 0:
        print(f"  ℹ️  {skipped} quiet samples were skipped automatically.")
    print(f"  📁 Folder: {OUTPUT_DIR}")
    print()
    print("  Ab training ke liye bata — prompt deta hoon!")
    print("=" * 55)

if __name__ == "__main__":
    main()
