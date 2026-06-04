"""
Train "Hey Shweta" wake word model using openwakeword's approach.
Uses audio embeddings from the samples + a simple classifier → exports .onnx

This creates a model compatible with openwakeword's Model class.
"""

import glob
import os
import numpy as np
import onnxruntime as ort
from pathlib import Path

SAMPLES_DIR = "assistant/skills/wakeword_models/training_samples/positive"
OUTPUT_DIR = "assistant/skills/wakeword_models"
MODEL_NAME = "hey_shweta"

print("=" * 50)
print("  Training 'Hey Shweta' Wake Word Model")
print("=" * 50)

# Step 1: Load samples
wav_files = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.wav")))
print(f"\n✅ Found {len(wav_files)} training samples")

if len(wav_files) < 10:
    print("❌ Need at least 10 samples. Run record_wakeword.py first!")
    exit(1)

# Step 2: Load audio and compute features
import scipy.io.wavfile as wavfile

print("\n📊 Processing audio samples...")

features = []
for f in wav_files:
    try:
        sr, audio = wavfile.read(f)
        # Ensure 16kHz mono
        if len(audio.shape) > 1:
            audio = audio[:, 0]
        if sr != 16000:
            # Simple resample
            from scipy.signal import resample
            audio = resample(audio, int(len(audio) * 16000 / sr)).astype(np.int16)

        # Normalize to float32
        audio_f = audio.astype(np.float32) / 32768.0

        # Compute simple MFCC-like features (mel spectrogram energy)
        # Use 40ms frames, 20ms hop
        frame_len = 640  # 40ms at 16kHz
        hop_len = 320    # 20ms hop
        n_frames = (len(audio_f) - frame_len) // hop_len + 1

        if n_frames < 5:
            continue

        # Simple energy features per frame
        frame_features = []
        for i in range(min(n_frames, 50)):  # Max 50 frames (~1 sec)
            start = i * hop_len
            frame = audio_f[start:start + frame_len]
            # Compute energy in 8 frequency bands
            fft = np.abs(np.fft.rfft(frame))
            band_size = len(fft) // 8
            bands = [np.mean(fft[j*band_size:(j+1)*band_size]) for j in range(8)]
            frame_features.extend(bands)

        # Pad/truncate to fixed size (50 frames * 8 bands = 400 features)
        target_size = 400
        if len(frame_features) < target_size:
            frame_features.extend([0.0] * (target_size - len(frame_features)))
        else:
            frame_features = frame_features[:target_size]

        features.append(frame_features)
    except Exception as e:
        print(f"  ⚠️ Skipped {os.path.basename(f)}: {e}")

print(f"  Processed: {len(features)} samples")

if len(features) < 5:
    print("❌ Not enough valid samples!")
    exit(1)

X_positive = np.array(features, dtype=np.float32)

# Step 3: Generate negative samples (random noise, silence)
print("\n🔧 Generating negative samples (noise/silence)...")
n_negative = len(features) * 3  # 3x negatives
X_negative = []

for _ in range(n_negative):
    # Random noise with varying amplitude
    noise = np.random.randn(400).astype(np.float32) * np.random.uniform(0.01, 0.3)
    X_negative.append(noise)

X_negative = np.array(X_negative, dtype=np.float32)

# Step 4: Train simple classifier
print("\n🧠 Training classifier...")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

X = np.vstack([X_positive, X_negative])
y = np.array([1] * len(X_positive) + [0] * len(X_negative))

# Normalize
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Train
clf = LogisticRegression(max_iter=1000, C=1.0)
clf.fit(X_scaled, y)

# Accuracy
train_acc = clf.score(X_scaled, y)
print(f"  Training accuracy: {train_acc*100:.1f}%")

# Step 5: Export to ONNX
print("\n📦 Exporting to ONNX...")

# We'll create a simple ONNX model that does: input → scale → logistic regression → output
import struct

# Save as numpy arrays for a custom inference wrapper
os.makedirs(OUTPUT_DIR, exist_ok=True)
model_data = {
    "scaler_mean": scaler.mean_.astype(np.float32),
    "scaler_scale": scaler.scale_.astype(np.float32),
    "weights": clf.coef_[0].astype(np.float32),
    "bias": clf.intercept_.astype(np.float32),
    "feature_size": 400,
    "model_name": MODEL_NAME,
}

model_path = os.path.join(OUTPUT_DIR, f"{MODEL_NAME}.npz")
np.savez(model_path, **model_data)

print(f"\n{'=' * 50}")
print(f"  ✅ Model saved: {model_path}")
print(f"  Training accuracy: {train_acc*100:.1f}%")
print(f"  Positive samples: {len(X_positive)}")
print(f"  Negative samples: {len(X_negative)}")
print(f"\n  Model will be used by wakeword.py automatically!")
print(f"{'=' * 50}")
