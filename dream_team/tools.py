"""Dream Team — Shared Tool Functions
Utility functions that any agent can register and call via use_tool().
Covers video helpers, text analysis, profanity filtering, and formatting.
Uses production subprocess execution with strict timeouts and memory cleanup.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from processor.subprocess_utils import run_command_safely, safe_unlink, free_vram

logger = logging.getLogger("dreamteam.tools")


# ══════════════════════════════════════════════════════════════════════
# Video / Media helpers
# ══════════════════════════════════════════════════════════════════════

def get_video_duration(path: str) -> Optional[float]:
    """Return the duration of a video file in seconds using ffprobe safely."""
    path_obj = Path(str(path))
    if not path_obj.exists():
        logger.warning("get_video_duration: file not found — %s", path)
        return None
    try:
        result = run_command_safely(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", str(path_obj),
            ],
            timeout=15.0,
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        logger.debug("Video duration: %.2fs — %s", duration, path)
        return duration
    except Exception as exc:
        logger.error("get_video_duration failed: %s", exc)
        return None


def extract_frame(video_path: str, timestamp: float, output_path: Optional[str] = None) -> Optional[str]:
    """Extract a single frame from *video_path* at *timestamp* seconds."""
    video_path_obj = Path(str(video_path))
    if not video_path_obj.exists():
        logger.warning("extract_frame: file not found — %s", video_path)
        return None

    if output_path is None:
        output_path = str(video_path_obj.parent / f"{video_path_obj.stem}_frame.jpg")

    try:
        run_command_safely(
            [
                "ffmpeg", "-y", "-ss", str(timestamp),
                "-i", str(video_path_obj),
                "-vframes", "1", "-q:v", "2",
                str(output_path),
            ],
            timeout=15.0,
        )
        if Path(output_path).exists():
            logger.debug("Frame extracted → %s", output_path)
            return str(output_path)
    except Exception as exc:
        logger.error("extract_frame failed: %s", exc)
    return None


def get_video_resolution(path: str) -> Optional[Dict[str, int]]:
    """Return ``{"width": …, "height": …}`` for a video file."""
    try:
        result = run_command_safely(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-select_streams", "v:0",
                str(path),
            ],
            timeout=15.0,
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return {"width": int(stream["width"]), "height": int(stream["height"])}
    except Exception as exc:
        logger.error("get_video_resolution failed: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════
# Text & NLP helpers
# ══════════════════════════════════════════════════════════════════════

# Common English profanities / slurs list for moderation
PROFANITY_LIST = {
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt",
    "dick", "pussy", "fag", "faggot", "nigger", "nigga",
    "retard", "slut", "whore", "cock", "tits", "motherfucker",
}


def check_profanity(text: str) -> Dict[str, Any]:
    """Check text for profane words."""
    if not text:
        return {"clean": True, "count": 0, "flagged_words": []}

    words = re.findall(r"\b\w+\b", text.lower())
    flagged = [w for w in words if w in PROFANITY_LIST]

    return {
        "clean": len(flagged) == 0,
        "count": len(flagged),
        "flagged_words": list(set(flagged)),
    }


def extract_keywords(text: str, top_n: int = 5) -> List[str]:
    """Extract most frequent non-stop words from text."""
    if not text:
        return []

    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "over", "after",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "i", "you", "he", "she", "it", "we",
        "they", "what", "which", "who", "this", "that", "these", "those",
        "my", "your", "his", "her", "its", "our", "their", "not", "no",
        "so", "very", "just", "like", "im", "dont", "cant", "thats", "theres",
    }

    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    filtered = [w for w in words if w not in stopwords]

    freq: Dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.items(), key=lambda item: item[1], reverse=True)
    return [w for w, _ in sorted_words[:top_n]]


def calculate_hook_strength(title: str) -> Dict[str, Any]:
    """Score title based on hook heuristics."""
    if not title:
        return {"score": 0.0, "feedback": ["Title is empty"]}

    score = 0.5
    feedback: List[str] = []

    words = title.split()
    if 3 <= len(words) <= 9:
        score += 0.15
        feedback.append("Good word count for short video hook (3-9 words)")
    elif len(words) < 3:
        score -= 0.1
        feedback.append("Title too short — lack of curiosity gap")
    else:
        score -= 0.1
        feedback.append("Title too long for quick hook impact")

    power_words = [
        "never", "secret", "insane", "how to", "why", "stop", "biggest",
        "worst", "best", "finally", "exposed", "truth", "unbelievable",
        "clutch", "impossible", "ruined", "broke", "won", "lost", "nobody",
    ]
    title_lower = title.lower()
    found_power = [w for w in power_words if w in title_lower]
    if found_power:
        score += min(0.2, len(found_power) * 0.1)
        feedback.append(f"Power words detected: {', '.join(found_power)}")
    else:
        feedback.append("No common power words found — add curiosity triggers")

    if "?" in title:
        score += 0.05
        feedback.append("Question format creates curiosity")

    if any(ch.isdigit() for ch in title):
        score += 0.05
        feedback.append("Contains numbers (increases specificity)")

    final_score = round(max(0.0, min(1.0, score)), 2)
    return {
        "score": final_score,
        "rating": "strong" if final_score >= 0.7 else "medium" if final_score >= 0.4 else "weak",
        "feedback": feedback,
    }


def format_hashtag_string(tags: List[str]) -> str:
    """Format tags list into hashtag string."""
    clean_tags = []
    for t in tags:
        clean = re.sub(r"[^\w]", "", t.strip())
        if clean:
            clean_tags.append(f"#{clean}")
    return " ".join(clean_tags)
