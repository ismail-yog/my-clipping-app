"""
StreamClipper / LumiClip — Word-Level Animated Subtitle Engine
Generates Advanced SubStation Alpha (.ass) subtitle files with millisecond-precise
karaoke tags (\\k), pop animations, emoji injections, and exportable Remotion JSON timelines.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

import config
from processor.subprocess_utils import ms_to_ass_timestamp

logger = logging.getLogger("streamclipper.captions_engine")


class SubtitleStyle(str, Enum):
    HORMOZI = "hormozi"
    MRBEAST = "mrbeast"
    NEON = "neon"
    MINIMAL_CLEAN = "minimal_clean"


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


# Emoji keyword dictionary for automatic visual retention enhancement
EMOJI_KEYWORDS: Dict[str, str] = {
    "clutch": "🔥",
    "insane": "🤯",
    "crazy": "😱",
    "win": "🏆",
    "winning": "🏆",
    "won": "🏆",
    "money": "💰",
    "dollars": "💵",
    "kill": "💀",
    "dead": "💀",
    "death": "💀",
    "rage": "🤬",
    "angry": "😡",
    "scary": "👻",
    "omg": "😱",
    "gg": "🔥",
    "goat": "🐐",
    "1v1": "⚔️",
    "fight": "🥊",
    "love": "❤️",
    "laugh": "😂",
    "hilarious": "🤣",
    "no": "❌",
    "stop": "🛑",
    "fast": "⚡",
    "fire": "🔥",
    "boss": "👑",
}


class CaptionsEngine:
    """Renders high-retention, word-level animated subtitles in ASS & JSON format."""

    # ASS Header Templates for styles
    STYLE_HEADERS: Dict[str, str] = {
        SubtitleStyle.HORMOZI: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,4,2,40,40,320,1
Style: Highlight,Arial Black,76,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,110,110,2,0,1,10,6,2,40,40,320,1
""",
        SubtitleStyle.MRBEAST: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Impact,78,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,9,4,2,40,40,340,1
Style: Highlight,Impact,82,&H0000FF55,&H000000FF,&H00000000,&H80000000,-1,0,0,0,112,112,1,0,1,11,6,2,40,40,340,1
""",
        SubtitleStyle.NEON: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Montserrat ExtraBold,70,&H00FFFFFF,&H000000FF,&H00FF00AA,&H80000000,-1,0,0,0,100,100,2,0,1,6,12,2,40,40,300,1
Style: Highlight,Montserrat ExtraBold,74,&H00FFFF00,&H000000FF,&H00FF00AA,&H80000000,-1,0,0,0,108,108,2,0,1,8,16,2,40,40,300,1
""",
        SubtitleStyle.MINIMAL_CLEAN: """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Inter,64,&H00F5F5F5,&H000000FF,&H00111111,&H60000000,-1,0,0,0,100,100,1,0,1,4,2,2,40,40,280,1
Style: Highlight,Inter,66,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,104,104,1,0,1,5,4,2,40,40,280,1
""",
    }

    def __init__(self, default_style: SubtitleStyle = SubtitleStyle.HORMOZI):
        self.default_style = default_style

    def parse_whisper_words(
        self,
        transcript_segments: list,
        base_offset_ms: int = 0,
        words_per_group: int = 4
    ) -> List[CaptionBlock]:
        """
        Group millisecond-accurate Whisper words into cohesive 3-5 word screen blocks.
        """
        all_words: List[CaptionWord] = []

        for seg in transcript_segments:
            seg_words = seg.get("words", [])
            if not seg_words:
                # Fallback: estimate timestamps if word_timestamps wasn't returned
                text = seg.get("text", "").strip()
                if not text:
                    continue
                s_ms = int(seg.get("start", 0) * 1000) - base_offset_ms
                e_ms = int(seg.get("end", 0) * 1000) - base_offset_ms
                split = text.split()
                if not split:
                    continue
                step = (e_ms - s_ms) // max(1, len(split))
                for idx, w in enumerate(split):
                    w_clean = w.strip()
                    emoji = self._lookup_emoji(w_clean)
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
                    word_txt = w_obj.get("word", "").strip()
                    if not word_txt:
                        continue
                    w_s = int(w_obj.get("start", 0) * 1000) - base_offset_ms
                    w_e = int(w_obj.get("end", 0) * 1000) - base_offset_ms
                    emoji = self._lookup_emoji(word_txt)
                    all_words.append(
                        CaptionWord(
                            word=word_txt,
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
        style: SubtitleStyle = SubtitleStyle.HORMOZI,
        base_offset_ms: int = 0
    ) -> Path:
        """
        Generate a fully styled .ass file with karaoke word highlighting.
        """
        if output_path is None:
            output_path = config.CLIPS_DIR / f"{clip_id}.ass"

        blocks = self.parse_whisper_words(transcript_segments, base_offset_ms=base_offset_ms)
        style_header = self.STYLE_HEADERS.get(style, self.STYLE_HEADERS[SubtitleStyle.HORMOZI])

        lines = [style_header, "\n[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

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
        logger.info("Generated ASS karaoke captions (%s style) -> %s", style.value, output_path)
        return output_path

    def generate_json_timeline(
        self,
        transcript_segments: list,
        base_offset_ms: int = 0,
        style: SubtitleStyle = SubtitleStyle.HORMOZI
    ) -> Dict[str, Any]:
        """
        Export Remotion-compatible JSON timeline payload with millisecond word timestamps.
        """
        blocks = self.parse_whisper_words(transcript_segments, base_offset_ms=base_offset_ms)
        
        timeline_data = {
            "style": style.value,
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
