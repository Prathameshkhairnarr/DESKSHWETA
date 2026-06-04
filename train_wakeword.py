# train_wakeword.py
# D:\Shweeta ai desk assistant\ mein rakh aur run kar
# Teri recorded samples se "Hey Shweta" model banayega

import os
import glob
import numpy as np
import scipy.io.wavfile as wav

SAMPLES_DIR  = "assistant/skills/wakeword_models/training_samples/positive"
OUTPUT_DIR   = "assistant/skills/wakeword_models"
MODEL_NAME   = "hey_shweta"
SAMPLE_RATE  = 16000

def load_samples():
    files = glob.glob(os.path.join(SAMPLES_DIR, "*.wav"))
    if not files:
        print(f"❌ Koi samples nahi mile: {SAMPLES_DIR}")
        print("   Pehle record_wakeword.py run karo!")
        return []
    print(f"✅ {len(files)} samples mile")
    return files

def check_openwakeword():
    try:
        import openwakeword
        print(f"✅ openwakeword version: {openwakeword.__version__}")
        return True
    except ImportError:
        print("❌ openwakeword install nahi hai")
        print("   Run: pip install openwakeword")
        return False

def train():
    print("=" * 55)
    print("  Shweta Wake Word Trainer")
    print("=" * 55)
    print()

    if not check_openwakeword():
        return

    files = load_samples()
    if not files:
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print()
    print("  Training start ho raha hai...")
    print("  (5-10 minute lag sakte hain pehli baar)")
    print()

    try:
        from openwakeword.train import train as oww_train

        oww_train(
            model_name=MODEL_NAME,
            positive_reference_clips=files,
            output_dir=OUTPUT_DIR,
            n_epochs=100,
            target_fp_rate=0.5,
        )

        model_path = os.path.join(OUTPUT_DIR, f"{MODEL_NAME}.onnx")
        if os.path.exists(model_path):
            print()
            print("=" * 55)
            print(f"  ✅ Model ready: {model_path}")
            print()
            print("  Ab wakeword.py mein yeh path use karo:")
            print(f'  MODEL_PATH = "{model_path}"')
            print("=" * 55)
        else:
            print("⚠️  Model file nahi mili — error check karo upar")

    except AttributeError:
        # Older openwakeword API fallback
        _train_fallback(files)
    except Exception as e:
        print(f"❌ Training error: {e}")
        print()
        _train_fallback(files)

def _train_fallback(files):
    """
    Agar openwakeword ka train API match nahi kiya toh
    yeh message dikhao — manual steps guide karega
    """
    print()
    print("=" * 55)
    print("  ⚠️  Auto-training API match nahi kiya")
    print()
    print("  Manual steps (2 min kaam):")
    print()
    print("  1. Yeh run karo:")
    print("     pip install openwakeword[training]")
    print()
    print("  2. Phir yeh run karo:")
    print(f"     oww-train --positive_clips {files[0].rsplit(os.sep,1)[0]}")
    print(f"               --model_name hey_shweta")
    print(f"               --output_dir {os.path.abspath('assistant/skills/wakeword_models')}")
    print()
    print("  3. .onnx file milegi wakeword_models/ mein")
    print("=" * 55)

if __name__ == "__main__":
    train()
