"""
StreamClipper / LumiClip — Word-Level Animated Subtitle Engine
Generates Advanced SubStation Alpha (.ass) subtitle files with millisecond-precise
karaoke tags (\\k), pop animations, emoji injections, and exportable Remotion JSON timelines.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import config
from processor.subprocess_utils import ms_to_ass_timestamp

logger = logging.getLogger("streamclipper.captions_engine")


class SubtitleStyle(str, Enum):
    GLACIER_GLOW = "glacier_glow"
    HORMOZI = "hormozi"
    MRBEAST = "mrbeast"
    NEON = "neon"
    TIKTOK_BOLD = "tiktok_bold"
    MINIMAL_CLEAN = "minimal_clean"


def normalize_subtitle_style(style_input: Any) -> SubtitleStyle:
    """
    Robust normalization supporting all frontend and backend style aliases.
    Guarantees no unintended fallback to GLACIER_GLOW.
    """
    if isinstance(style_input, SubtitleStyle):
        return style_input

    raw = str(style_input or "").strip().lower().replace(" ", "_").replace("-", "_")

    if raw in ("hormozi", "harmazi", "harmazi_yellow", "hormozi_yellow", "alex_hormozi", "yellow"):
        return SubtitleStyle.HORMOZI
    if raw in ("mrbeast", "mr_beast", "beast", "hype", "green"):
        return SubtitleStyle.MRBEAST
    if raw in ("tiktok_bold", "tiktok", "bold", "proxima"):
        return SubtitleStyle.TIKTOK_BOLD
    if raw in ("neon", "neon_cyber", "cyber", "cyber_neon", "neon_glow", "magenta"):
        return SubtitleStyle.NEON
    if raw in ("minimal_clean", "clean_sans", "clean", "minimal", "sans", "simple"):
        return SubtitleStyle.MINIMAL_CLEAN
    if raw in ("glacier_glow", "glacier", "cyan", "ice"):
        return SubtitleStyle.GLACIER_GLOW

    try:
        return SubtitleStyle(raw)
    except ValueError:
        return SubtitleStyle.GLACIER_GLOW


@dataclass
class CaptionWord:
    word: str
    start_ms: int
    end_ms: int
    emoji: Optional[str] = None

    @property
    def duration_cs(self) -> int:
        """Duration in centiseconds (10ms units) for ASS \\k tags."""
        return max(1, (self.end_ms - self.start_ms) // 10)


@dataclass
class CaptionBlock:
    words: List[CaptionWord] = field(default_factory=list)
    start_ms: int = 0
    end_ms: int = 0
    text: str = ""


from processor.censor import censor_word

# Verified high-retention gaming/streamer emoji keyword dictionary
EMOJI_KEYWORDS: Dict[str, str] = {
    # High-retention action / clutch
    "clutch": "🔥",
    "insane": "🤯",
    "crazy": "😱",
    "cracked": "⚡",
    "ace": "🎯",
    "headshot": "🎯",
    "toxic": "☣️",
    "diff": "💥",
    "dub": "🏆",
    "win": "🏆",
    "winning": "🏆",
    "won": "🏆",
    "goat": "🐐",
    "1v1": "⚔️",
    "fight": "🥊",
    "fast": "⚡",
    "fire": "🔥",
    "boss": "👑",
    # Economy & wealth
    "money": "💰",
    "dollars": "💵",
    "rich": "💎",
    # Eliminations
    "kill": "💀",
    "dead": "💀",
    "death": "💀",
    "rip": "🪦",
    # Emotions & reactions
    "rage": "🤬",
    "angry": "😡",
    "scary": "👻",
    "omg": "😱",
    "shock": "⚡",
    "gg": "🔥",
    "love": "❤️",
    "laugh": "😂",
    "hilarious": "🤣",
    "pog": "😲",
    "sheesh": "🥶",
    "hype": "🚀",
    "ez": "😎",
    "no": "❌",
    "stop": "🛑",
    "w": "🏆",
    "l": "📉",
}


class CaptionsEngine:
    """Renders high-retention, word-level animated subtitles in ASS & JSON format."""

    # ASS Header Templates for styles. Color format: &HAABBGGRR (Alpha, Blue, Green, Red in Hex)
    # Using confirmed Windows-native ultra-heavy fonts (Impact, Arial Black, Segoe UI Bold)
    STYLE_HEADERS: Dict[SubtitleStyle, str] = {
        SubtitleStyle.GLACIER_GLOW: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Arial Black,76,&H00FFFFFF,&H00FFF000,&H00000000,&H90000000,-1,0,0,0,100,100,2,0,1,10,4,2,40,40,320,1
Style: Highlight,Arial Black,82,&H00FFF000,&H00FFFFFF,&H00000000,&H00FFF000,-1,0,0,0,118,118,2,0,1,12,8,2,40,40,320,1
""",
        SubtitleStyle.HORMOZI: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Impact,88,&H00FFFFFF,&H0000E6FF,&H00000000,&HA0000000,-1,0,0,0,100,100,2,0,1,11,5,2,40,40,420,1
Style: Highlight,Impact,96,&H0000E6FF,&H00000000,&H00000000,&H80000000,-1,0,0,0,122,122,2,0,1,14,8,2,40,40,420,1
""",
        SubtitleStyle.MRBEAST: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Impact,88,&H00FFFFFF,&H0044FF00,&H00000000,&HA0000000,-1,0,0,0,100,100,2,0,1,11,5,2,40,40,420,1
Style: Highlight,Impact,96,&H0044FF00,&H00000000,&H00000000,&H80000000,-1,0,0,0,122,122,2,0,1,14,8,2,40,40,420,1
""",
        SubtitleStyle.NEON: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Arial Black,76,&H00FFFFFF,&H0000FFFF,&H00B400FF,&HA0000000,-1,0,0,0,100,100,2,0,1,10,12,2,40,40,300,1
Style: Highlight,Arial Black,82,&H0000FFFF,&H00000000,&H00000000,&H00B400FF,-1,0,0,0,118,118,2,0,1,12,16,2,40,40,300,1
""",
        SubtitleStyle.TIKTOK_BOLD: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Impact,82,&H00FFFFFF,&H0000D0FF,&H00000000,&HA0000000,-1,0,0,0,100,100,2,0,1,10,5,2,40,40,320,1
Style: Highlight,Impact,90,&H0000D0FF,&H00000000,&H00000000,&HA0000000,-1,0,0,0,120,120,2,0,1,12,8,2,40,40,320,1
""",
        SubtitleStyle.MINIMAL_CLEAN: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Segoe UI,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,8,4,2,40,40,280,1
Style: Highlight,Segoe UI,74,&H00FFFFFF,&H00000000,&H00000000,&HA0000000,-1,0,0,0,112,112,1,0,1,10,6,2,40,40,280,1
""",
    }

    def __init__(self, default_style: SubtitleStyle = SubtitleStyle.GLACIER_GLOW):
        self.default_style = default_style

    def parse_whisper_words(
        self,
        transcript_segments: list,
        base_offset_ms: int = 0,
        words_per_group: int = 4
    ) -> List[CaptionBlock]:
        """
        Group millisecond-accurate Whisper words into cohesive 2-4 word screen blocks.
        Applies profanity and demonetization censoring to every word token.
        """
        all_words: List[CaptionWord] = []

        for seg in transcript_segments:
            seg_words = getattr(seg, "words", None) if hasattr(seg, "words") else (seg.get("words", []) if isinstance(seg, dict) else [])
            if not seg_words:
                # Fallback: estimate timestamps if word_timestamps wasn't returned
                text = (getattr(seg, "text", "") if hasattr(seg, "text") else seg.get("text", "") if isinstance(seg, dict) else "").strip()
                if not text:
                    continue
                s_sec = getattr(seg, "start", 0) if hasattr(seg, "start") else seg.get("start", 0) if isinstance(seg, dict) else 0
                e_sec = getattr(seg, "end", 0) if hasattr(seg, "end") else seg.get("end", 0) if isinstance(seg, dict) else 0
                s_ms = int(s_sec * 1000) - base_offset_ms
                e_ms = int(e_sec * 1000) - base_offset_ms
                split = text.split()
                if not split:
                    continue
                step = max(1, (e_ms - s_ms) // max(1, len(split)))
                for idx, w in enumerate(split):
                    w_clean = censor_word(w.strip())
                    emoji = self._lookup_emoji(w.strip())
                    all_words.append(
                        CaptionWord(
                            word=w_clean,
                            start_ms=max(0, s_ms + idx * step),
                            end_ms=max(0, s_ms + (idx + 1) * step),
                            emoji=emoji
                        )
                    )
            else:
                for w_obj in seg_words:
                    word_txt = (getattr(w_obj, "word", "") if hasattr(w_obj, "word") else w_obj.get("word", "") if isinstance(w_obj, dict) else "").strip()
                    if not word_txt:
                        continue
                    w_s_sec = getattr(w_obj, "start", 0) if hasattr(w_obj, "start") else w_obj.get("start", 0) if isinstance(w_obj, dict) else 0
                    w_e_sec = getattr(w_obj, "end", 0) if hasattr(w_obj, "end") else w_obj.get("end", 0) if isinstance(w_obj, dict) else 0
                    w_s = int(w_s_sec * 1000) - base_offset_ms
                    w_e = int(w_e_sec * 1000) - base_offset_ms
                    emoji = self._lookup_emoji(word_txt)
                    censored_txt = censor_word(word_txt)
                    all_words.append(
                        CaptionWord(
                            word=censored_txt,
                            start_ms=max(0, w_s),
                            end_ms=max(0, w_e),
                            emoji=emoji
                        )
                    )

        # Chunk words into display blocks
        blocks: List[CaptionBlock] = []
        for i in range(0, len(all_words), words_per_group):
            group = all_words[i:i + words_per_group]
            if not group:
                continue
            block_start = group[0].start_ms
            block_end = group[-1].end_ms
            block_text = " ".join(cw.word for cw in group)
            blocks.append(
                CaptionBlock(
                    words=group,
                    start_ms=block_start,
                    end_ms=block_end,
                    text=block_text
                )
            )

        return blocks

    def generate_ass(
        self,
        clip_id: str,
        transcript_segments: list,
        output_path: Optional[Path] = None,
        style: Union[SubtitleStyle, str] = SubtitleStyle.GLACIER_GLOW,
        base_offset_ms: int = 0,
        layout_type: str = "",
    ) -> Path:
        """
        Generate a fully styled .ass file with karaoke word highlighting.
        Supports layout-specific vertical positioning (e.g. bottom margin for white_canvas).
        """
        if output_path is None:
            output_path = config.CLIPS_DIR / f"{clip_id}.ass"

        style_enum = normalize_subtitle_style(style)
        words_per_grp = 2 if style_enum in (SubtitleStyle.HORMOZI, SubtitleStyle.MRBEAST, SubtitleStyle.TIKTOK_BOLD) else 4
        blocks = self.parse_whisper_words(transcript_segments, base_offset_ms=base_offset_ms, words_per_group=words_per_grp)
        style_header = self.STYLE_HEADERS.get(style_enum, self.STYLE_HEADERS[SubtitleStyle.GLACIER_GLOW])

        # Layout-aware vertical positioning:
        # white_canvas: bottom white zone center is y=1592 -> MarginV=300 from bottom of 1920 canvas
        # 9:16 full-bleed: lower-third safe zone -> MarginV=420 from bottom (above TikTok/Reels UI)
        is_white_canvas = layout_type in ("white_canvas", "16_9_white", "white_letterbox")
        target_margin_v = 300 if is_white_canvas else 420
        style_header = re.sub(r'(,\s*\d+\s*,\s*\d+\s*,)\s*\d+(\s*,\s*1\s*$)', rf'\g<1>{target_margin_v}\2', style_header, flags=re.MULTILINE)

        lines = [
            style_header,
            "\n[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]

        for block in blocks:
            # Generate word-by-word active pop timeline within the block
            for active_idx, active_word in enumerate(block.words):
                w_start_ts = ms_to_ass_timestamp(active_word.start_ms)
                w_end_ts = ms_to_ass_timestamp(active_word.end_ms)

                # Assemble line with highlighted word
                rendered_parts: List[str] = []
                for idx, cw in enumerate(block.words):
                    word_str = cw.word.upper()
                    if idx == active_idx:
                        # Add scale pop animation and active color
                        if cw.emoji:
                            rendered_parts.append(f"{{\\rHighlight\\t(0,80,\\fscx115\\fscy115)}}{word_str} {cw.emoji}{{\\rBase}}")
                        else:
                            rendered_parts.append(f"{{\\rHighlight\\t(0,80,\\fscx115\\fscy115)}}{word_str}{{\\rBase}}")
                    else:
                        rendered_parts.append(f"{{\\rBase}}{word_str}")

                dialogue_text = " ".join(rendered_parts)
                lines.append(f"Dialogue: 0,{w_start_ts},{w_end_ts},Base,,0,0,0,,{dialogue_text}")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Generated ASS karaoke captions (%s style) -> %s", style_enum.value, output_path)
        return output_path

    def generate_json_timeline(
        self,
        transcript_segments: list,
        base_offset_ms: int = 0,
        style: Union[SubtitleStyle, str] = SubtitleStyle.GLACIER_GLOW
    ) -> Dict[str, Any]:
        """
        Export Remotion-compatible JSON timeline payload with millisecond word timestamps.
        """
        style_enum = normalize_subtitle_style(style)
        blocks = self.parse_whisper_words(transcript_segments, base_offset_ms=base_offset_ms)
        
        timeline_data = {
            "style": style_enum.value,
            "blocks": []
        }

        for block in blocks:
            b_dict = {
                "start_ms": block.start_ms,
                "end_ms": block.end_ms,
                "text": block.text,
                "words": [asdict(w) for w in block.words]
            }
            timeline_data["blocks"].append(b_dict)

        return timeline_data

    @staticmethod
    def _lookup_emoji(word: str) -> Optional[str]:
        """Match word against high-retention emoji keywords."""
        cleaned = "".join(c for c in word.lower() if c.isalnum())
        return EMOJI_KEYWORDS.get(cleaned)
