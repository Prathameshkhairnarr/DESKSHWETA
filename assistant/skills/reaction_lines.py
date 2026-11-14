"""
Window-move reaction voice lines for Shweta.
Natural, warm, human Hinglish — like a real person reacting, not dramatic or
robotic. No ALL-CAPS screaming and no "arre"/dash bursts (TTS mangled those into
"aaar"). Short, genuine, and friendly. ReactionPool avoids repeating a line.
"""

import random
from collections import deque
from typing import List, Optional, Tuple


class ReactionPool:
    """Pool of voice lines that avoids repetition."""

    def __init__(self, lines: List[str]) -> None:
        self.lines = lines
        self.last_3: deque = deque(maxlen=3)

    def get(self) -> str:
        available = [l for l in self.lines if l not in self.last_3]
        if not available:
            available = self.lines
        choice = random.choice(available)
        self.last_3.append(choice)
        return choice


# === SLOW DRAG REACTIONS (light, natural) ===

SLOW_LEFT = ReactionPool([
    "achha, idhar shift ho rahe hain",
    "theek hai, left side chalo",
    "hmm, ye jagah bhi sahi lagti hai",
    "chalo, idhar aa gaye",
    "ye corner bhi theek hai",
    "haan, yahan set ho jaati hoon",
])

SLOW_RIGHT = ReactionPool([
    "haan, right side bhi badhiya hai",
    "achha, idhar le aaye",
    "ye view mujhe achha laga",
    "theek hai, yahan set ho jaati hoon",
    "ye side bhi mast hai",
    "chalo, yahan bhi theek hai",
])

SLOW_UP = ReactionPool([
    "ooh, upar? mast hai",
    "yahan se sab saaf dikhta hai",
    "achha, thodi height mil gayi",
    "ye upar wali jagah achhi hai",
    "haan, yahan theek lagega",
    "upar se accha feel aata hai",
])

SLOW_DOWN = ReactionPool([
    "neeche le aaye, theek hai",
    "hmm, upar thoda behtar tha",
    "chalo, yahan bhi chalega",
    "achha, thoda neeche",
    "theek hai, yahin sahi",
    "thoda upar rakhte toh achha tha",
])


# === MEDIUM SHAKE (startled but light) ===

MEDIUM_SHAKE = ReactionPool([
    "oye, thoda aaram se",
    "haan haan, samajh gayi, move karna hai",
    "dheere yaar, dheere",
    "achha okay, bas bas",
    "itni jaldi kya hai",
    "pakad ke rakho theek se",
    "haan, main yahin hoon, aaram se",
])

# === FAST SHAKE (energetic but natural — burst + followup) ===

FAST_SHAKE_BURST = ReactionPool([
    "oye oye, ruko",
    "haan haan, sun rahi hoon",
    "achha okay, bas",
    "oye, dheere zara",
    "ruko ruko",
    "haan, samajh gayi",
])

FAST_SHAKE_FOLLOWUP = ReactionPool([
    "itna hilao mat yaar",
    "chakkar aa jayega",
    "thoda aaram se karo na",
    "ye kya tha abhi",
    "bas bas, samajh gayi",
    "dheere bhi kar sakte ho",
])

# === VERY FAST SHAKE (strong but not screaming) ===

VERY_FAST_BURST = ReactionPool([
    "oye ruko ruko",
    "bas bas bas",
    "achha ruko zara",
    "oye itna nahi",
    "ruko yaar, ruko",
    "haan haan, bas",
])

VERY_FAST_FOLLOWUP = ReactionPool([
    "itna tez mat hilao yaar",
    "sach mein chakkar aa gaya",
    "thoda sambhaal ke",
    "ab bas karo na",
    "ye thoda zyada ho gaya",
    "aaram se bhi ho sakta hai ye",
])

# === SETTLE (relief after movement) ===

SETTLE_AFTER_SLOW = ReactionPool([
    "haan, yahan theek hai",
    "chalo, set ho gaye",
    "ye jagah sahi hai",
    "okay, ab yahin rehte hain",
    "theek hai, adjust ho gayi",
])

SETTLE_AFTER_FAST = ReactionPool([
    "chalo, ab theek hai",
    "haan, ab settle ho gayi",
    "ab aaram hai",
    "theek hai, saans aa gayi",
    "ab yahin rehne do",
    "haan, ab sahi lag raha hai",
])

# === BONUS REACTIONS ===

DOUBLE_CLICK = ReactionPool([
    "haan, bolo",
    "kya kaam hai?",
    "sun rahi hoon, bolo",
    "haan, kaho",
    "kya hua?",
])

RESTORE_FROM_MINIMIZE = ReactionPool([
    "haan, aa gayi main",
    "wapas aa gayi, bolo",
    "main yahin hoon",
    "haan ji, kaho",
    "aa gayi, kya chahiye?",
])

IDLE_BORED = ReactionPool([
    "main yahin hoon, jab kaam ho batao",
    "ready hoon, bolo kya karna hai",
    "kuch chahiye ho toh kaho",
    "main available hoon, bolo",
])


def get_reaction_lines(reaction_type: str, intensity: str = "slow") -> Tuple[str, Optional[str]]:
    """
    Get reaction lines based on type.
    Returns (burst_line, followup_line_or_None).
    """
    if reaction_type == "left":
        return (SLOW_LEFT.get(), None)
    elif reaction_type == "right":
        return (SLOW_RIGHT.get(), None)
    elif reaction_type == "up":
        return (SLOW_UP.get(), None)
    elif reaction_type == "down":
        return (SLOW_DOWN.get(), None)
    elif reaction_type == "medium_shake":
        return (MEDIUM_SHAKE.get(), None)
    elif reaction_type == "fast_shake":
        return (FAST_SHAKE_BURST.get(), FAST_SHAKE_FOLLOWUP.get())
    elif reaction_type == "very_fast_shake":
        return (VERY_FAST_BURST.get(), VERY_FAST_FOLLOWUP.get())
    elif reaction_type == "settle_slow":
        return (SETTLE_AFTER_SLOW.get(), None)
    elif reaction_type == "settle_fast":
        return (SETTLE_AFTER_FAST.get(), None)
    elif reaction_type == "double_click":
        return (DOUBLE_CLICK.get(), None)
    elif reaction_type == "restore":
        return (RESTORE_FROM_MINIMIZE.get(), None)
    elif reaction_type == "idle_bored":
        return (IDLE_BORED.get(), None)
    return ("haan, bolo", None)
