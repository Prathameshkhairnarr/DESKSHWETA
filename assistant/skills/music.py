"""
Smart Music Recommendation and Playback Engine for Shweta AI Assistant.
Manages curated databases for Phonk, Hindi, English, Punjabi, Haryanvi, South Indian,
and mood-based music, ensuring no repeating tracks by tracking play history.
Dynamically learns and classifies songs requested by the user in the background.
"""

import os
import json
import random
import logging
import threading
from typing import Dict, List, Optional
from assistant.skills.browser import play_youtube

logger = logging.getLogger(__name__)

# Paths for saving history and learned songs
HISTORY_FILE = os.path.join("cache", "played_songs.json")
LEARNED_FILE = os.path.join("cache", "learned_songs.json")

# Core Music Database categorized by Genre/Region/Mood
MUSIC_DATABASE: Dict[str, List[Dict[str, str]]] = {
    "phonk": [
        {"title": "Kordhell - Murder In My Mind", "desc": "Drift Phonk vibes!"},
        {"title": "Interworld - Metamorphosis", "desc": "Ultimate Phonk energy."},
        {"title": "Dxrk - RAVE", "desc": "Drift Phonk classic."},
        {"title": "Hensonn - Sahara", "desc": "Sahara Phonk."},
        {"title": "g3ox_em - GigaChad Theme Phonk", "desc": "Sigma Phonk!"},
        {"title": "MoonDeity - Wake Up", "desc": "High speed Phonk."},
        {"title": "DVRST - Close Eyes", "desc": "Memphis/Drift Phonk hybrid."},
        {"title": "PlayaPhonk - Phonky Town", "desc": "Retro phonk feel."},
        {"title": "KSLV Noh - Disaster", "desc": "Heavy drift phonk."},
        {"title": "SHADOWX - Brazilian Phonk Montagem", "desc": "Brazilian Phonk beats."}
    ],
    "hindi": [
        {"title": "Arijit Singh - Apna Bana Le", "desc": "Dil ko chune wala romantic song."},
        {"title": "Arijit Singh - Kesariya", "desc": "Superhit love song."},
        {"title": "Anirudh Ravichander - Chaleya", "desc": "Groovy romantic track."},
        {"title": "Mithoon - Tum Hi Ho", "desc": "All-time favorite Bollywood romance."},
        {"title": "Amit Trivedi - Iktara", "desc": "Beautiful soulful melody."},
        {"title": "Tochi Raina - Kabira", "desc": "Emotional/Sufi vibe."},
        {"title": "Karan Aujla - Tauba Tauba", "desc": "Vibe check superhit dance song!"},
        {"title": "Vishal-Shekhar - Ghungroo", "desc": "Sleek club dance song."},
        {"title": "Badshah - Soulmate", "desc": "Pop-rap romantic song."},
        {"title": "Jubin Nautiyal - Raataan Lambiyan", "desc": "Heartwarming love ballad."}
    ],
    "english": [
        {"title": "The Weeknd - Blinding Lights", "desc": "80s synth-pop banger."},
        {"title": "The Weeknd - Starboy ft. Daft Punk", "desc": "Classic Weeknd vibe."},
        {"title": "Ed Sheeran - Shape of You", "desc": "Super catchy pop tune."},
        {"title": "One Direction - Night Changes", "desc": "Nostalgic sweet song."},
        {"title": "Post Malone - Sunflower", "desc": "Chilled out pop-rap."},
        {"title": "Imagine Dragons - Believer", "desc": "High energy rock/pop."},
        {"title": "Billie Eilish - Bad Guy", "desc": "Quirky pop beats."},
        {"title": "Coldplay - Hymn For The Weekend", "desc": "Symphonic indie rock."},
        {"title": "Harry Styles - As It Was", "desc": "Upbeat synth-pop."},
        {"title": "Dua Lipa - Levitating", "desc": "Modern disco dance pop."}
    ],
    "punjabi": [
        {"title": "AP Dhillon - Excuses", "desc": "Kehndi hundi si... dil todne wala track."},
        {"title": "AP Dhillon - Brown Munde", "desc": "Desi boys anthem!"},
        {"title": "Karan Aujla - 52 Bars", "desc": "Heavy Punjabi hip hop."},
        {"title": "Diljit Dosanjh - G.O.A.T.", "desc": "Swag level max!"},
        {"title": "Diljit Dosanjh & Ikky - Softly", "desc": "Cute romantic Punjabi pop."},
        {"title": "Shubh - Cheques", "desc": "Smooth flows and bass."},
        {"title": "Sidhu Moose Wala - 295", "desc": "Legendary Moosewala track."},
        {"title": "Sidhu Moose Wala - The Last Ride", "desc": "Epic Punjabi rap tribute."},
        {"title": "Karan Aujla - Softly", "desc": "Smooth Punjabi vibe."},
        {"title": "Guru Randhawa - High Rated Gabru", "desc": "Catchy Punjabi dance pop."}
    ],
    "marathi": [
        {"title": "Ajay-Atul - Zingaat", "desc": "Full energetic dance beat!"},
        {"title": "Ajay-Atul - Yad lagla", "desc": "Beautiful romantic melody."},
        {"title": "Sairat - Aatach Baya Ka Baavla", "desc": "Sweet Marathi love track."},
        {"title": "Adarsh Shinde - Devaak Kalji Re", "desc": "Deeply emotional Marathi track."},
        {"title": "Ajay Gogavale - Mauli Mauli", "desc": "Powerful cultural fusion."},
        {"title": "Kombdi Palali", "desc": "Old-school high-energy Marathi dance beat."}
    ],
    "haryanvi": [
        {"title": "Manisha Sharma - Gypsy", "desc": "Balam Thanedar Chalawe Gypsy!"},
        {"title": "Amit Saini Rohtakiya - System", "desc": "Desi Haryanvi swag."},
        {"title": "Sapna Choudhary - Chatak Matak", "desc": "Traditional Haryanvi dance pop."},
        {"title": "Diler Kharkiya - Moto", "desc": "Sweet Haryanvi romance."},
        {"title": "MD Desi Rockstar - Badmash", "desc": "Haryanvi gangsta beats."}
    ],
    "south_indian": [
        {"title": "M. M. Keeravani - Naatu Naatu", "desc": "Oscar-winning high energy dance track!"},
        {"title": "Anirudh Ravichander - Hukum Jailer", "desc": "Mass BGM theme track!"},
        {"title": "Anirudh Ravichander - Arabic Kuthu", "desc": "Fun fusion dance track."},
        {"title": "Devi Sri Prasad - Oo Antava Mawa", "desc": "Sizzling mass item number."},
        {"title": "Santhosh Narayanan - Rakita Rakita", "desc": "Cool local beats."},
        {"title": "Harris Jayaraj - Halena", "desc": "Stylish romantic track."}
    ],
    "chill": [
        {"title": "Lofi Hip Hop Radio - beats to relax/study to", "desc": "Study or relax with standard chill lofi beats."},
        {"title": "Anuv Jain - Baarishein", "desc": "Soft acoustic indie vibe."},
        {"title": "Zaeden - tere bina", "desc": "Chill Hindi pop."},
        {"title": "Taba Chake - Shaayad", "desc": "Beautiful acoustic indie track."},
        {"title": "Prateek Kuhad - Cold/Mess", "desc": "Deep indie romance feel."}
    ],
    "workout": [
        {"title": "NEFFEX - Fight Back", "desc": "Gym motivation power rap."},
        {"title": "Imagine Dragons - Radioactive", "desc": "Epic energy workout track."},
        {"title": "Roy Jones Jr. - Can't Be Touched", "desc": "Aggressive workout rap."},
        {"title": "Skillet - Monster", "desc": "Heavy rock gym energy."}
    ]
}


def _load_history() -> List[str]:
    """Load previously played songs to prevent repetitions."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading play history: {e}")
        return []


def _save_history(history: List[str]) -> None:
    """Save play history, keeping only the last 30 songs."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        if len(history) > 30:
            history = history[-30:]
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        logger.warning(f"Error saving play history: {e}")


def _load_learned_songs() -> Dict[str, List[Dict[str, str]]]:
    """Load user-learned songs from file."""
    if not os.path.exists(LEARNED_FILE):
        return {}
    try:
        with open(LEARNED_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading learned songs: {e}")
        return {}


def _save_learned_songs(songs: Dict[str, List[Dict[str, str]]]) -> None:
    """Save user-learned songs to file."""
    os.makedirs(os.path.dirname(LEARNED_FILE), exist_ok=True)
    try:
        with open(LEARNED_FILE, "w") as f:
            json.dump(songs, f, indent=4)
    except Exception as e:
        logger.warning(f"Error saving learned songs: {e}")


def get_music_recommendation(category: str) -> Dict[str, str]:
    """
    Get a unique music recommendation for a category and play it on YouTube.
    Maintains history to prevent repeating songs and integrates learned songs.
    """
    cat = category.lower().strip()
    
    # Normalize category names
    if cat in ["phonk", "drift_phonk", "sigma", "gym_phonk", "brazilian_phonk"]:
        genre_key = "phonk"
    elif cat in ["hindi", "bollywood", "desi", "indian"]:
        genre_key = "hindi"
    elif cat in ["english", "pop", "hollywood", "western"]:
        genre_key = "english"
    elif cat in ["punjabi", "bhangra"]:
        genre_key = "punjabi"
    elif cat in ["marathi"]:
        genre_key = "marathi"
    elif cat in ["haryanvi"]:
        genre_key = "haryanvi"
    elif cat in ["south", "telugu", "tamil", "south_indian"]:
        genre_key = "south_indian"
    elif cat in ["chill", "lofi", "relax", "study", "coding", "focus", "sleep"]:
        genre_key = "chill"
    elif cat in ["workout", "gym", "heavy", "motivation"]:
        genre_key = "workout"
    else:
        genre_key = random.choice(list(MUSIC_DATABASE.keys()))

    # Merge static database and learned songs
    songs = list(MUSIC_DATABASE.get(genre_key, []))
    learned = _load_learned_songs()
    if genre_key in learned:
        songs.extend(learned[genre_key])

    history = _load_history()

    # Filter out songs played recently
    available_songs = [s for s in songs if s["title"].lower().strip() not in [h.lower().strip() for h in history]]

    if not available_songs:
        available_songs = songs
        titles_to_remove = [s["title"].lower().strip() for s in songs]
        history = [h for h in history if h.lower().strip() not in titles_to_remove]

    selected_song = random.choice(available_songs)

    # Add to history
    history.append(selected_song["title"])
    _save_history(history)

    query = selected_song["title"]
    logger.info(f"[MusicEngine] Selected '{query}' from category '{genre_key}'")
    play_result = play_youtube(query)

    if play_result["status"] == "success":
        desc = selected_song.get("desc", "A song you loved and played before!")
        return {
            "status": "success",
            "message": f"Sure bestie! Playing {selected_song['title']} ({desc}). Mazze kar!",
            "track": selected_song["title"]
        }
    else:
        return play_result


def learn_song_in_background(query: str) -> None:
    """Start a background thread to classify and learn a song query."""
    thread = threading.Thread(target=_learn_song, args=(query,), daemon=True)
    thread.start()


def _learn_song(query: str) -> None:
    """Classify the song query via active AI model and add to learned database."""
    query = query.strip()
    if not query or len(query) < 3:
        return

    # Check if song is already in base database to avoid duplicates
    query_lower = query.lower()
    for cat, list_songs in MUSIC_DATABASE.items():
        for s in list_songs:
            if s["title"].lower() == query_lower:
                return

    # Check if song is already in learned database
    learned = _load_learned_songs()
    for cat, list_songs in learned.items():
        for s in list_songs:
            if s["title"].lower() == query_lower:
                return

    # Call AI API key to classify song
    category = _classify_song_via_api(query)
    if not category or category not in MUSIC_DATABASE:
        category = "hindi"  # Default fallback

    # Add to learned dictionary
    if category not in learned:
        learned[category] = []
    
    learned[category].append({
        "title": query,
        "desc": "A song you played earlier."
    })
    _save_learned_songs(learned)
    logger.info(f"[MusicEngine] Successfully learned song: '{query}' -> Category: '{category}'")


def _classify_song_via_api(query: str) -> Optional[str]:
    """Helper to classify a song category using Gemini or Groq key."""
    # List of categories Shweta supports
    categories_str = ", ".join(MUSIC_DATABASE.keys())

    # Try Groq first
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            prompt = (
                f"Classify this song query into exactly one of these categories: {categories_str}. "
                f"Return ONLY the category name in lowercase with no punctuation or extra text. "
                f"Song query: \"{query}\""
            )
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0,
                max_tokens=10
            )
            res = chat_completion.choices[0].message.content.strip().lower()
            if res in MUSIC_DATABASE:
                return res
        except Exception as e:
            logger.warning(f"Groq classification failed: {e}")

    # Try Gemini next
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = (
                f"Classify this song query into exactly one of these categories: {categories_str}. "
                f"Return ONLY the category name in lowercase with no punctuation or extra text. "
                f"Song query: \"{query}\""
            )
            response = model.generate_content(prompt)
            res = response.text.strip().lower()
            if res in MUSIC_DATABASE:
                return res
        except Exception as e:
            logger.warning(f"Gemini classification failed: {e}")

    # Heuristic fallback if offline or no keys
    q_lower = query.lower()
    if "phonk" in q_lower:
        return "phonk"
    if any(w in q_lower for w in ["punjabi", "ap dhillon", "shubh", "sidhu", "diljit"]):
        return "punjabi"
    if any(w in q_lower for w in ["marathi", "zingaat", "sairat", "ajay atul"]):
        return "marathi"
    if any(w in q_lower for w in ["haryanvi", "gypsy", "sapna"]):
        return "haryanvi"
    if any(w in q_lower for w in ["naatu", "telugu", "tamil", "jailer", "anirudh"]):
        return "south_indian"
    if any(c in q_lower for c in "abcdefghijklmnopqrstuvwxyz"):
        # Check if it has mostly Hindi/Romanized words
        hindi_indicators = ["dil", "tum", "ho", "meri", "hai", "yeh", "kya", "na", "yaar", "apna", "pe", "se", "ko"]
        if any(w in q_lower.split() for w in hindi_indicators):
            return "hindi"
        return "english"

    return "hindi"
