# SHWETA AI - VOICE ENGINE COMPLETE DOCUMENTATION

## File: `assistant/voice_output.py`

---

## 1. OVERVIEW (KYA HAI YE FILE)

Ye file Shweta AI ki "awaaz" hai. Jab bhi Shweta kuch bolta/bolti hai, ye file handle karti hai:
- Text ko audio mein convert karna (TTS - Text to Speech)
- Audio ko play karna speakers se
- Real-time lip sync (avatar ka muh hilana audio ke saath)
- Caching (ek baar generate kiya audio save karna taaki next time instant bole)
- Interruptible playback (naya command aaye toh purana audio turant band ho)

---

## 2. CURRENT TTS ENGINE SETUP

### PRIMARY: Amazon Polly Generative (Kajal Voice)
- **Engine:** `generative` (billion-parameter transformer model)
- **Voice ID:** `Kajal`
- **Language:** `hi-IN` (Hindi-India, bilingual — speaks Hindi + English naturally)
- **Output Format:** MP3
- **Quality:** Most human-like, emotionally engaged, colloquial speech
- **Limitation:** Available only in `us-east-1` region (may not work in other AWS regions)

### FALLBACK 1: Amazon Polly Neural (Kajal Voice)
- **Engine:** `neural`
- **Voice ID:** `Kajal`
- **Language:** `hi-IN`
- **Used when:** Generative engine unavailable in user's AWS region
- **SSML Applied:** `<prosody rate="108%" pitch="+18%">` (makes neural sound younger/feminine)

### FALLBACK 2: pyttsx3 (Offline - Last Resort)
- **Engine:** Windows SAPI5 (Microsoft Zira voice)
- **Used when:** Internet unavailable OR both Polly engines fail
- **Quality:** Robotic, basic, but works offline

---

## 3. ENVIRONMENT VARIABLES (.env FILE)

```
# Amazon AWS Credentials (for Polly TTS)
AWS_ACCESS_KEY_ID=your_aws_access_key_id_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key_here
AWS_REGION=us-east-1
```

**Note:** `SARVAM_API_KEY` is set to empty (disabled). Only Polly is active.

---

## 4. COMPLETE FUNCTION FLOW (STEP BY STEP)

### When `speak("Namaste! Main Shweta hoon.")` is called:

```
main.py calls → voice_output.speak(text)
                    ↓
            _interrupt() — purana audio band karo
                    ↓
            New thread start → _speak_thread(text, callback, voice)
                    ↓
            STEP 1: _is_cached(text) — cache mein hai?
                    ↓ (if YES → play cached audio)
                    ↓ (if NO → continue)
            STEP 2: _speak_polly(text) — Amazon Polly Generative
                    ↓
                _prepare_text_for_polly(text) — text clean + Hinglish→Devanagari
                    ↓
                _build_polly_ssml(clean_text) — SSML wrap karo
                    ↓
                polly_client.synthesize_speech(...) — AWS API call
                    ↓
                _pitch_shift_audio(tmp_path, 1.10) — pitch upar shift
                    ↓
                _play_with_lip_sync(play_path) — audio play + lip sync
                    ↓
                _save_to_cache(text, play_path) — cache mein save (short phrases only)
                    ↓
            STEP 3 (if Polly failed): _speak_pyttsx3(text) — offline fallback
                    ↓
            callback() — done signal to main.py
```

---

## 5. ALL FUNCTIONS - DETAILED DESCRIPTION

### 5.1 MODULE-LEVEL FUNCTIONS (Cache System)

#### `_text_to_cache_path(text: str) → Path`
- **Kya karta hai:** Text ko MD5 hash mein convert karke cache file path banata hai
- **Input:** `"theek hai"` → Output: `cache/tts_cache/a1b2c3d4...mp3`
- **Normalization:** lowercase + strip (so "Theek Hai" == "theek hai")

#### `_is_cached(text: str) → Optional[Path]`
- **Kya karta hai:** Check karta hai ki text ka audio already cached hai ya nahi
- **Returns:** Path to cached MP3 file, ya None
- **Validation:** File size > 500 bytes hona chahiye (corrupt files delete karta hai)
- **LRU tracking:** Access time update karta hai (purani files pehle delete hoti hain)

#### `_save_to_cache(text: str, mp3_path: str) → None`
- **Kya karta hai:** Generated audio file ko cache folder mein copy karta hai
- **Thread-safe:** Lock use karta hai (multiple threads safe)
- **Eviction:** Agar cache full hai toh purani files delete karta hai pehle

#### `_evict_if_needed() → None`
- **Kya karta hai:** Cache size check karke purani files delete karta hai
- **Limits:** Max 500 files, max 100MB total
- **Strategy:** Oldest 20% files ek saath delete (frequent eviction avoid)

#### `_get_cache_stats() → dict`
- **Kya karta hai:** Cache ka status return karta hai (files count, size)

---

### 5.2 CLASS: VoiceOutput

#### `__init__(self)`
- **Kya karta hai:** Polly client initialize karta hai boto3 se
- **Checks:**
  - AWS credentials available hain? → boto3.client create
  - soundfile available? (lip sync ke liye)
  - sounddevice available? (audio playback ke liye)
- **State variables:**
  - `is_speaking: bool` — currently speaking?
  - `_interrupt_event: threading.Event` — stop signal
  - `_polly_available: bool` — Polly ready?
  - `_lip_sync_callback: Optional[Callable]` — avatar ke liye callback

#### `set_lip_sync_callback(callback: Callable)`
- **Kya karta hai:** Lip sync callback set karta hai (avatar ka muh hilane ke liye)
- **Callback format:** `callback(volume: float)` where volume = 0.0 to 1.0
- **Called at:** 30fps during audio playback

#### `speak(text, language, voice, callback)`
- **Kya karta hai:** Main speak function — text bolna shuru karta hai
- **Parameters:**
  - `text` — bolna kya hai
  - `language` — (unused currently)
  - `voice` — custom voice (unused, for future)
  - `callback` — function to call when speaking done
- **Behavior:** Purana audio turant band karta hai, naya thread start karta hai

#### `stop()`
- **Kya karta hai:** Turant current speech band karta hai

#### `speak_reaction(text, intensity)`
- **Kya karta hai:** Quick reactions bolna (jab user avatar ko shake kare)
- **Intensity:** "calm", "normal", "surprised", "panicking", "screaming", "exhausted", "relieved"
- **Currently:** Intensity parameter ignored — directly Polly use hota hai

#### `_speak_reaction_impl(text, intensity)`
- **Kya karta hai:** Internal implementation of speak_reaction
- **Flow:** Polly try → fail? → pyttsx3

#### `_interrupt()`
- **Kya karta hai:** Current speech turant stop karta hai
- **Actions:**
  1. `_interrupt_event.set()` — signal to stop
  2. pygame.mixer.music.stop() — audio turant band
  3. Wait for current thread to finish (max 1 second)
  4. lip_sync_callback(0.0) — mouth close

---

### 5.3 AMAZON POLLY FUNCTIONS

#### `_speak_polly(text: str) → bool`
- **Kya karta hai:** Polly Generative engine se audio generate karta hai
- **COMPLETE FLOW:**
  1. `_prepare_text_for_polly(text)` — text clean karo
  2. `_build_polly_ssml(clean_text)` — SSML mein wrap karo
  3. `polly_client.synthesize_speech(...)` — AWS API call
  4. Response ka AudioStream file mein save karo (tmp .mp3)
  5. `_pitch_shift_audio(tmp_path, 1.10)` — pitch 10% upar shift
  6. `_play_with_lip_sync(play_path)` — play audio + lip sync
  7. Cache mein save karo (agar text <= 40 chars)
  8. Temp files delete karo
- **Error handling:** Agar "ValidationException" → neural fallback try
- **Returns:** True (success) / False (failed)

#### `_speak_polly_neural_fallback(text: str) → bool`
- **Kya karta hai:** Agar generative engine region mein available nahi hai toh neural use karta hai
- **SSML:** `<prosody rate="108%" pitch="+18%">` — thoda faster + higher pitch
- **Engine:** "neural" (instead of "generative")
- **No pitch shift applied** (SSML pitch handles it)

#### `_prepare_text_for_polly(text: str) → str`
- **Kya karta hai:** Text ko Polly ke liye clean/optimize karta hai
- **Steps:**
  1. Emojis remove (Polly can't pronounce them)
  2. Markdown formatting remove (`*bold*`, `_italic_`, etc.)
  3. Tech abbreviations expand: "CPU" → "C P U", "RAM" → "raam", "WiFi" → "why fy"
  4. `_clean_for_tts(text)` call — Hinglish words ko Devanagari mein convert
  5. Repeated punctuation clean: "..." → ".", "!!!" → "!"
  6. Multiple spaces remove

#### `_build_polly_ssml(text: str) → str`
- **Kya karta hai:** Text ko SSML format mein wrap karta hai Polly ke liye
- **Logic:**
  - XML characters escape: `&` → "and", `<` → remove, `>` → remove
  - Sentences split karo (`.!?।` ke baad)
  - Agar 1 sentence → `<speak>text</speak>`
  - Agar multiple sentences → each in `<s>sentence</s>` tags
- **IMPORTANT:** No `<break>` tags added — generative engine apni pacing khud handle karta hai
- **IMPORTANT:** No `<prosody>` tags — generative engine doesn't support pitch/rate SSML

#### `_clean_for_tts(text: str) → str`
- **Kya karta hai:** Romanized Hinglish words ko Devanagari script mein convert karta hai
- **WHY:** Polly ka hi-IN generative engine Devanagari ko proper Hindi phonetics se bolta hai, lekin Roman Hinglish ko English accent se pronounce karta hai
- **Example:**
  - Input: `"Namaste! Main Shweta hoon."`
  - Output: `"नमस्ते! मैं Shweta हूँ."`
  - "Namaste" → "नमस्ते" (proper Hindi pronunciation)
  - "Main" → "मैं" (not "main" as English word)
  - "Shweta" → stays as-is (proper noun, not in dictionary)
  - "hoon" → "हूँ" (proper Hindi)
- **Dictionary:** 200+ common Hinglish words mapped to Devanagari
- **Preserves:** Punctuation, English words (app names, tech terms), proper nouns
- **KNOWN ISSUE:** Mixed script (Devanagari + Roman in same sentence) CAN cause micro-pauses between words as Polly switches language context internally

---

### 5.4 AUDIO POST-PROCESSING

#### `_pitch_shift_audio(audio_path: str, pitch_factor: float = 1.10) → str`
- **Kya karta hai:** Audio ka pitch upar shift karta hai (more feminine/young sound)
- **Method:** numpy interpolation — audio samples ko resample karta hai
- **pitch_factor:** 1.10 = 10% higher pitch (subtle feminine boost)
- **How it works:**
  1. Audio file read karo (soundfile)
  2. Stereo → Mono convert
  3. Original samples ko fewer new samples mein interpolate karo
  4. Same sample rate pe play → sounds higher pitched
- **Output:** New WAV file (temp) — `original_pitched.wav`
- **Fallback:** If pitch shift fails → original audio use karo (no crash)
- **KNOWN ISSUE:** Pitch shift changes audio duration slightly (makes it ~10% shorter)

---

### 5.5 AUDIO PLAYBACK FUNCTIONS

#### `_play_with_lip_sync(mp3_path: str)`
- **Kya karta hai:** Audio file play karta hai + lip sync
- **Priority:** soundfile available? → `_play_sounddevice()` else → `_play_winsound()`
- **Interruptible:** `_interrupt_event` check hota hai throughout

#### `_play_sounddevice(mp3_path: str)`
- **Kya karta hai:** pygame.mixer se audio play karta hai + parallel lip sync analysis
- **COMPLETE FLOW:**
  1. soundfile se audio data load karo (for lip sync analysis)
  2. Stereo → Mono convert
  3. pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)
  4. pygame.mixer.music.load(mp3_path) + .play()
  5. `_run_lip_sync(lip_data, lip_sr)` — parallel lip sync
  6. Poll: `pygame.mixer.music.get_busy()` — wait till done
  7. Interrupt check: agar interrupt → `pygame.mixer.music.stop()`
- **Fallback:** pygame nahi hai → `_play_sounddevice_fallback()`

#### `_play_sounddevice_fallback(mp3_path, data, samplerate)`
- **Kya karta hai:** sounddevice library se directly audio play
- **Used when:** pygame unavailable
- **Non-blocking play** + lip sync + wait

#### `_run_lip_sync(data: np.ndarray, samplerate: int)`
- **Kya karta hai:** Real-time audio volume analysis for avatar mouth movement
- **Algorithm:**
  1. Audio ko 30fps frames mein divide karo (samplerate/30 samples per frame)
  2. Each frame ka RMS (Root Mean Square) amplitude calculate karo
  3. Normalize to 0.0-1.0 range
  4. Threshold apply: volume < 0.05 → 0.0 (mouth closed for silence)
  5. Lip sync callback ko volume value bhejo at 30fps
  6. Real-time sync: `time.sleep()` se audio playback ke saath sync
- **Interruptible:** `_interrupt_event.wait(timeout=sleep_time)` — turant break

#### `_play_winsound(mp3_path: str)`
- **Kya karta hai:** Last resort — subprocess se audio play
- **Priority:**
  1. `ffplay` (ffmpeg) — hidden window
  2. PowerShell `Media.SoundPlayer` — if ffplay not found
- **No lip sync** in this fallback
- **Interruptible:** proc.terminate() on interrupt

---

### 5.6 OFFLINE FALLBACK

#### `_speak_pyttsx3(text: str)`
- **Kya karta hai:** Windows built-in TTS engine use karta hai (offline)
- **Settings:** rate=200 (faster), volume=0.9, female voice (Zira)
- **Quality:** Robotic, basic — only used when internet/Polly completely unavailable
- **No lip sync** available

---

## 6. CACHE SYSTEM DETAILS

### Location: `project_root/cache/tts_cache/`
### Format: `{md5_hash_of_text}.mp3`

### Cache Rules:
- Max 500 files, max 100MB total size
- Only caches text <= 40 characters (short phrases)
- LRU eviction: oldest 20% files deleted when limit hit
- Minimum valid file size: 500 bytes (below = corrupt, auto-deleted)
- Thread-safe: `_cache_lock` threading.Lock used for all operations
- Cache key: `md5(f"{POLLY_VOICE_ID}:{POLLY_ENGINE}:{POLLY_LANGUAGE}:pitch{VOICE_PITCH_SEMITONES}|{text.lower().strip()}")` — the engine signature is baked into the hash so audio from a different engine/voice can never be matched (fixes the greeting voice-mismatch bug permanently)
- Each cached `.mp3` has a `.meta` sidecar recording the engine signature + source text

### Cache Benefit:
- First time: Polly API call (1-3 seconds latency)
- Cached: Instant playback (0ms latency, no API call, no cost)

---

## 7. AUDIO PLAYBACK CHAIN (Priority Order)

```
pygame.mixer (PRIMARY — most reliable on Windows)
    ↓ (if ImportError or failure)
sounddevice (SECONDARY — good but sometimes cuts audio)
    ↓ (if failure)
ffplay subprocess (TERTIARY — needs ffmpeg installed)
    ↓ (if FileNotFoundError)
PowerShell Media.SoundPlayer (LAST — basic, WAV only limitation)
```

---

## 8. THREADING MODEL

```
Main Thread (PyQt5 UI)
    ↓ speak() called
    ↓
Background Thread "TTS-Speak" (daemon=True)
    ├── API call to Polly (blocking, ~1-3 seconds)
    ├── Pitch shift (blocking, ~100ms)
    ├── Audio playback (blocking, duration of audio)
    │   └── Lip sync callback at 30fps (in same thread)
    └── callback() → signals main thread: speaking done

Interrupt: _interrupt_event.set() → all blocking operations check this and abort
```

---

## 9. KNOWN ISSUES & PROBLEMS

### Issue 1: Mixed Script Pauses — FIXED (2026-07)
- **Problem (was):** `_clean_for_tts()` converted some words to Devanagari but left English words in Roman, e.g. `"नमस्ते! मैं Shweta हूँ."` Polly re-evaluated language context at every script boundary and inserted a micro-pause each time → choppy Hinglish.
- **Fix applied:** `_clean_for_tts()` no longer converts to Devanagari at all. The whole sentence stays in ONE consistent Roman script (Polly's hi-IN generative engine reads Romanized Hinglish natively). It now only applies targeted Roman-script shorthand/pronunciation fixes (e.g. `nhi`→`nahi`, `mt`→`mat`, `kr`→`kar`). A debug log prints the exact SSML before every Polly call so accidental script-mixing is immediately visible.
- **Verified:** 6 mixed Hindi+English sentences produce zero Devanagari in the final SSML.

### Issue 2: Pitch Shift Mangled Pronunciation + Changed Duration — FIXED (2026-07)
- **Problem (was):** `_pitch_shift_audio(factor=1.10)` used naive `np.interp` resampling — it shifted pitch AND tempo together, deformed consonants/formants (smeared words), and shortened audio ~10% (broke lip-sync at the end).
- **Fix applied:** Replaced with `librosa.effects.pitch_shift` (phase vocoder). Duration is preserved exactly (measured ratio 1.0000 vs old 0.909) and only frequency shifts, so speech stays crisp and lip-sync stays aligned. If librosa is ever unavailable it returns the clean natural-pitch audio instead of falling back to the destructive resample.
- **Verified:** 220Hz test tone → 247Hz (expected 246.9Hz for +2 semitones), sample count unchanged (72000→72000).

### Issue 3: Cache Voice Mismatch (greeting sounded like a different girl) — FIXED (2026-07)
- **Problem (was):** `_text_to_cache_path()` hashed only the text, so audio generated by a previous engine (Edge-TTS/Sarvam) with the SAME text was matched and played back, mixing voices — most visible on the short, generic startup greeting.
- **Fix applied:** The cache hash now includes an engine signature — `md5(f"{voice}:{engine}:{lang}:pitch{semitones}|{text}")` via `CACHE_ENGINE_SIGNATURE`. Any change to voice/engine/language/pitch makes ALL old entries hash to different, unreachable keys — no manual wipe ever needed again. A `.meta` sidecar records which engine produced each file for auditability. The 50 stale files were also wiped once as cleanup.
- **Verified:** Same text under Polly vs a simulated Edge signature produces two different cache filenames.

### Issue 4: Generative Engine Region Limitation — mitigated
- **Problem:** Polly "generative" engine only available in `us-east-1`. Other regions get `ValidationException`.
- **Where:** `_speak_polly()` exception handling → falls back to neural.
- **Now:** Both engine paths apply the SAME perceptual pitch lift (`VOICE_PITCH_SEMITONES` for generative via librosa; the equivalent `VOICE_PITCH_SSML_PERCENT` for neural via SSML `<prosody>`), so a region fallback no longer changes the voice character.

### Issue 5: Intro Greeting Timing
- **Problem:** On startup, `"Namaste! Main Shweta hoon."` goes through full Polly pipeline (1-3 sec latency) the FIRST time. After that it is cached (correct voice now) and plays instantly.
- **Where:** `main.py` line ~152 → `voice_output.speak(greeting)`
- **Impact:** Slight delay before first greeting only on first-ever run.

### Issue 6: No Emotion/Intensity Control in Polly (still open)
- **Problem:** `speak_reaction(text, intensity)` receives intensity but Polly generative doesn't support prosody SSML, so reactions all sound the same intensity.
- **Where:** `_speak_reaction_impl()` — intensity parameter is currently ignored.
- **Impact:** Calm vs screaming reactions sound identical. (Not addressed in this pass.)

---

## 10. AMAZON POLLY API DETAILS

### Synthesize Speech Call:
```python
response = polly_client.synthesize_speech(
    Text=ssml_text,           # SSML formatted text
    TextType="ssml",          # Tell Polly we're sending SSML
    OutputFormat="mp3",       # Output as MP3 file
    VoiceId="Kajal",          # Indian Female voice
    Engine="generative",      # Generative (most human-like) engine
    LanguageCode="hi-IN",     # Hindi-India language code
)
```

### Response:
```python
response["AudioStream"]  # StreamingBody — read() gives raw MP3 bytes
```

### Polly Generative vs Neural:
| Feature | Generative | Neural |
|---------|-----------|--------|
| Quality | Most human-like | Good but slightly robotic |
| SSML Support | Minimal (only `<speak>`, `<s>`, `<break>`) | Full (`<prosody>`, `<emphasis>`, etc.) |
| Emotion | Auto-handles from text context | Needs SSML markup |
| Pacing | Auto natural pacing | Needs rate/pitch SSML |
| Availability | us-east-1 only | All regions |
| Cost | Same as neural | Same as generative |

### Polly Kajal Voice:
- **Type:** Bilingual (Hindi + English)
- **Gender:** Female
- **Engines:** Supports both generative and neural
- **Best for:** Hinglish (mixed Hindi-English) speech
- **Character:** Emotionally engaged, assertive, colloquial

---

## 11. POST-PROCESSING PIPELINE

```
Raw Polly MP3 (24kHz, mono, ~Kajal natural pitch)
    ↓
_pitch_shift_audio(factor=1.10)
    ↓
Read MP3 → numpy float32 array
    ↓
Resample: reduce sample count by 10% (via np.interp)
    ↓
Write to WAV file (pitched version)
    ↓
Play WAV through pygame/sounddevice
```

**Result:** Voice sounds ~10% higher pitched (more feminine/younger feel)

---

## 12. WHO CALLS WHAT (FROM OTHER FILES)

### main.py:
```python
self.voice_output = VoiceOutput()                                    # Initialize
self.voice_output.speak(text, callback=self._on_speaking_done)       # Normal speech
self.voice_output.speak_reaction(text)                               # Shake reactions
self.voice_output.set_lip_sync_callback(self._on_lip_sync)          # Lip sync connect
self.voice_output.stop()                                             # Force stop
self.voice_output.is_speaking                                        # Check state
```

### How main.py uses it for greeting:
```python
greeting = f"Namaste! Main {ASSISTANT_NAME} hoon."
self.voice_output.speak(greeting, callback=self._on_speaking_done)
```

### How avatar shake uses it:
```python
self.ui.set_speak_reaction_fn(lambda text: self.voice_output.speak_reaction(text))
```

---

## 13. DEPENDENCIES

| Package | Purpose | Required? |
|---------|---------|-----------|
| boto3 | AWS Polly API client | YES (for Polly) |
| numpy | Pitch shift calculation | YES (for pitch shift) |
| soundfile | Read audio for lip sync | YES (for lip sync) |
| pygame | Audio playback (primary) | RECOMMENDED |
| sounddevice | Audio playback (fallback) | OPTIONAL |
| pyttsx3 | Offline TTS (last resort) | OPTIONAL |

---

## 14. CONFIGURATION CONSTANTS

```python
# Polly Config
POLLY_VOICE_ID = "Kajal"           # Voice selection
POLLY_ENGINE = "generative"         # Engine type
POLLY_LANGUAGE = "hi-IN"           # Language code
AWS_REGION = "us-east-1"           # AWS region (generative only here)

# Cache Config
CACHE_MAX_FILES = 500              # Max cached audio files
CACHE_MAX_SIZE_MB = 100            # Max cache folder size
CACHE_MIN_FILE_SIZE = 500          # Min valid MP3 bytes (below = corrupt)
AUTO_CACHE_MAX_LEN = 40            # Only cache text <= 40 chars

# Voice Character (single source of truth — used by BOTH engine paths)
VOICE_PITCH_SEMITONES = 2.0        # +2 semitones youthful/feminine lift (librosa, generative path)
VOICE_PITCH_SSML_PERCENT = 12      # auto-derived equivalent for neural SSML <prosody pitch>
CACHE_ENGINE_SIGNATURE             # "Kajal:generative:hi-IN:pitch2.0" — baked into cache hash

# Audio Processing
PYGAME_FREQUENCY = 24000           # Mixer sample rate
PYGAME_BUFFER = 2048               # Audio buffer size
LIP_SYNC_FPS = 30                  # Lip sync update rate
# NOTE: pitch shift now uses librosa.effects.pitch_shift (phase vocoder, duration-preserving),
#       NOT the old np.interp resample. n_steps = VOICE_PITCH_SEMITONES.
```

---

## 15. FILE STRUCTURE SUMMARY

```
voice_output.py
│
├── Module-level constants (Polly config, cache config)
├── Module-level functions (cache utilities)
│   ├── _text_to_cache_path()
│   ├── _is_cached()
│   ├── _save_to_cache()
│   ├── _evict_if_needed()
│   └── _get_cache_stats()
│
└── class VoiceOutput
    ├── __init__()                    — Polly client setup
    ├── set_lip_sync_callback()       — connect avatar
    ├── speak()                       — PUBLIC: main speak entry
    ├── stop()                        — PUBLIC: stop speaking
    ├── speak_reaction()              — PUBLIC: quick reactions
    ├── _speak_reaction_impl()        — reaction internal
    ├── _interrupt()                  — stop current audio
    ├── _safe_delete_temp()           — cleanup helper
    ├── _speak_polly()                — Polly Generative call
    ├── _speak_polly_neural_fallback()— Polly Neural fallback
    ├── _prepare_text_for_polly()     — text preprocessing
    ├── _build_polly_ssml()           — SSML construction
    ├── _pitch_shift_audio()          — audio pitch up
    ├── _speak_thread()               — main speak logic thread
    ├── _clean_for_tts()              — Hinglish→Devanagari
    ├── _play_with_lip_sync()         — play + lip sync router
    ├── _play_sounddevice()           — pygame playback
    ├── _play_sounddevice_fallback()  — sounddevice playback
    ├── _run_lip_sync()               — RMS analysis at 30fps
    ├── _play_winsound()              — subprocess playback
    ├── _wait_interruptible()         — sleep with interrupt
    ├── _speak_pyttsx3()              — offline fallback
    └── __del__()                     — cleanup
```
