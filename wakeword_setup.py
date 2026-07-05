import os
import json
import time
import queue

try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except ImportError:
    print("Error: Required libraries not found. Run 'pip install vosk sounddevice'")
    exit(1)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "assistant", "skills", "wakeword_config.json")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "assistant", "skills", "wakeword_models", "vosk-model-small-en-in-0.4")
TRIGGERS = ["shweta", "schweta", "shveta", "swetha", "sweta", "hey shweta", "oye shweta", "sun shweta"]

def main():
    print("="*60)
    print(" SHWETA WAKE WORD SETUP & DIAGNOSTIC TOOL ")
    print("="*60)
    print("This tool helps you select the correct microphone for the wake word.")
    print("Sometimes Windows sets 'Stereo Mix' or a virtual cable as default,")
    print("which prevents Shweta from hearing you in the background.\n")

    print("Loading Vosk Model (this takes a few seconds)...")
    if not os.path.exists(MODEL_PATH):
        print(f"ERROR: Model not found at {MODEL_PATH}")
        return

    model = Model(MODEL_PATH)
    print("Model loaded successfully!\n")

    print("Available Audio Devices:")
    devices = sd.query_devices()
    input_devices = []
    
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            input_devices.append(i)
            print(f"[{i}] {dev['name']}")

    print("\nWhich microphone do you want to use? (Type the number inside [])")
    while True:
        try:
            choice = int(input("Enter device number: "))
            if choice in input_devices:
                break
            print("Please enter a valid input device number.")
        except ValueError:
            print("Please enter a number.")

    print(f"\nTesting Microphone: {devices[choice]['name']}")
    print("Say 'Hey Shweta' to test if it works. Press Ctrl+C to stop and save.")
    print("-" * 50)

    q = queue.Queue()

    def callback(indata, frames, time, status):
        if status:
            pass
        q.put(bytes(indata))

    try:
        rec = KaldiRecognizer(model, 16000)
        with sd.RawInputStream(samplerate=16000, blocksize=4000, device=choice, dtype='int16',
                               channels=1, callback=callback):
            while True:
                data = q.get()
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = res.get("text", "").lower()
                    if any(t in text for t in TRIGGERS):
                        print(f"✅ WAKE WORD DETECTED! (Heard: '{text}')")
                else:
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").lower()
                    if any(t in text for t in TRIGGERS):
                        print(f"✅ WAKE WORD DETECTED! (Partial heard: '{text}')")
                        rec.Reset()
    except KeyboardInterrupt:
        print("\nTest stopped.")
    except Exception as e:
        print(f"\nError opening audio stream: {e}")
        return

    print("\nSaving configuration...")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump({"device_index": choice, "device_name": devices[choice]['name']}, f, indent=4)
    
    print(f"Saved! Shweta will now use [{devices[choice]['name']}] for the wake word.")
    print("You can close this window and start Shweta normally.")
    time.sleep(3)

if __name__ == "__main__":
    main()
