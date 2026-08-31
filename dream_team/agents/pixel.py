"""Dream Team — Pixel Agent
The Visual Artist: enhances thumbnails with text overlays and styling.

Pixel provides:
    - Thumbnail text generation (LLM-powered, attention-grabbing)
    - Thumbnail image analysis (PIL-based with heuristic fallback)
    - Emotion-based color scheme suggestions
    - Full visual enhancement pipeline for clip metadata
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory
from dream_team.tools import extract_frame, get_video_resolution


# ── Emotion → colour palettes ──────────────────────────────────────────
_EMOTION_COLORS: Dict[str, Dict[str, str]] = {
    "anger": {
        "primary": "#E53935",
        "secondary": "#B71C1C",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
    "joy": {
        "primary": "#FFD600",
        "secondary": "#F9A825",
        "text_color": "#000000",
        "outline_color": "#FFFFFF",
    },
    "surprise": {
        "primary": "#FF9100",
        "secondary": "#E65100",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
    "sadness": {
        "primary": "#1E88E5",
        "secondary": "#0D47A1",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
    "fear": {
        "primary": "#8E24AA",
        "secondary": "#4A148C",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
    "disgust": {
        "primary": "#43A047",
        "secondary": "#1B5E20",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
    "neutral": {
        "primary": "#00E5FF",
        "secondary": "#00B8D4",
        "text_color": "#FFFFFF",
        "outline_color": "#000000",
    },
}

_DEFAULT_COLORS = _EMOTION_COLORS["neutral"]

# Emoji map for thumbnail text decoration
_EMOTION_EMOJI: Dict[str, str] = {
    "anger": "🔥",
    "joy": "😂",
    "surprise": "😱",
    "sadness": "😢",
    "fear": "😨",
    "disgust": "🤢",
    "neutral": "⚡",
}


class Pixel(BaseAgent):
    """Visual Artist agent — enhances thumbnails with text overlays and styling.

    Attributes:
        memory: Shared memory store for cross-agent communication.
        cfg: Agent-specific configuration from ``config.PIXEL_CONFIG``.
    """

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="pixel",
            description="Visual Artist — enhances thumbnails with text overlays and styling.",
            agent_config=config.PIXEL_CONFIG,
        )
        self.memory = memory
        self.cfg: Dict[str, Any] = config.PIXEL_CONFIG

        # Register visual tools
        self.register_tool("extract_frame", extract_frame)
        self.register_tool("get_video_resolution", get_video_resolution)

        self.logger.info("Pixel initialised — config: %s", self.cfg)

    # ──────────────────────────────────────────────────────────────────
    # Thumbnail text generation (LLM-powered)
    # ──────────────────────────────────────────────────────────────────

    def suggest_thumbnail_text(self, title: str, emotion: str) -> str:
        """Generate short, punchy thumbnail text for a clip.

        Uses :py:meth:`self.think` to produce 2–5 bold words designed to
        grab attention on a YouTube Shorts thumbnail.

        Args:
            title: The clip title to base the text on.
            emotion: Dominant emotion (e.g. ``"joy"``, ``"anger"``).

        Returns:
            A short string suitable for thumbnail overlay (2–5 words,
            uppercase, optionally with emoji).
        """
        self.logger.info(
            "suggest_thumbnail_text() — title=%r, emotion=%s", title[:60], emotion,
        )

        add_emoji = self.cfg.get("add_emoji", True)
        style = self.cfg.get("style", "bold")

        emoji_instruction = ""
        if add_emoji:
            emoji = _EMOTION_EMOJI.get(emotion, "⚡")
            emoji_instruction = (
                f" Include exactly ONE relevant emoji (suggested: {emoji})."
            )

        prompt = (
            "You are a YouTube thumbnail text expert. Generate a SHORT, "
            f"{style.upper()} thumbnail overlay text (2-5 words MAXIMUM) for this clip.\n\n"
            f"Title: {title}\n"
            f"Emotion: {emotion}\n\n"
            "Rules:\n"
            "- ALL CAPS\n"
            "- 2-5 words only, be punchy and attention-grabbing\n"
            "- Match the emotional tone\n"
            f"{emoji_instruction}\n"
            "- Return ONLY the text, nothing else."
        )

        try:
            response = self.think(prompt, temperature=0.8, max_tokens=30)
            text = self._clean_thumbnail_text(response)
        except Exception as exc:
            self.logger.error("suggest_thumbnail_text() LLM failed: %s", exc)
            # Deterministic fallback: first 3 words of title, uppercased
            words = title.upper().split()[:3]
            text = " ".join(words)
            if add_emoji:
                emoji = _EMOTION_EMOJI.get(emotion, "⚡")
                text = f"{emoji} {text}"

        self.remember("last_thumbnail_text", text)
        self.logger.info("suggest_thumbnail_text() → %r", text)
        return text

    # ──────────────────────────────────────────────────────────────────
    # Thumbnail analysis
    # ──────────────────────────────────────────────────────────────────

    def analyze_thumbnail(self, image_path: str) -> dict:
        """Analyse a thumbnail image and return quality metadata.

        Attempts to use **PIL/Pillow** for actual image analysis; falls
        back to a heuristic based on file size and extension.

        Args:
            image_path: Absolute path to the thumbnail image file.

        Returns:
            A dict with::

                {
                    "brightness": "dark" | "medium" | "bright",
                    "has_text": bool,
                    "suggested_improvements": [str, ...],
                    "score": float,   # 0.0–1.0
                }
        """
        self.logger.info("analyze_thumbnail() — path=%s", image_path)

        path = Path(image_path)
        if not path.exists():
            self.logger.warning("analyze_thumbnail() — file not found: %s", image_path)
            return {
                "brightness": "unknown",
                "has_text": False,
                "suggested_improvements": ["Thumbnail file not found"],
                "score": 0.0,
            }

        # Try PIL-based analysis
        try:
            return self._analyze_with_pil(path)
        except Exception as exc:
            self.logger.info(
                "PIL analysis unavailable (%s), using heuristic fallback", exc,
            )
            return self._analyze_heuristic(path)

    def _analyze_with_pil(self, path: Path) -> dict:
        """Perform thumbnail analysis using PIL/Pillow."""
        from PIL import Image, ImageStat  # type: ignore[import-untyped]

        img = Image.open(path).convert("RGB")
        stat = ImageStat.Stat(img)

        # Average brightness (0–255)
        avg_brightness = sum(stat.mean) / 3
        if avg_brightness < 85:
            brightness = "dark"
        elif avg_brightness > 170:
            brightness = "bright"
        else:
            brightness = "medium"

        # Resolution quality
        width, height = img.size
        is_hd = width >= 1280 and height >= 720

        # Contrast heuristic (stddev of pixel values)
        avg_stddev = sum(stat.stddev) / 3
        has_high_contrast = avg_stddev > 50

        # Text detection heuristic: high local contrast often indicates text
        # (rough approximation — real text detection needs OCR)
        has_text = avg_stddev > 60

        # Scoring
        improvements: List[str] = []
        score = 0.7  # base

        if brightness == "dark":
            improvements.append("Image is dark — consider increasing brightness")
            score -= 0.1
        elif brightness == "bright":
            improvements.append("Image is very bright — ensure text remains readable")
            score -= 0.05

        if not is_hd:
            improvements.append(f"Low resolution ({width}×{height}) — aim for 1280×720+")
            score -= 0.15

        if not has_high_contrast:
            improvements.append("Low contrast — bold colours improve click-through rate")
            score -= 0.1

        if not has_text:
            improvements.append("No text overlay detected — add punchy text for engagement")
            score -= 0.1

        # Aspect ratio check (9:16 ideal for Shorts)
        aspect = width / max(height, 1)
        if aspect > 1.0:
            improvements.append("Landscape orientation — Shorts perform best at 9:16 portrait")
            score -= 0.1

        score = round(max(0.0, min(1.0, score)), 2)

        return {
            "brightness": brightness,
            "has_text": has_text,
            "suggested_improvements": improvements,
            "score": score,
        }

    @staticmethod
    def _analyze_heuristic(path: Path) -> dict:
        """Fallback thumbnail analysis using file metadata only."""
        file_size_kb = path.stat().st_size / 1024
        suffix = path.suffix.lower()

        improvements: List[str] = []
        score = 0.5  # uncertain baseline

        if file_size_kb < 20:
            improvements.append("Very small file — possibly low quality or placeholder")
            score -= 0.2
        elif file_size_kb > 5000:
            improvements.append("Large file — consider compressing for faster load times")
            score -= 0.05

        if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
            improvements.append(f"Unusual format ({suffix}) — use JPG or PNG for compatibility")
            score -= 0.1

        improvements.append("Install Pillow for detailed image analysis (pip install Pillow)")
        score = round(max(0.0, min(1.0, score)), 2)

        return {
            "brightness": "unknown",
            "has_text": False,
            "suggested_improvements": improvements,
            "score": score,
        }

    # ──────────────────────────────────────────────────────────────────
    # Colour scheme suggestion
    # ──────────────────────────────────────────────────────────────────

    def suggest_colors(self, emotion: str) -> dict:
        """Return a colour scheme tailored to the given emotion.

        Args:
            emotion: The dominant emotion string (e.g. ``"anger"``,
                ``"joy"``, ``"surprise"``).

        Returns:
            A dict with hex colour codes::

                {
                    "primary": "#RRGGBB",
                    "secondary": "#RRGGBB",
                    "text_color": "#RRGGBB",
                    "outline_color": "#RRGGBB",
                }
        """
        self.logger.info("suggest_colors() — emotion=%s", emotion)

        colors = _EMOTION_COLORS.get(emotion.lower(), _DEFAULT_COLORS)

        self.remember("last_color_scheme", colors)
        self.logger.info("suggest_colors() → primary=%s", colors["primary"])
        return dict(colors)  # return a copy

    # ──────────────────────────────────────────────────────────────────
    # Full visual enhancement pipeline
    # ──────────────────────────────────────────────────────────────────

    def enhance_clip_visuals(self, clip_data: dict) -> dict:
        """Run the full visual enhancement pipeline on a clip.

        Generates thumbnail text, selects a colour scheme, and optionally
        analyses an existing thumbnail — then attaches all visual metadata
        to the returned clip data.

        Args:
            clip_data: Dictionary with keys such as *title*, *emotion*,
                *thumbnail_path*, *video_path*, etc.

        Returns:
            A copy of *clip_data* enriched with a ``visual_metadata`` key::

                {
                    ...original clip_data...,
                    "visual_metadata": {
                        "thumbnail_text": str,
                        "colors": {...},
                        "style": str,
                        "thumbnail_analysis": {...} | None,
                        "suggested_frame_time": float | None,
                    },
                }
        """
        self.logger.info("enhance_clip_visuals() — starting visual pipeline")

        title: str = clip_data.get("title", "Epic Moment")
        emotion: str = clip_data.get("emotion", "neutral")
        thumbnail_path: Optional[str] = clip_data.get("thumbnail_path")
        video_path: Optional[str] = clip_data.get("video_path")

        # 1. Generate thumbnail text
        thumbnail_text = self.suggest_thumbnail_text(title, emotion)

        # 2. Select colour scheme
        colors = self.suggest_colors(emotion)

        # 3. Analyse existing thumbnail (if available)
        thumbnail_analysis: Optional[dict] = None
        if thumbnail_path and Path(thumbnail_path).exists():
            thumbnail_analysis = self.analyze_thumbnail(thumbnail_path)

        # 4. Suggest a frame extraction time (simple heuristic)
        suggested_frame_time: Optional[float] = None
        if video_path and Path(video_path).exists():
            # Use the 30% mark — typically a good "action" moment for Shorts
            try:
                from dream_team.tools import get_video_duration

                duration = get_video_duration(video_path)
                if duration and duration > 0:
                    suggested_frame_time = round(duration * 0.30, 2)
                    self.logger.info(
                        "Suggested frame extraction at %.2fs (30%% of %.2fs)",
                        suggested_frame_time, duration,
                    )
            except Exception as exc:
                self.logger.warning("Could not determine video duration: %s", exc)

        # 5. Assemble visual metadata
        visual_metadata = {
            "thumbnail_text": thumbnail_text,
            "colors": colors,
            "style": self.cfg.get("style", "bold"),
            "thumbnail_analysis": thumbnail_analysis,
            "suggested_frame_time": suggested_frame_time,
        }

        # Return enriched clip data (non-destructive copy)
        enhanced = dict(clip_data)
        enhanced["visual_metadata"] = visual_metadata

        # Persist in shared memory
        clip_id = clip_data.get("id", clip_data.get("title", "unknown"))
        self.memory.store(
            key=f"pixel_visuals_{clip_id}",
            value=visual_metadata,
            category="clips",
            agent=self.name,
        )
        self.remember("last_visual_enhancement", visual_metadata)

        self.logger.info(
            "enhance_clip_visuals() complete — text=%r, primary=%s",
            thumbnail_text, colors["primary"],
        )
        return enhanced

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_thumbnail_text(raw: str) -> str:
        """Sanitise LLM output into clean thumbnail text.

        Strips quotes, markdown, and excessive whitespace.
        """
        text = raw.strip()
        # Remove markdown formatting
        text = re.sub(r"[*_`#]", "", text)
        # Remove surrounding quotes
        text = text.strip("\"'""''")
        # Collapse whitespace
        text = " ".join(text.split())
        # Enforce uppercase
        text = text.upper()
        # Truncate to a reasonable length (prevent runaway LLM output)
        if len(text) > 50:
            text = text[:50].rsplit(" ", 1)[0]
        return text
