"""
Hinglish (Roman) → Devanagari converter for Murf hi-IN TTS.

WHY THIS EXISTS:
Murf's hi-IN voice (Ayushi) pronounces Hindi naturally when given Devanagari script,
and pronounces English words (apps, computer terms, tech, UI, conversational English)
natively with an authentic Indian accent when kept in Latin/English.
When English words are transliterated phonetically into broken Devanagari
(e.g., 'Calculator' -> 'कलकुलतोर', 'Notepad' -> 'नोतेपद', 'system' -> 'सयसतेम'),
Murf synthesizes garbled, robotic gibberish.

ACCURACY RULES:
1. Exact WORD_MAP: Comprehensive dictionary of casual Hinglish words, pronouns,
   verbs, question words, greetings, adverbs, and particles.
2. ENGLISH_WORDS: Comprehensive whitelist of system, application, UI, Windows,
   and conversational English terms that MUST stay in Latin script.
3. Morphological heuristics: English words with suffixes (-ing, -tion, -sion, -ment,
   -able, -ible, -ness, -ity, -ous, -ive, -ly, -ed) stay in Latin script.
4. Smart fallback transliteration for unmapped Hindi words: correctly handles
   trailing 'a' as 'ा' (karta -> करता, apna -> अपना, sabka -> सबका) and initial
   conjuncts (st, sp, sk -> स्...).
"""

import re

# ── Exact word map: Roman Hinglish → Devanagari ──────────────────────────────
WORD_MAP = {
    # ── Greetings / Identity / Politeness ──
    "namaste": "नमस्ते", "namaskar": "नमस्कार", "pranam": "प्रणाम",
    "shweta": "श्वेता", "prathmesh": "प्रथमेश",
    "shukriya": "शुक्रिया", "dhanyawad": "धन्यवाद", "dhanyavad": "धन्यवाद",
    "swagat": "स्वागत", "alvida": "अलविदा",
    "dost": "दोस्त", "yaar": "यार", "bhai": "भाई", "bro": "भाई",
    "sahab": "साहब", "saheb": "साहब", "saab": "साब", "ji": "जी",

    # ── Pronouns (Full Conjugations) ──
    # First person (Main / Hum)
    "main": "मैं", "mai": "मैं",
    "mera": "मेरा", "meri": "मेरी", "mere": "मेरे",
    "mujhe": "मुझे", "mujhse": "मुझसे", "mujhko": "मुझको",
    "hum": "हम", "humara": "हमारा", "humari": "हमारी", "humare": "हमारे",
    "humein": "हमें", "humse": "हमसे", "humko": "हमको",

    # Second person informal (Tu)
    "tu": "तू", "tera": "तेरा", "teri": "तेरी", "tere": "तेरे",
    "tujhe": "तुझे", "tujhse": "तुझसे", "tujhko": "तुझको",

    # Second person familiar (Tum)
    "tum": "तुम", "tumhara": "तुम्हारा", "tumhari": "तुम्हारी", "tumhare": "तुम्हारे",
    "tumhe": "तुम्हें", "tumhein": "तुम्हें", "tumse": "तुमसे", "tumko": "तुमको",

    # Second person respectful (Aap)
    "aap": "आप", "aapka": "आपका", "aapki": "आपकी", "aapke": "आपके",
    "aapko": "आपको", "aapse": "आपसे", "aapne": "आपने",

    # Reflexive (Apna / Khud)
    "apna": "अपना", "apni": "अपनी", "apne": "अपने", "apno": "अपनों",
    "khud": "खुद", "khudka": "खुदका", "khudki": "खुदकी", "khudke": "खुदके", "khudko": "खुदको",

    # Demonstrative Proximal (Yeh / Is)
    "yeh": "यह", "ye": "ये", "yehi": "यही", "yahi": "यही",
    "isi": "इसी", "iska": "इसका", "iski": "इसकी", "iske": "इसके",
    "isse": "इससे", "isko": "इसको", "ismein": "इसमें", "isme": "इसमें",
    "inhone": "इन्होंने", "inhe": "इन्हें", "inka": "इनका", "inki": "इनकी", "inke": "इनके", "inme": "इनमें",

    # Demonstrative Distal (Woh / Us)
    "woh": "वह", "wo": "वो", "wahi": "वही",
    "usi": "उसी", "uska": "उसका", "uski": "उसकी", "uske": "उसके",
    "usse": "उससे", "usko": "उसको", "usmein": "उसमें", "usme": "उसमें",
    "unhone": "उन्होंने", "unhe": "उन्हें", "unhein": "उन्हें",
    "unka": "उनका", "unki": "उनकी", "unke": "उनके", "unse": "उनसे", "unme": "उनमें",

    # Relative & Interrogative
    "kaun": "कौन", "koi": "कोई", "kisi": "किसी", "kisko": "किसको", "kisse": "किससे",
    "kiska": "किसका", "kiski": "किसकी", "kiske": "किसके", "kismein": "किसमें", "kisme": "किसमें",
    "jo": "जो", "jiska": "जिसका", "jiski": "जिसकी", "jiske": "जिसके", "jisko": "जिसको", "jisse": "जिससे",
    "jinhone": "जिन्होंने", "jinhe": "जिन्हें",

    # Quantifiers
    "sab": "सब", "sabka": "सबका", "sabki": "सबकी", "sabke": "सबके", "sabko": "सबको", "sabse": "सबसे", "sabme": "सबमें",
    "kuch": "कुछ", "kuchh": "कुछ", "har": "हर", "koi2": "कोई",

    # ── Question Words ──
    "kya": "क्या", "kyun": "क्यों", "kyu": "क्यों", "kyoon": "क्यों",
    "kaise": "कैसे", "kaisa": "कैसा", "kaisi": "कैसी",
    "kab": "कब", "kahan": "कहाँ", "kaha": "कहा", "kidhar": "किधर",
    "kitna": "कितना", "kitni": "कितनी", "kitne": "कितने",
    "konsa": "कौनसा", "konsi": "कौनसी", "konse": "कौनसे",
    "kaunsa": "कौनसा", "kaunsi": "कौनसी", "kaunse": "कौनसे",

    # ── Demonstrative Adverbs / Direction / Placement ──
    "itna": "इतना", "itni": "इतनी", "itne": "इतने",
    "utna": "उतना", "utni": "उतनी", "utne": "उतने",
    "aisa": "ऐसा", "aisi": "ऐसी", "aise": "ऐसे",
    "waisa": "वैसा", "waisi": "वैसी", "waise": "वैसे",
    "yahan": "यहाँ", "wahan": "वहाँ", "idhar": "इधर", "udhar": "उधर",
    "upar": "ऊपर", "neeche": "नीचे", "aage": "आगे", "peeche": "पीछे",
    "andar": "अंदर", "bahar": "बाहर", "paas": "पास", "door": "दूर",
    "saath": "साथ", "bina": "बिना", "alawa": "अलावा", "jagah": "जगह",
    "side": "side", "corner": "corner",

    # ── Common Particles, Conjunctions & Adverbs ──
    "haan": "हाँ", "han": "हाँ", "ha": "हाँ",
    "nahi": "नहीं", "nahin": "नहीं", "na": "ना", "mat": "मत",
    "aur": "और", "ya": "या", "par": "पर", "pe": "पे", "mein": "में", "me": "में",
    "lekin": "लेकिन", "magar": "मगर",
    "toh": "तो", "to": "तो", "bhi": "भी", "sirf": "सिर्फ", "bas": "बस",
    "isliye": "इसलिए", "kyunki": "क्योंकि", "chunki": "चूंकि",
    "bahut": "बहुत", "bohot": "बहुत", "zyada": "ज़्यादा", "jyada": "ज़्यादा",
    "kam": "कम", "thoda": "थोड़ा", "thodi": "थोड़ी", "thode": "थोड़े",
    "theek": "ठीक", "thik": "ठीक", "achha": "अच्छा", "accha": "अच्छा", "acha": "अच्छा",
    "badhiya": "बढ़िया", "mast": "मस्त", "shandaar": "शानदार", "zabardast": "ज़बरदस्त",
    "sahi": "सही", "galat": "गलत", "sach": "सच", "jhooth": "झूठ",
    "jaldi": "जल्दी", "dheere": "धीरे", "dheerey": "धीरे", "aaram": "आराम",
    "arre": "अरे", "arey": "अरे", "oye": "ओये", "wah": "वाह", "uff": "उफ़",

    # ── Time & Temporal ──
    "aaj": "आज", "kal": "कल", "parso": "परसों", "tarso": "तरसों",
    "subah": "सुबह", "dopahar": "दोपहर", "shaam": "शाम", "raat": "रात",
    "waqt": "वक़्त", "samay": "समय", "din": "दिन", "hafte": "हफ़्ते", "mahina": "महीना", "mahine": "महीने", "saal": "साल",
    "abhi": "अभी", "kabhi": "कभी", "tabhi": "तभी", "jab": "जब", "tab": "तब",
    "hamesha": "हमेशा", "roz": "रोज़", "pehle": "पहले", "baad": "बाद", "wapas": "वापस", "dobara": "दोबारा",
    "baje": "बजे", "baj": "बज", "bajke": "बजके", "ghanta": "घंटा", "ghante": "घंटे",

    # ── Life, State & Environment ──
    "haal": "हाल", "khush": "खुश", "udaas": "उदास", "pareshan": "परेशान",
    "pareshani": "परेशानी", "chinta": "चिंता", "dhyan": "ध्यान", "khayal": "ख़्याल",
    "pani": "पानी", "paani": "पानी", "chai": "चाय", "khana": "खाना", "ghar": "घर", "kaam": "काम",
    "baat": "बात", "baatein": "बातें", "gaana": "गाना", "gana": "गाना", "gaane": "गाने", "gane": "गाने",
    "aankho": "आँखों", "aankhein": "आँखें", "chashma": "चश्मा", "saree": "साड़ी",
    "madad": "मदद", "zaroorat": "ज़रूरत", "zarurat": "ज़रूरत", "zaroor": "ज़रूर", "zarur": "ज़रूर", "zaroori": "ज़रूरी", "zaruri": "ज़रूरी",
    "chahiye": "चाहिए", "chaiye": "चाहिए", "chahie": "चाहिए",
    "pata": "पता", "maloom": "मालूम", "yaad": "याद",

    # ── Common Verbs (Roots & Conjugations) ──
    # Hona (To be)
    "hoon": "हूँ", "hu": "हूँ", "hun": "हूँ",
    "ho": "हो", "hai": "है", "hain": "हैं",
    "hoga": "होगा", "hogi": "होगी", "honge": "होंगे",
    "hona": "होना", "hota": "होता", "hoti": "होती", "hote": "होते",
    "hua": "हुआ", "hui": "हुई", "hue": "हुए", "huye": "हुए",
    "hoke": "होके",

    # Karna (To do)
    "kar": "कर", "karo": "करो", "karna": "करना",
    "karta": "करता", "karti": "करती", "karte": "करते",
    "karu": "करूँ", "karun": "करूँ", "karunga": "करूँगा", "karungi": "करूँगी", "karenge": "करेंगे",
    "karega": "करेगा", "karegi": "करेगी",
    "kiya": "किया", "kiye": "किए", "kijiye": "कीजिए", "kariye": "करिए",
    "karwa": "करवा", "karwao": "करवाओ", "kardo": "कर दो",

    # Jaana (To go)
    "ja": "जा", "jao": "जाओ", "jana": "जाना",
    "jaata": "जाता", "jaati": "जाती", "jaate": "जाते",
    "jaunga": "जाऊँगा", "jaungi": "जाऊँगी", "jayenge": "जाएँगे", "jayega": "जाएगा", "jayegi": "जाएगी",
    "gaya": "गया", "gayi": "गई", "gaye": "गए", "jaiye": "जाइए", "jado": "जा दो",

    # Aana (To come)
    "aa": "आ", "aao": "आओ", "aana": "आना",
    "aata": "आता", "aati": "आती", "aate": "आते",
    "aaunga": "आऊँगा", "aaungi": "आऊँगी", "aayenge": "आएँगे", "aayega": "आएगा", "aayegi": "आएगी",
    "aaya": "आया", "aayi": "आई", "aaye": "आए", "aaiye": "आइए",

    # Rehna (To stay/continue)
    "reh": "रह", "raho": "रहो", "rehna": "रहना",
    "rehta": "रहता", "rehti": "रहती", "rehte": "रहते",
    "raha": "रहा", "rahi": "रही", "rahe": "रहे",
    "rahunga": "रहूँगा", "rahungi": "रहूँगी", "rahenge": "रहेंगे",

    # Bolna / Kehna (To speak/say)
    "bol": "बोल", "bolo": "बोलो", "bolna": "बोलना",
    "bolta": "बोलता", "bolti": "बोलती", "bolte": "बोलते",
    "bolunga": "बोलूँगा", "bolungi": "बोलूँगी", "bolenge": "बोलेंगे",
    "bolega": "बोलेगा", "bolegi": "बोलेगी",
    "bola": "बोला", "boli": "बोली", "bole": "बोले", "boliye": "बोलिए",
    "keh": "कह", "kaho": "कहो", "kehna": "कहना",
    "kehta": "कहता", "kehti": "कहती", "kehte": "कहते",
    "kaha": "कहा", "kahi": "कही", "kahe": "कहे", "kahiye": "कहिए",

    # Batana (To tell)
    "bata": "बता", "batao": "बताओ", "batana": "बताना",
    "batata": "बताता", "batati": "बताती", "batate": "बताते",
    "bataunga": "बताऊँगा", "bataungi": "बताूँगी", "batayenge": "बताएँगे",
    "batayega": "बताएगा", "batayegi": "बताएगी",
    "bataya": "बताया", "batayi": "बताई", "bataye": "बताए", "bataiye": "बताइए",
    "batado": "बता दो",

    # Dekhna (To see)
    "dekh": "देख", "dekho": "देखो", "dekhna": "देखना",
    "dekhta": "देखता", "dekhti": "देखती", "dekhte": "देखते",
    "dekhunga": "देखूँगा", "dekhungi": "देखूँगी", "dekhenge": "देखेंगे",
    "dekhega": "देखेगा", "dekhegi": "देखेगी",
    "dekha": "देखा", "dekhi": "देखी", "dekhe": "देखे", "dekhiye": "देखिए",

    # Sunna (To listen/hear)
    "sun": "सुन", "suno": "सुनो", "sunna": "सुनना",
    "sunta": "सुनता", "sunti": "सुनती", "sunte": "सुनते",
    "sununga": "सुनूँगा", "sunungi": "सुनूँगी", "sunenge": "सुनेंगे",
    "sunega": "सुनेगा", "sunegi": "सुनेगी",
    "suna": "सुना", "suni": "सुनी", "sune": "सुने", "suniye": "सुनिए", "sunao": "सुनाओ",

    # Samajhna (To understand)
    "samajh": "समझ", "samjho": "समझो", "samajhna": "समझना",
    "samajhta": "समझता", "samajhti": "समझती", "samajhte": "समझते",
    "samjha": "समझा", "samjhi": "समझी", "samjhe": "समझे",
    "samjhiye": "समझिए", "samjhao": "समझाइए",

    # Kholna (To open) / Band (To close)
    "khol": "खोल", "kholo": "खोलो", "kholna": "खोलना",
    "kholta": "खोलता", "kholti": "खोलती", "kholte": "खोलते",
    "khola": "खोला", "kholi": "खोली", "khole": "खोले", "kholiye": "खोलिए", "kholdo": "खोल दो",
    "band": "बंद", "chalu": "चालू", "shuru": "शुरू", "khatam": "खत्म",

    # Dena (To give) / Lena (To take)
    "de": "दे", "do": "दो", "dena": "देना", "deta": "देता", "deti": "देती", "dete": "देते",
    "dega": "देगा", "degi": "देगी", "denge": "देंगे", "diya": "दिया", "diye": "दिए", "dijiye": "दीजिए",
    "le": "ले", "lo": "लो", "lena": "लेना", "leta": "लेता", "leti": "लेती", "lete": "लेते",
    "lega": "लेगा", "legi": "लेगी", "lenge": "लेंगे", "liya": "लिया", "liye": "लिए", "lijiye": "लीजिए",

    # Rakhna (To keep/put)
    "rakh": "रख", "rakho": "रखो", "rakhna": "रखना", "rakhta": "रखता", "rakhti": "रखती", "rakhte": "रखते",
    "rakha": "रखा", "rakhi": "रखी", "rakhe": "रखे", "rakhiye": "रखिए",

    # Rukna (To wait/stop)
    "ruk": "रुक", "ruko": "रुको", "rukna": "रुकना", "rukta": "रुकता", "rukti": "रुकती", "rukte": "रुकते",
    "ruka": "रुका", "ruki": "रुकी", "ruke": "रुके", "rukiye": "रुकिए",

    # Chalna (To walk/run/move)
    "chal": "चल", "chalo": "चलो", "chalna": "चलना", "chalta": "चलता", "chalti": "चलती", "chalte": "चलते",
    "chala": "चला", "chali": "चली", "chale": "चले", "chaliye": "चलिए",

    # Banna / Banana (To make)
    "ban": "बन", "bano": "बनो", "banna": "बनना", "banta": "बनता", "banti": "बनती", "bante": "बनते",
    "bana": "बना", "banao": "बनाओ", "banaya": "बनाया", "banayi": "बनाई", "banaye": "बनाए",

    # Milna (To meet/get)
    "mil": "मिल", "milo": "मिलो", "milna": "मिलना", "milta": "मिलता", "milti": "मिलती", "milte": "मिलते",
    "mila": "मिला", "mili": "मिली", "mile": "मिले", "milega": "मिलेगा", "milegi": "मिलेगी", "milenge": "मिलेंगे",

    # Lagna (To feel/apply)
    "lag": "लग", "lago": "लगाओ", "lagna": "लगना", "lagta": "लगता", "lagti": "लगती", "lagte": "लगते",
    "laga": "लगा", "lagi": "लगी", "lage": "लगे", "lagao": "लगाओ",

    # Sochna (To think)
    "soch": "सोच", "socho": "सोचो", "sochna": "सोचना", "sochta": "सोचता", "sochti": "सोचती", "sochte": "सोचते",
    "socha": "सोचा", "sochi": "सोची", "soche": "सोचे",

    # Likhna (To write) / Padhna (To read)
    "likh": "लिख", "likho": "लिखो", "likhna": "लिखना", "likhta": "लिखता", "likhti": "लिखती", "likha": "लिखा",
    "padh": "पढ़", "padho": "पढ़ो", "padhna": "पढ़ना", "padhta": "पढ़ता", "padhti": "पढ़ती", "padha": "पढ़ा",

    # Bhejna (To send)
    "bhej": "भेज", "bhejo": "भेजो", "bhejna": "भेjna", "bheja": "भेजा", "bheji": "भेजी", "bheje": "भेजे",

    # Sakna (Ability)
    "sakta": "सकता", "sakti": "सकती", "sakte": "सकते",
    "sakunga": "सकूँगा", "sakungi": "सकूँगी", "sakenge": "सकेंगे",

    # Badhana / Kam (Volume/Brightness)
    "badha": "बढ़ा", "badhao": "बढ़ाओ", "badhaya": "बढ़ाया", "badhana": "बढ़ाना",
    "ghata": "घटा", "ghatao": "घटाओ",

    # Miscellaneous
    "pehan": "पहन", "uth": "उठ", "utho": "उठो", "uthna": "उठना",
    "baith": "बैठ", "baitho": "बैठो", "baithna": "बैठना",
    "pakad": "पकड़", "pakdo": "पकड़ो",
    "ud": "उड़", "udna": "उड़ना",

    # Tech Terms, Acronyms & Apps (Explicit Devanagari phonetics so Murf hi-IN never says 'paa')
    "pc": "पीसी", "ai": "एआई", "ok": "ओके", "okay": "ओके", "tv": "टीवी",
    "wifi": "वाई-फ़ाई", "ui": "यूआई", "os": "ओएस", "cpu": "सीपीयू",
    "gpu": "जीपीयू", "ram": "रैम", "rom": "रोम", "usb": "यूएसबी",
    "pdf": "पीडीएफ", "url": "यूआरएल", "app": "ऐप", "apps": "ऐप्स",
    "gb": "जीबी", "mb": "एमबी", "kb": "केबी", "tb": "टीबी",
    "youtube": "यूट्यूब", "google": "गूगल", "chrome": "क्रोम",
    "spotify": "स्पॉटिफ़ाई", "whatsapp": "व्हाट्सएप", "notepad": "नोटपैड",
    "calculator": "कैलकुलेटर", "terminal": "टर्मिनल", "vscode": "वीएस कोड",
    "windows": "विंडोज़", "desktop": "डेस्कटॉप", "laptop": "लैपटॉप",
    "computer": "कंप्यूटर", "bluetooth": "ब्लूटूथ", "internet": "इंटरनेट",
    "online": "ऑनलाइन", "offline": "ऑफलाइन", "restart": "रीस्टार्ट",
    "reboot": "रीबूट", "shutdown": "शटडाउन", "lock": "लॉक", "screen": "स्क्रीन",
    "screenshot": "स्क्रीनशॉट", "volume": "वॉल्यूम", "brightness": "ब्राइटनेस",
    "battery": "बैटरी", "settings": "सेटिंग्स", "file": "फ़ाइल", "files": "फ़ाइलें",
    "folder": "फ़ोल्डर", "folders": "फ़ोल्डर्स", "song": "सॉन्ग", "songs": "सॉन्ग्स",
    "music": "म्यूज़िक", "playlist": "प्लेलिस्ट", "play": "प्ले", "pause": "पॉज़",
    "next": "नेक्स्ट", "previous": "प्रीवियस", "mute": "म्यूट", "unmute": "अनम्यूट",
    "done": "डन", "ready": "रेडी", "cancel": "कैंसिल", "clear": "क्लियर",
    "delete": "डिलीट", "open": "ओपन", "close": "क्लोज़", "search": "सर्च",
    "timer": "टाइमर", "alarm": "अलार्म", "reminder": "रिमाइंडर", "notes": "नोट्स",
    "note": "नोट", "project": "प्रोजेक्ट", "task": "टास्क", "assistant": "असिस्टेंट",
    "hello": "हेलो", "hi": "हाय", "hey": "हे", "bye": "बाय",

    # Conversational Polish & Common Expressions
    "sannata": "सन्नाटा", "sanata": "सन्नाटा", "shanti": "शांति", "khamoshi": "ख़ामोशी",
    "bore": "बोर", "boring": "बोरिंग", "time": "टाइम", "aise": "ऐसे",
    "baithi": "बैठी", "baitha": "बैठा", "baithe": "बैठे", "baitho": "बैठो",
    "rahungi": "रहूंगी", "rahunga": "रहूंगा", "rahenge": "रहेंगे", "rahegi": "रहेगी", "rahega": "रहेगा",
    "akeli": "अकेली", "akela": "अकेला", "akele": "अकेले",
    "jaun": "जाऊं", "jaunga": "जाऊंगा", "jaungi": "जाऊंगी", "jao": "जाओ",
    "yahin": "यहीं", "wahin": "वहीं", "kahin": "कहीं",
    "thodi": "थोड़ी", "thoda": "थोड़ा", "thode": "थोड़े",
    "khelte": "खेलते", "khelna": "खेलना", "khelo": "खेलो", "khel": "खेल",
}

# ── Comprehensive English Vocabulary (MUST STAY LATIN) ───────────────────────
# Murf hi-IN natively synthesizes English words with a natural Indian accent.
# Acronyms (like PC, AI, OK) are mapped above to prevent letter-by-letter phonetic misreading.
ENGLISH_WORDS = {
    # Desktop, Apps & Windows System Terms
    "calculator", "notepad", "terminal", "system", "settings", "volume",
    "brightness", "screen", "screenshot", "display", "desktop", "window",
    "windows", "browser", "chrome", "edge", "firefox", "brave", "spotify",
    "music", "song", "songs", "playlist", "player", "video", "audio",
    "sound", "microphone", "mic", "speaker", "speakers", "headphones",
    "camera", "webcam", "bluetooth", "internet", "network",
    "connection", "battery", "charging", "percent", "percentage",
    "memory", "disk", "drive", "storage",
    "file", "files", "folder", "folders", "document", "documents",
    "download", "downloads", "doc", "txt", "zip", "code",
    "vscode", "editor", "git", "github", "commit", "push", "pull",
    "powershell", "cmd", "bash", "command", "task", "tasks", "taskbar",
    "process", "manager", "monitor", "performance", "search", "google",
    "youtube", "web", "website", "link", "click", "double",
    "type", "press", "key", "keyboard", "shortcut", "hotkey", "mouse",
    "cursor", "drag", "drop", "copy", "paste", "cut", "select", "delete",
    "remove", "clear", "clean", "undo", "redo", "refresh", "reload",
    "restart", "reboot", "shutdown", "sleep", "lock", "hibernate",
    "power", "turn", "off", "on", "switch", "toggle", "update", "upgrade",
    "install", "setup", "open", "close", "save", "saved", "shift", "shifted",
    "show", "hide", "send", "sent", "find", "found", "set", "get", "put",
    "application", "software",
    "tool", "tools", "widget", "dock", "notch", "menu", "icon", "bar",
    "button", "dialog", "modal", "alert", "notification", "message",
    "chat", "email", "mail", "telegram", "whatsapp", "discord", "slack",
    "zoom", "meet", "call", "photo", "picture", "image", "wallpaper",
    "theme", "dark", "light", "mode", "status", "info", "details",
    "version", "error", "warning", "bug", "crash", "fix", "test",
    "run", "start", "stop", "pause", "resume", "play", "next", "prev",
    "previous", "back", "forward", "skip", "mute", "unmute", "level",
    "high", "medium", "low", "full", "empty", "min", "max", "fast",
    "slow", "smooth", "quick", "speed", "timer", "alarm", "clock",
    "stopwatch", "reminder", "reminders", "event", "calendar", "schedule",
    "note", "notes", "memo", "list", "todo", "item", "items",
    "yes", "no", "true", "false", "bot", "assistant", "voice", "speech",
    "tradingview", "nvda", "laptop", "computer", "spec", "specs",

    # Conversational Indian English Words & Colloquialisms
    "actually", "basically", "seriously", "literally", "normally",
    "properly", "completely", "quickly", "smoothly", "really", "finally",
    "mostly", "simply", "directly", "recently", "slowly", "safely",
    "easily", "strictly", "clearly", "perfectly", "exactly", "absolutely",
    "personally", "automatically", "definitely", "probably", "maybe",
    "sure", "certainly", "please", "sorry", "welcome", "thanks", "thank",
    "cool", "super", "awesome", "nice", "fine", "good", "great", "bad",
    "perfect", "fresh", "happy", "sad", "crazy", "smart", "cute",
    "sweet", "hot", "cold", "warm", "weather", "temperature", "rain",
    "sun", "cloud", "forecast", "relax", "chill", "enjoy", "party",
    "weekend", "office", "work", "job", "meeting", "project", "plan",
    "schedule", "moment", "second", "seconds", "minute", "minutes",
    "hour", "hours", "morning", "evening", "afternoon", "night",
    "hello", "hi", "hey", "bye", "goodbye", "later", "online",
    "offline", "connect", "connected", "disconnect", "available",
    "feeling", "mood", "vibe", "scene", "view", "side", "corner",
    "floor", "ground", "penthouse", "basement", "helicopter",
    "simulator", "earthquake", "dignity", "height", "fancy", "boring",
    "interesting", "problem", "issue", "simple", "easy", "difficult",
    "tension", "feel", "sir", "maam", "madam", "miss", "boss", "buddy",
    "dude", "guy", "guys", "check", "try", "wait", "free", "busy",
    "break", "rest", "hydrated", "stretch", "walk", "choice",
}

# ── Syllables for unknown casual Hindi transliteration ───────────────────────
_CONS = {
    # Double consonants (geminates) & special conjuncts
    "cch": "च्छ", "chh": "छ", "tth": "ट्ठ", "ddh": "ड्ढ",
    "kk": "क्क", "gg": "ग्ग", "ch": "च", "jj": "ज्ज", "tt": "त्त", "dd": "द्द",
    "nn": "न्न", "pp": "प्प", "bb": "ब्ब", "mm": "म्म", "ll": "ल्ल", "ss": "स्स",
    "kh": "ख", "gh": "घ", "jh": "झ", "th": "थ",
    "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श", "ng": "ंग",
    "k": "क", "g": "ग", "j": "ज", "t": "त", "d": "द", "n": "न",
    "p": "प", "b": "ब", "m": "म", "y": "य", "r": "र", "l": "ल",
    "v": "व", "w": "व", "s": "स", "h": "ह", "f": "फ", "z": "ज़", "c": "क",
}

_MATRA = {
    "aa": "ा", "a": "", "ee": "ी", "i": "ि", "ii": "ी",
    "oo": "ू", "u": "ु", "uu": "ू", "e": "े", "ai": "ै",
    "o": "ो", "au": "ौ",
}

_VOWEL_STANDALONE = {
    "aa": "आ", "a": "अ", "ee": "ई", "i": "इ", "ii": "ई",
    "oo": "ऊ", "u": "उ", "uu": "ऊ", "e": "ए", "ai": "ऐ",
    "o": "ओ", "au": "औ",
}


def _is_english_word(w: str) -> bool:
    """
    Determine if a word is English (keep Latin script for Murf hi-IN).
    Murf Ayushi handles Latin English naturally with native Indian accent.
    """
    low = w.lower()
    if low in ENGLISH_WORDS:
        return True

    # Common English morphological suffixes for words >= 5 characters
    if len(low) >= 5:
        english_suffixes = (
            "ing", "tion", "sion", "ment", "able", "ible", "ness",
            "ity", "ous", "ive", "ed", "est"
        )
        if any(low.endswith(sfx) for sfx in english_suffixes):
            return True

    return False


def _translit_word(w: str) -> str:
    """
    Robust rule-based syllable transliteration fallback for unknown Hindi words.
    Correctly recognizes trailing 'a' as 'ा' (karta -> करता, apna -> अपना).
    """
    s = w.lower()
    out = []
    i = 0
    first = True
    while i < len(s):
        # Initial s conjunct: st, sp, sk, sm, sn -> स्...
        if first and s[i] == "s" and i + 1 < len(s) and s[i+1] in "tkpmn":
            out.append("स्")
            i += 1
            first = False
            continue

        matched = False
        for clen in (3, 2, 1):
            chunk = s[i:i + clen]
            if chunk in _CONS:
                cons = _CONS[chunk]
                i += clen
                # look ahead for vowel
                vmatched = ""
                for vlen in (2, 1):
                    vchunk = s[i:i + vlen]
                    if vchunk in _MATRA:
                        vmatched = vchunk
                        i += vlen
                        break
                if vmatched:
                    # In casual Hinglish, a trailing 'a' at end of word is 'ा' (aa)
                    if vmatched == "a" and i >= len(s):
                        out.append(cons + "ा")
                    else:
                        out.append(cons + _MATRA[vmatched])
                else:
                    out.append(cons)
                matched = True
                first = False
                break
        if matched:
            continue

        # Standalone vowel
        vmatched = ""
        for vlen in (2, 1):
            vchunk = s[i:i + vlen]
            if vchunk in _VOWEL_STANDALONE:
                vmatched = vchunk
                i += vlen
                break
        if vmatched:
            out.append(_VOWEL_STANDALONE[vmatched] if first else _MATRA[vmatched])
            first = False
            continue

        # Unknown character — keep as-is
        out.append(s[i])
        i += 1

    return "".join(out)


def to_devanagari(text: str) -> str:
    """
    Convert Romanized Hinglish text for Murf hi-IN TTS.
    - Casual Hinglish words -> Accurate Devanagari via WORD_MAP or smart syllable transliteration.
    - English, system, and tech terms -> Preserved in Roman/Latin script for native Murf bilingual synthesis.
    - Numbers, punctuation, and emojis handled gracefully.
    """
    if not text:
        return text

    # Tokenize preserving whitespace, words, numbers, and punctuation
    tokens = re.findall(r"[A-Za-z]+|\d+|[^\sA-Za-z\d]+|\s+", text)
    out = []
    for tok in tokens:
        if tok.isspace() or tok.isdigit() or not tok.isalpha():
            out.append(tok)
            continue
        low = tok.lower()
        if low in WORD_MAP:
            out.append(WORD_MAP[low])
        elif _is_english_word(low):
            out.append(tok)  # keep brand/tech/English words in Roman
        else:
            out.append(_translit_word(tok))
    return "".join(out)
