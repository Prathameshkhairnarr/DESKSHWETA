# Shweta AI — Full Testing Checklist

Har test ke baad terminal logs dekho. Tick karo jo pass ho, cross jo fail.

---

## 1. VOICE & STT (Speech Recognition)

| # | Bolna hai | Expected | Pass? |
|---|-----------|----------|-------|
| 1.1 | "Hey Shweta" (wake word) | Wake word detect ho, listening shuru | |
| 1.2 | Ctrl+Shift+A (hotkey) | Listening shuru without wake word | |
| 1.3 | Hindi: "श्वेता टाइम बताओ" | Whisper Devanagari mein recognize kare | |
| 1.4 | English: "What is the time?" | Whisper English mein recognize kare | |
| 1.5 | Hinglish: "Shweta weather batao" | Whisper correctly recognize kare | |
| 1.6 | Silence (kuch mat bolo 6 sec) | "No speech detected" timeout | |

---

## 2. TTS & PRONUNCIATION

| # | Trigger | Expected | Pass? |
|---|---------|----------|-------|
| 2.1 | "Time batao" | "Abhi dopahar ke X bajke Y minute" — natural Hindi, NO letter spelling | |
| 2.2 | "What is the time?" | Same time reply, natural pronunciation | |
| 2.3 | "Open notepad" | "Main notepad khol rahi hoon" — smooth Hinglish | |
| 2.4 | "Mera naam kya hai?" | "Aapka naam Prathamesh hai" — naam sahi bole | |
| 2.5 | Long reply test (news) | No garbled audio, no letter-by-letter reading | |

---

## 3. NEWS (Language Matching)

| # | Bolna hai | Expected | Pass? |
|---|-----------|----------|-------|
| 3.1 | Hindi: "Aaj ki khabar sunao" | Hindi news, "Pehli khabar... Doosri khabar..." format | |
| 3.2 | English: "Tell me the news" | English news, "First... Second... Third..." format | |
| 3.3 | Check: no "1. 2. 3." numbers | Natural connectors, no numbered list | |
| 3.4 | Check: no "- India Today" source names | Source names stripped | |

---

## 4. ACTIONS (Desktop Control)

| # | Bolna hai | Expected | Pass? |
|---|-----------|----------|-------|
| 4.1 | "Open notepad" | Notepad khule | |
| 4.2 | "Open calculator" | Calculator khule | |
| 4.3 | "Take screenshot" | Screenshot save ho | |
| 4.4 | "Volume up" | Volume badhe | |
| 4.5 | "Lock screen" | Screen lock ho (careful!) | |
| 4.6 | "What's the weather?" | Weather info bole | |
| 4.7 | "What's the date?" | Aaj ki date bole | |
| 4.8 | "Battery kitni hai?" | Battery percentage bole | |
| 4.9 | "Close notepad" | Notepad band ho | |
| 4.10 | "Play lofi music on YouTube" | YouTube mein lofi play ho | |

---

## 5. CHAT & PERSONALITY

| # | Bolna hai | Expected | Pass? |
|---|-----------|----------|-------|
| 5.1 | "Hey Shweta, how are you?" | Friendly reply, no action | |
| 5.2 | "Kya kar rahi hai?" | Casual Hinglish reply | |
| 5.3 | "Tell me a joke" | Short joke, happy emotion | |
| 5.4 | "Mera naam yaad rakh — Prathamesh" | remember_user_info action fire | |
| 5.5 | "Kaun banaya tujhe?" | "Prathamesh aur Aryan" reply | |

---

## 6. SPEED & LATENCY

| # | Test | Expected | Pass? |
|---|------|----------|-------|
| 6.1 | Chat reply (smalltalk) | < 3 seconds total | |
| 6.2 | Single action (time/date) | < 4 seconds total | |
| 6.3 | News fetch | < 6 seconds total | |
| 6.4 | No agent loop for chat | Logs show NO "[Loop]" for simple chat | |

---

## 7. ERROR HANDLING

| # | Test | Expected | Pass? |
|---|------|----------|-------|
| 7.1 | Gibberish/noise input | "Samajh nahi aaya" or graceful fallback | |
| 7.2 | Very long sentence (20+ words) | multi_step intent, handles without crash | |
| 7.3 | Rapid double-tap mic | Second listen ignored (lock prevents) | |

---

## 8. AVATAR & UI

| # | Test | Expected | Pass? |
|---|------|----------|-------|
| 8.1 | Idle state | Avatar breathing animation | |
| 8.2 | Speaking state | Lip sync moving | |
| 8.3 | Happy emotion | Smile expression on face | |
| 8.4 | Thinking state | Think expression | |
| 8.5 | Chat bubble | Text bubble appears with reply | |

---

## LOG LINES TO CHECK

Terminal mein ye lines dikhni chahiye har interaction pe:

```
[Whisper] Recognized: <user text>
[Orchestrator] intent=<intent> text='<text>'
[Agent Hub] <agent>/<provider> completed in <X>s
[Response] agent=<agent> action=<action> emotion=<emotion> reply='<text>'
[Speaking] final_reply='<text>'
[TTS] Murf Falcon 2.1 request → voice=Pooja locale=<hi-IN|en-IN> | '<text>'
[TTS] Murf Falcon 2.1 spoke: '<text>'
```

Agar koi line missing hai ya error hai → note karo, baad mein fix karenge.

---

## HOW TO TEST

1. Start Shweta: `python main.py`
2. Har test ek ek karke bolo
3. Terminal logs dekho — `[Response]` aur `[Speaking]` lines check karo
4. Jo fail ho uska # note karo (e.g., "3.2 fail — English news mein Hindi aa raha")
5. Sab done hone pe batao kya kya fail hua
