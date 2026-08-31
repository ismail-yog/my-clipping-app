"""Dream Team — Shared Tool Functions
Utility functions that any agent can register and call via use_tool().
Covers video helpers, text analysis, profanity filtering, and formatting.
"""
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("dreamteam.tools")


# ══════════════════════════════════════════════════════════════════════
# Video / Media helpers
# ══════════════════════════════════════════════════════════════════════

def get_video_duration(path: str) -> Optional[float]:
    """Return the duration of a video file in seconds using ffprobe.

    Returns None if ffprobe fails or the file doesn't exist.
    """
    path = str(path)
    if not Path(path).exists():
        logger.warning("get_video_duration: file not found — %s", path)
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        logger.debug("Video duration: %.2fs — %s", duration, path)
        return duration
    except Exception as exc:
        logger.error("get_video_duration failed: %s", exc)
        return None


def extract_frame(video_path: str, timestamp: float, output_path: Optional[str] = None) -> Optional[str]:
    """Extract a single frame from *video_path* at *timestamp* seconds.

    Args:
        video_path: Path to the source video.
        timestamp: Time in seconds to extract the frame.
        output_path: Where to save the frame (default: same dir, ``_frame.jpg``).

    Returns:
        The output path on success, or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        logger.warning("extract_frame: file not found — %s", video_path)
        return None

    if output_path is None:
        output_path = str(video_path.parent / f"{video_path.stem}_frame.jpg")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1", "-q:v", "2",
                str(output_path),
            ],
            capture_output=True, timeout=15,
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
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-select_streams", "v:0",
                str(path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return {"width": int(stream["width"]), "height": int(stream["height"])}
    except Exception as exc:
        logger.error("get_video_resolution failed: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════
# Text analysis
# ══════════════════════════════════════════════════════════════════════

def count_words(text: str) -> int:
    """Count the number of whitespace-delimited words in *text*."""
    return len(text.split())


def detect_language(text: str) -> str:
    """Simple heuristic language detection.

    Returns an ISO 639-1 code (e.g. ``"en"``, ``"es"``, ``"fr"``).
    Falls back to ``"en"`` if unsure.
    """
    # Very small sample → default
    if not text or len(text) < 20:
        return "en"

    text_lower = text.lower()

    # Spanish markers
    spanish_markers = ["el ", "la ", "los ", "las ", "de ", "que ", "en ", "por ", "para ",
                       "con ", "una ", "como ", "pero ", "más ", "este ", "esta "]
    # French markers
    french_markers = ["le ", "la ", "les ", "de ", "des ", "un ", "une ", "que ",
                      "est ", "dans ", "pour ", "avec ", "sur ", "pas ", "ce "]
    # German markers
    german_markers = ["der ", "die ", "das ", "und ", "ist ", "ein ", "eine ",
                      "für ", "mit ", "auf ", "den ", "dem ", "nicht "]
    # Portuguese markers
    portuguese_markers = ["o ", "a ", "os ", "as ", "de ", "que ", "em ",
                          "um ", "uma ", "para ", "com ", "não ", "por "]

    scores = {
        "es": sum(1 for m in spanish_markers if m in text_lower),
        "fr": sum(1 for m in french_markers if m in text_lower),
        "de": sum(1 for m in german_markers if m in text_lower),
        "pt": sum(1 for m in portuguese_markers if m in text_lower),
    }

    best = max(scores, key=scores.get)
    if scores[best] >= 3:
        return best
    return "en"


# ══════════════════════════════════════════════════════════════════════
# Content safety
# ══════════════════════════════════════════════════════════════════════

# Basic profanity word list (kept deliberately short & PG-13).
_PROFANITY_LIST = {
    "fuck", "shit", "bitch", "ass", "damn", "crap", "dick", "piss",
    "bastard", "slut", "whore", "cock", "cunt", "twat", "wanker",
    "asshole", "bullshit", "motherfucker", "nigger", "nigga", "faggot",
    "retard", "retarded",
}

# Compiled regex for whole-word matching
_PROFANITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _PROFANITY_LIST) + r")\b",
    re.IGNORECASE,
)


def is_profane(text: str) -> bool:
    """Return True if *text* contains profanity from the built-in word list."""
    return bool(_PROFANITY_PATTERN.search(text))


def censor_profanity(text: str) -> str:
    """Replace profane words with asterisks (e.g. ``f***``)."""
    def _mask(match):
        word = match.group(0)
        if len(word) <= 2:
            return "*" * len(word)
        return word[0] + "*" * (len(word) - 2) + word[-1]
    return _PROFANITY_PATTERN.sub(_mask, text)


# ══════════════════════════════════════════════════════════════════════
# Formatting helpers
# ══════════════════════════════════════════════════════════════════════

def format_duration(seconds: float) -> str:
    """Convert seconds to ``MM:SS`` or ``HH:MM:SS`` string."""
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:02d}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "…") -> str:
    """Truncate *text* to *max_length* characters, adding *suffix* if trimmed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)].rstrip() + suffix


def slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


# ══════════════════════════════════════════════════════════════════════
# File helpers
# ══════════════════════════════════════════════════════════════════════

def safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON file, returning None on any error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("safe_read_json(%s) failed: %s", path, exc)
        return None


def safe_write_json(path: str, data: Any, indent: int = 2) -> bool:
    """Write *data* as JSON to *path*. Returns True on success."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except Exception as exc:
        logger.error("safe_write_json(%s) failed: %s", path, exc)
        return False


def get_file_size_mb(path: str) -> Optional[float]:
    """Return the file size in megabytes, or None if the file doesn't exist."""
    p = Path(path)
    if p.exists():
        return p.stat().st_size / (1024 * 1024)
    return None


# ══════════════════════════════════════════════════════════════════════
# Registry — convenient dict of all tools for agent registration
# ══════════════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, callable] = {
    "get_video_duration": get_video_duration,
    "extract_frame": extract_frame,
    "get_video_resolution": get_video_resolution,
    "count_words": count_words,
    "detect_language": detect_language,
    "is_profane": is_profane,
    "censor_profanity": censor_profanity,
    "format_duration": format_duration,
    "truncate_text": truncate_text,
    "slugify": slugify,
    "safe_read_json": safe_read_json,
    "safe_write_json": safe_write_json,
    "get_file_size_mb": get_file_size_mb,
}
