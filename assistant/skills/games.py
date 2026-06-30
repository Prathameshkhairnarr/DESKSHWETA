"""
Interactive Mini-Games Skill — Play Rock-Paper-Scissors, Truth or Dare, or Bollywood Quiz with Shweta.
"""

import random
from typing import Dict

# Truth or Dare Catalog (teasing/casual best friend style)
TRUTHS = [
    "Tera abhi tak koi crush hai ya tu single hi marega?",
    "Apni search history bata, abhi isi waqt! Sacch bolna.",
    "Tune kabhi kisi ladki ke samne hero banne ke chakkar me beizzati karwayi hai?",
    "Mera avatar tere baaki dosto se zyada pyaara hai na? Sach bata!",
    "Tu din me kitne ghante bas reels dekhta hai bina kisi kaam ke?"
]

DARES = [
    "Notepad khol ke blindfolded (aankhein band karke) type kar: 'Shweta is my bestie forever'.",
    "Agle 1 minute tak bina ruke apni hi tareef kar!",
    "Apne kisi dost ko text kar ke bol: 'Mujhe ek alien ne kidnap kar liya hai' aur reactions bata.",
    "Ek glass paani 5 second me pee kar dikha (time shuru hota hai ab!).",
    "Apne room me jo bhi sabse ajeeb cheez hai uski screenshot leke mujhe dikha."
]

# Bollywood Quiz Catalog
BOLLYWOOD_QUIZ = [
    {
        "question": "Movie 'Sholay' mein Gabbar Singh ka iconic dialogue kya hai?",
        "options": ["Kitne aadmi the?", "Mogambo khush hua!", "Rishte mein toh hum tumhare baap lagte hain"],
        "answer": "kitne aadmi the"
    },
    {
        "question": "SRK ki kis movie mein dialogue hai: 'Rahul, naam toh suna hoga'?",
        "options": ["Dil To Pagal Hai", "Kuch Kuch Hota Hai", "Kabhi Khushi Kabhie Gham"],
        "answer": "dil to pagal hai"
    },
    {
        "question": "3 Idiots mein Aamir Khan ke character ka asli naam kya tha?",
        "options": ["Ranchoddas Chanchad", "Phunsukh Wangdu", "Raju Rastogi"],
        "answer": "phunsukh wangdu"
    },
    {
        "question": "Kaunsi movie mein Kareena Kapoor ka character bolta hai: 'Main apni favorite hoon'?",
        "options": ["Jab We Met", "Kabhi Khushi Kabhie Gham", "3 Idiots"],
        "answer": "jab we met"
    }
]

# Global game state helper
_current_game: Dict = {}


def start_game(game_name: str) -> Dict[str, str]:
    """Start a new mini game."""
    global _current_game
    game_name = game_name.lower().strip()

    if game_name in ["rps", "rock_paper_scissors", "stone_paper_scissor"]:
        _current_game = {"name": "rps"}
        return {
            "status": "success",
            "message": "Rock, Paper, or Scissors? Bol re! (Command format: play_turn with choice)"
        }

    elif game_name in ["truth_or_dare", "tod", "truth or dare"]:
        _current_game = {"name": "tod"}
        return {
            "status": "success",
            "message": "Truth ya Dare? Jaldi bol, darna mat!"
        }

    elif game_name in ["quiz", "bollywood_quiz", "trivia"]:
        q = random.choice(BOLLYWOOD_QUIZ)
        _current_game = {
            "name": "quiz",
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"]
        }
        opts = ", ".join(f"[{i+1}] {opt}" for i, opt in enumerate(q["options"]))
        return {
            "status": "success",
            "message": f"Sawaal ye hai: {q['question']} Options hain: {opts}"
        }

    return {
        "status": "error",
        "message": f"Mujhe '{game_name}' khelna nahi aata re. Hum Rock Paper Scissors, Truth or Dare, ya Bollywood Quiz khel sakte hain!"
    }


def play_turn(choice: str) -> Dict[str, str]:
    """Play a turn in the active game."""
    global _current_game
    if not _current_game:
        return {"status": "error", "message": "Pehle koi game toh start kar re! 'start_game' call karo."}

    game_name = _current_game["name"]
    choice_clean = choice.lower().strip()

    if game_name == "rps":
        ai_choice = random.choice(["rock", "paper", "scissors"])
        user_choice = choice_clean

        if user_choice not in ["rock", "paper", "scissors"]:
            # Quick mapper for common alternatives
            if "stone" in user_choice or "rock" in user_choice:
                user_choice = "rock"
            elif "scissor" in user_choice:
                user_choice = "scissors"
            else:
                return {"status": "error", "message": "Sirf 'rock', 'paper', ya 'scissors' bol."}

        # Clear state
        _current_game = {}

        if user_choice == ai_choice:
            return {
                "status": "success",
                "message": f"Draw ho gaya re! Dono ne {ai_choice.capitalize()} chunna. Chalo phir se khelo."
            }

        # Win conditions
        win = False
        if user_choice == "rock" and ai_choice == "scissors":
            win = True
        elif user_choice == "paper" and ai_choice == "rock":
            win = True
        elif user_choice == "scissors" and ai_choice == "paper":
            win = True

        if win:
            return {
                "status": "success",
                "message": f"Arre yaar! Tu jeet gaya. Maine {ai_choice.capitalize()} chunna tha aur tune {user_choice.capitalize()}. Bada aaya luck chal gaya tera!"
            }
        else:
            return {
                "status": "success",
                "message": f"Haha! Tu haar gaya! Maine {ai_choice.capitalize()} chunna tha aur tune {user_choice.capitalize()}. Nakhre kam kar aur mere aage sir jhuka!"
            }

    elif game_name == "tod":
        _current_game = {}  # Reset
        if "truth" in choice_clean or "sacch" in choice_clean:
            q = random.choice(TRUTHS)
            return {"status": "success", "message": f"Truth it is: {q}"}
        elif "dare" in choice_clean or "himmat" in choice_clean:
            d = random.choice(DARES)
            return {"status": "success", "message": f"Dare de rahi hoon chal: {d}"}
        else:
            return {"status": "error", "message": "Truth ya dare me se koi ek bol na re!"}

    elif game_name == "quiz":
        correct_ans = _current_game["answer"].lower()
        _current_game = {}  # Reset after answering

        # Check if user matches answer text or option text
        if correct_ans in choice_clean or any(opt.lower() in choice_clean for opt in _current_game.get("options", [])):
            return {
                "status": "success",
                "message": "Arre wah! Ekdum sahi jawab. Tu toh bada intelligent ban raha hai aaj."
            }

        # Check option indices (1, 2, 3)
        if choice_clean in ["1", "2", "3"]:
            opts = _current_game.get("options", [])
            idx = int(choice_clean) - 1
            if idx < len(opts) and opts[idx].lower() == correct_ans:
                return {
                    "status": "success",
                    "message": "Sahi jawab re! Maan gaye tujhe."
                }

        return {
            "status": "success",
            "message": f"Haha galat jawab! Asli jawab tha: '{correct_ans}'. Chalo agli baar try karna re."
        }

    return {"status": "error", "message": "Unknown game state."}
