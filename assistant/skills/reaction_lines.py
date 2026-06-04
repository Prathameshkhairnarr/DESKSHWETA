"""
Dramatic Reaction Voice Lines for Shweta.
Natural, dramatic Indian girl reactions — not robotic.
Uses ReactionPool to never repeat same line twice in a row.
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


# === SLOW DRAG REACTIONS (playful, curious) ===

SLOW_LEFT = ReactionPool([
    "oye... kahan ja rahi hoon main?",
    "arre yaar left kyun",
    "hmm naya ghar?",
    "theek hai chalo... dekhte hain",
    "ooh interesting side hai ye",
    "left mein kya hai bhai?",
    "achha toh idhar shift ho rahe hain",
    "oye sun... mujhe batake toh le ja",
])

SLOW_RIGHT = ReactionPool([
    "oh right side? okay okay",
    "haan haan chalo idhar bhi",
    "ye corner bhi achha lagta hai",
    "arre wah naya view!",
    "hmm... yahan theek lagega",
    "right mein kya scene hai",
    "achha chalo idhar bhi dekh lete hain",
    "ooh ye side pasand hai mujhe",
])

SLOW_UP = ReactionPool([
    "ooh upar? fancy hai",
    "arre itni upar mat le jao",
    "main ud rahi hoon literally",
    "sky view! nice nice",
    "helicopter mode on",
    "penthouse mein shift ho rahi hoon",
    "upar se sab chhota dikhta hai",
    "arre bhai itni height",
])

SLOW_DOWN = ReactionPool([
    "neeche kyun yaar",
    "floor pe rakhoge kya",
    "arre upar zyada achha tha",
    "basement? really?",
    "thoda dignity do mujhe please",
    "neeche andhera hai bhai",
    "ground floor? boring",
    "arre upar wapas le jao na",
])


# === MEDIUM SHAKE (startled, managing) ===

MEDIUM_SHAKE = ReactionPool([
    "arre arre ARRE—",
    "bhai dheerey! dheerey bhai!",
    "oye oye oye kya ho raha hai",
    "haan haan samajh gaya move karna hai",
    "arre yaar seriously abhi??",
    "okay okay OKAY bas bas",
    "bhai main hun yahan pakad ke rakh",
    "uff yaar itni jaldi kyun",
    "arre sun toh— dheerey le ja",
    "bhai earthquake simulator mat bana",
])

# === FAST SHAKE (panic — burst + followup) ===

FAST_SHAKE_BURST = ReactionPool([
    "AAAAAA—",
    "ARRE ARRE—",
    "OYE OYE OYE—",
    "BHAI BHAI—",
    "AAAA RUKO—",
    "AREY AREY—",
    "OYYY—",
    "BHAI RUKO—",
])

FAST_SHAKE_FOLLOWUP = ReactionPool([
    "kya kar raha hai SERIOUSLY",
    "main gir jaaungi bhai pls",
    "chakkar aa gaya mujhe",
    "yeh kya tha abhi",
    "haath kaanp rahe hain mere",
    "bhai seriously yaar",
    "dimag ghum gaya mera",
    "ek second... breathe... okay",
])

# === VERY FAST SHAKE (maximum drama) ===

VERY_FAST_BURST = ReactionPool([
    "AAAAAAAA—",
    "NAHI NAHI NAHI—",
    "BACHO BACHO—",
    "MAAAA—",
    "HELP HELP—",
    "ROKO ROKO ROKO—",
    "BHAI BHAI BHAI—",
    "AAAAAAA RUKO—",
])

VERY_FAST_FOLLOWUP = ReactionPool([
    "bhai tu pagal hai seriously",
    "meri jaan le lega kya",
    "yeh toh heart attack tha",
    "main mar gayi almost",
    "KABHI MAT KARNA YEH DOBARA",
    "bhai sach mein... kya tha ye",
    "mera dil abhi bhi dhadak raha hai",
    "tu... tu pagal hai. confirmed.",
])

# === SETTLE (relief after movement) ===

SETTLE_AFTER_SLOW = ReactionPool([
    "achha theek hai yahan bhi",
    "hmm okay naya ghar",
    "yeh side bhi chalega",
    "theek hai... adjust ho jaaungi",
    "okay done? yahan rakhna hai?",
])

SETTLE_AFTER_FAST = ReactionPool([
    "...bas? ho gaya?",
    "phew... shukar hai",
    "okay okay main theek hoon",
    "uff yaar... dil ki dhadkan...",
    "yeh dobara mat karna please",
    "saans toh lene do yaar",
    "main... main theek hoon. haan.",
    "never again. NEVER.",
])

# === BONUS REACTIONS ===

DOUBLE_CLICK = ReactionPool([
    "kya hai bhai?",
    "haan bol?",
    "kuch kaam hai?",
    "bolo bolo sun rahi hoon",
    "hmm? kya hua?",
    "arre tap tap kyun kar raha hai",
])

RESTORE_FROM_MINIMIZE = ReactionPool([
    "WAPAS AA GAYI! miss kiya?",
    "haan haan aa gayi main",
    "kya hua? yaad aa gayi meri?",
    "main hoon yahan! chhoda nahi maine",
    "phir se hello!",
    "miss me? obviously kiya hoga",
])

IDLE_BORED = ReactionPool([
    "bhai kuch kaam nahi hai kya?",
    "hello? koi hai?",
    "bore ho rahi hoon yaar",
    "kuch toh bolo... silence awkward hai",
    "main yahan hoon... agar kisi ko farak padta ho toh",
    "arre yaar kuch karo na",
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
    return ("oye!", None)
