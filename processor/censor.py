"""
StreamClipper — Profanity & Demonetization Censor Engine
Sanitizes profanity, slurs, and high-risk terms from subtitles, hooks, and metadata
to protect short-form videos against automated demonetization and platform shadowbans.
"""

import re
from typing import List, Tuple, Dict, Set, Optional

# Verified list of high-risk terms for TikTok, YouTube Shorts, and Instagram Reels
PROFANITY_MASKS: Dict[str, str] = {
    # F-words
    "fuck": "f**k",
    "fucking": "f***ing",
    "fucked": "f***ed",
    "fucker": "f***er",
    "fuckers": "f***ers",
    "motherfucker": "m***erf***er",
    "motherfucking": "m***erf***ing",
    "stfu": "st*u",
    
    # S-words
    "shit": "sh*t",
    "shits": "sh*ts",
    "shitty": "sh*tty",
    "bullshit": "bullsh*t",
    "horseshit": "horsesh*t",
    "dipshit": "dipsh*t",
    "shitting": "sh*tting",
    
    # B-words
    "bitch": "b***h",
    "bitches": "b****es",
    "bitching": "b***hing",
    "bastard": "b***ard",
    
    # A-words
    "ass": "a**",
    "asshole": "a**hole",
    "assholes": "a**holes",
    "badass": "bada**",
    "jackass": "jacka**",
    "dumbass": "dumba**",
    
    # D & P words (Sexual / Genitalia)
    "dick": "d**k",
    "dicks": "d**ks",
    "dickhead": "d**khead",
    "pussy": "p***y",
    "pussies": "p***ies",
    "cock": "c**k",
    "cocks": "c**ks",
    "tits": "t*ts",
    "boobs": "b**bs",
    
    # C-word
    "cunt": "c**t",
    "cunts": "c**ts",
    
    # Slurs and hate speech (completely masked or sanitized)
    "nigger": "[censored]",
    "niggers": "[censored]",
    "nigga": "n***a",
    "niggas": "n***as",
    "faggot": "[censored]",
    "faggots": "[censored]",
    "retard": "r***rd",
    "retarded": "r***rded",
    
    # Self-harm / Violence flags that trigger immediate strikes
    "kys": "k*s",
    "suicide": "s***ide",
    "kill yourself": "k*ll y***self",
}

# Pre-compile regex for word replacement preserving capitalization
_WORD_PATTERNS: List[Tuple[re.Pattern, str]] = []

def _init_patterns():
    global _WORD_PATTERNS
    if _WORD_PATTERNS:
        return
    for raw_word, masked in sorted(PROFANITY_MASKS.items(), key=lambda x: -len(x[0])):
        # Match standalone words, handling punctuation around them
        pattern = re.compile(rf"\b{re.escape(raw_word)}\b", flags=re.IGNORECASE)
        _WORD_PATTERNS.append((pattern, masked))

_init_patterns()


def _match_case(original: str, replacement: str) -> str:
    """Preserve case style of the original token (UPPERCASE, Titlecase, or lowercase)."""
    if original.isupper():
        return replacement.upper()
    if original.istitle():
        return replacement.capitalize()
    return replacement.lower()


def censor_word(word: str) -> str:
    """
    Censor a single word token, preserving punctuation and case.
    Example: 'Fucking!' -> 'F***ing!'
    """
    if not word:
        return ""
    
    # Strip leading/trailing punctuation for lookup
    match = re.match(r"^([^\w]*)([\w\'-]+)([^\w]*)$", word)
    if not match:
        # Fallback to direct replacement
        return censor_text(word)
    
    prefix, core, suffix = match.groups()
    lower_core = core.lower()
    
    if lower_core in PROFANITY_MASKS:
        masked = PROFANITY_MASKS[lower_core]
        return f"{prefix}{_match_case(core, masked)}{suffix}"
    
    return word


def censor_text(text: str) -> str:
    """
    Censor all profanity and high-risk terms in a sentence or hook headline.
    Preserves casing and surrounding punctuation.
    """
    if not text:
        return ""
    
    result = text
    for pattern, masked in _WORD_PATTERNS:
        def replace_match(m: re.Match) -> str:
            orig = m.group(0)
            return _match_case(orig, masked)
        result = pattern.sub(replace_match, result)
        
    return result


def contains_profanity(text: str) -> bool:
    """Check if text contains any recognized high-risk or profanity terms."""
    if not text:
        return False
    for pattern, _ in _WORD_PATTERNS:
        if pattern.search(text):
            return True
    return False
