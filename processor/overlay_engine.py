"""
StreamClipper — Overlay Engine
Production-grade Pillow graphics engine for 1080x1920 short-form video layouts.
Renders viral streamer hooks, multi-line typography with full-color emojis,
and authentic platform watermark badges (Kick, Twitch, YouTube).
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont

import config

from processor.censor import censor_text

logger = logging.getLogger("streamclipper.processor.overlay_engine")

# Font Fallback Candidates
PRIMARY_HEADLINE_FONTS = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

EMOJI_FONTS = [
    "C:/Windows/Fonts/seguiemj.ttf",
]

PLATFORM_COLORS = {
    "kick": {
        "text": (83, 252, 24, 255),        # Neon Kick Green (#53FC18)
        "stroke": (0, 0, 0, 255),           # Black stroke
        "bg": (10, 12, 16, 235),            # Dark translucent pill
        "border": (83, 252, 24, 200),       # Kick Green border
        "prefix": "KICK.COM/",
        "prefix_color": (255, 255, 255, 230),
    },
    "twitch": {
        "text": (169, 112, 255, 255),      # Signature Twitch Violet (#A970FF)
        "stroke": (0, 0, 0, 255),
        "bg": (14, 10, 20, 235),            # Dark purple-tinted pill
        "border": (145, 70, 255, 200),      # Twitch Purple border (#9146FF)
        "prefix": "TWITCH.TV/",
        "prefix_color": (255, 255, 255, 230),
    },
    "youtube": {
        "text": (255, 59, 48, 255),        # YouTube Red (#FF3B30 / #FF0000)
        "stroke": (0, 0, 0, 255),
        "bg": (18, 10, 10, 235),            # Dark red-tinted pill
        "border": (255, 40, 40, 200),       # YouTube Red border
        "prefix": "YOUTUBE.COM/@",
        "prefix_color": (255, 255, 255, 230),
    },
    "tiktok": {
        "text": (0, 242, 254, 255),        # TikTok Electric Cyan (#00F2FE)
        "stroke": (0, 0, 0, 255),
        "bg": (10, 12, 18, 235),
        "border": (254, 44, 85, 200),       # TikTok Pink accent border (#FE2C55)
        "prefix": "TIKTOK.COM/@",
        "prefix_color": (255, 255, 255, 230),
    },
    "rumble": {
        "text": (133, 199, 66, 255),       # Rumble Lime (#85C742)
        "stroke": (0, 0, 0, 255),
        "bg": (12, 16, 10, 235),
        "border": (133, 199, 66, 200),
        "prefix": "RUMBLE.COM/",
        "prefix_color": (255, 255, 255, 230),
    },
    "twitter": {
        "text": (29, 155, 240, 255),       # X / Twitter Blue (#1D9BF0)
        "stroke": (0, 0, 0, 255),
        "bg": (10, 14, 20, 235),
        "border": (29, 155, 240, 200),
        "prefix": "X.COM/",
        "prefix_color": (255, 255, 255, 230),
    },
    "custom": {
        "text": (0, 240, 255, 255),        # Electric Cyan
        "stroke": (0, 0, 0, 255),
        "bg": (10, 12, 18, 235),
        "border": (0, 240, 255, 200),
        "prefix": "@",
        "prefix_color": (255, 255, 255, 230),
    },
}


def _is_emoji_codepoint(cp: int) -> bool:
    """Detect if a unicode codepoint represents an emoji."""
    return (
        0x1F300 <= cp <= 0x1FAFF or   # Miscellaneous Symbols, Pictographs, Supplemental Symbols
        0x2600 <= cp <= 0x27BF or     # Misc symbols & Dingbats
        0xFE00 <= cp <= 0xFE0F or     # Variation selectors
        cp == 0x200D or               # Zero-width joiner
        0x1F1E6 <= cp <= 0x1F1FF or   # Regional indicator symbols (flags)
        0x1F900 <= cp <= 0x1F9FF      # Supplemental Symbols and Pictographs
    )


def tokenize_text_with_emojis(text: str) -> List[Tuple[str, bool]]:
    """
    Split text into alternating chunks of (text_content, is_emoji).
    Guarantees that emojis can be rendered with a specialized color emoji font.
    """
    if not text:
        return []

    tokens: List[Tuple[str, bool]] = []
    curr = ""
    curr_is_emoji: Optional[bool] = None

    for ch in text:
        is_em = _is_emoji_codepoint(ord(ch))
        if curr_is_emoji is None:
            curr_is_emoji = is_em
            curr += ch
        elif curr_is_emoji == is_em:
            curr += ch
        else:
            tokens.append((curr, curr_is_emoji))
            curr = ch
            curr_is_emoji = is_em

    if curr:
        tokens.append((curr, curr_is_emoji))

    return tokens


class OverlayEngine:
    """
    Generates transparent 1080x1920 overlay PNGs for high-retention short-form video layouts.
    """

    def __init__(self):
        self.canvas_width = 1080
        self.canvas_height = 1920
        self.headline_font_path = self._find_first_font(PRIMARY_HEADLINE_FONTS)
        self.emoji_font_path = self._find_first_font(EMOJI_FONTS)

    @staticmethod
    def _find_first_font(candidates: List[str]) -> Optional[str]:
        for p in candidates:
            if Path(p).exists():
                return p
        return None

    def _get_fonts(self, font_size: int) -> Tuple[ImageFont.ImageFont, Optional[ImageFont.ImageFont]]:
        if self.headline_font_path:
            headline_font = ImageFont.truetype(self.headline_font_path, font_size)
        else:
            headline_font = ImageFont.load_default()

        emoji_font = None
        if self.emoji_font_path:
            # Emoji font looks best slightly smaller or matched to headline size
            emoji_font = ImageFont.truetype(self.emoji_font_path, int(font_size * 0.9))

        return headline_font, emoji_font

    def _measure_tokens(
        self,
        tokens: List[Tuple[str, bool]],
        draw: ImageDraw.ImageDraw,
        headline_font: ImageFont.ImageFont,
        emoji_font: Optional[ImageFont.ImageFont]
    ) -> float:
        total_w = 0.0
        for chunk, is_em in tokens:
            f = emoji_font if (is_em and emoji_font) else headline_font
            total_w += draw.textlength(chunk, font=f)
        return total_w

    def wrap_headline(
        self,
        text: str,
        draw: ImageDraw.ImageDraw,
        headline_font: ImageFont.ImageFont,
        emoji_font: Optional[ImageFont.ImageFont],
        max_width: int = 960
    ) -> List[str]:
        """
        Wrap headline text into lines that fit within max_width, keeping words and emojis intact.
        """
        words = text.split(" ")
        lines: List[str] = []
        current_line: List[str] = []

        for w in words:
            test_line = " ".join(current_line + [w])
            tokens = tokenize_text_with_emojis(test_line)
            w_px = self._measure_tokens(tokens, draw, headline_font, emoji_font)
            if w_px <= max_width or not current_line:
                current_line.append(w)
            else:
                lines.append(" ".join(current_line))
                current_line = [w]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def render_white_canvas_overlay(
        self,
        output_path: Path,
        hook_text: str,
        streamer_name: str,
        platform: str = "kick",
    ) -> Path:
        """
        Render the 16:9 white-canvas overlay:
        - Top White Zone (y: 0 to 656): Bold centered multi-line viral headline with color emojis (profanity-censored).
        - Video Lower Border (y ~ 1195 to 1255): Branded platform watermark pill with streamer name in platform signature color.
        """
        img = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Render Top Headline Hook (Sanitized with Censor Engine)
        if hook_text:
            safe_hook = censor_text(hook_text)
            font_size = 54
            headline_font, emoji_font = self._get_fonts(font_size)
            lines = self.wrap_headline(safe_hook, draw, headline_font, emoji_font, max_width=980)

            # Keep headline within 2-3 lines max; if 3+ lines, slightly reduce font size
            if len(lines) > 2:
                font_size = 46
                headline_font, emoji_font = self._get_fonts(font_size)
                lines = self.wrap_headline(safe_hook, draw, headline_font, emoji_font, max_width=980)

            line_height = int(font_size * 1.25)
            total_text_height = len(lines) * line_height
            # Top white zone is y=0 to 656. Center headline vertically around y=300
            start_y = max(80, int(300 - (total_text_height / 2)))

            for i, line_str in enumerate(lines):
                tokens = tokenize_text_with_emojis(line_str)
                line_w = self._measure_tokens(tokens, draw, headline_font, emoji_font)
                cur_x = (self.canvas_width - line_w) / 2
                cur_y = start_y + (i * line_height)

                for chunk, is_em in tokens:
                    if is_em and emoji_font:
                        draw.text(
                            (cur_x, cur_y + 4),
                            chunk,
                            font=emoji_font,
                            fill=(0, 0, 0, 255),
                            embedded_color=True
                        )
                        cur_x += draw.textlength(chunk, font=emoji_font)
                    else:
                        draw.text(
                            (cur_x, cur_y),
                            chunk,
                            font=headline_font,
                            fill=(15, 23, 42, 255)  # Pitch black / slate-900 high contrast
                        )
                        cur_x += draw.textlength(chunk, font=headline_font)

        # 2. Render Authentic Platform Watermark Badge with Streamer Name in Platform Color
        if streamer_name:
            clean_platform = platform.lower().strip() if platform else "kick"
            plat_cfg = PLATFORM_COLORS.get(clean_platform, PLATFORM_COLORS["kick"])
            clean_streamer = streamer_name.upper().strip()
            prefix_text = plat_cfg["prefix"]
            streamer_text = clean_streamer

            badge_font_size = 44
            badge_font, _ = self._get_fonts(badge_font_size)

            prefix_w = draw.textlength(prefix_text, font=badge_font)
            streamer_w = draw.textlength(streamer_text, font=badge_font)
            total_w = prefix_w + streamer_w
            badge_h = int(badge_font_size * 1.15)
            
            # Position at bottom edge of the 16:9 video frame
            # 16:9 video ends at y = 1264px. Badge sits right across the bottom border (y = 1195 - 1255)
            badge_x = 44
            badge_y = 1198

            # Render sleek translucent rounded pill backing with platform color outline
            pill_pad_x = 18
            pill_pad_y = 10
            pill_box = [
                badge_x - pill_pad_x,
                badge_y - pill_pad_y,
                badge_x + total_w + pill_pad_x,
                badge_y + badge_h + pill_pad_y,
            ]
            draw.rounded_rectangle(
                pill_box,
                radius=14,
                fill=plat_cfg["bg"],
                outline=plat_cfg["border"],
                width=2
            )

            # Draw prefix in crisp white
            draw.text((badge_x, badge_y), prefix_text, font=badge_font, fill=plat_cfg["prefix_color"])

            # Draw streamer name in the signature platform brand color (Kick Neon Green, Twitch Purple, etc.)
            draw.text((badge_x + prefix_w, badge_y), streamer_text, font=badge_font, fill=plat_cfg["text"])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        logger.info("🎨 Rendered 16:9 white-canvas overlay -> %s", output_path)
        return output_path

    def render_full_bleed_hook_banner(
        self,
        output_path: Path,
        hook_text: str,
        streamer_name: str = "",
        platform: str = "twitch",
    ) -> Path:
        """
        Render sleek top-safe zone hook banner for 9:16 full-bleed clips (0-3s attention grabber).
        Includes profanity censoring and platform-colored streamer branding.
        """
        img = Image.new("RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if not hook_text and not streamer_name:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, "PNG")
            return output_path

        safe_hook = censor_text(hook_text) if hook_text else ""
        font_size = 44
        headline_font, emoji_font = self._get_fonts(font_size)

        lines = []
        if safe_hook:
            tokens = tokenize_text_with_emojis(safe_hook)
            total_w = self._measure_tokens(tokens, draw, headline_font, emoji_font)
            lines = [safe_hook]
            if total_w > 900:
                lines = self.wrap_headline(safe_hook, draw, headline_font, emoji_font, max_width=880)

        # Measure streamer badge if present
        clean_platform = platform.lower().strip() if platform else "twitch"
        plat_cfg = PLATFORM_COLORS.get(clean_platform, PLATFORM_COLORS["twitch"])
        badge_font, _ = self._get_fonts(36)
        prefix_text = plat_cfg["prefix"]
        streamer_text = streamer_name.upper().strip() if streamer_name else ""
        has_badge = bool(streamer_text)

        line_h = int(font_size * 1.3)
        hook_content_h = (len(lines) * line_h) if lines else 0
        badge_h = 44 if has_badge else 0
        gap = 16 if (lines and has_badge) else 0

        box_h = hook_content_h + badge_h + gap + 40
        max_line_w = max((self._measure_tokens(tokenize_text_with_emojis(ln), draw, headline_font, emoji_font) for ln in lines), default=0)
        badge_w = (draw.textlength(prefix_text, font=badge_font) + draw.textlength(streamer_text, font=badge_font) + 36) if has_badge else 0
        box_w = min(1020, max(max_line_w, badge_w) + 60)

        box_x0 = (self.canvas_width - box_w) / 2
        box_y0 = 200
        box_x1 = box_x0 + box_w
        box_y1 = box_y0 + box_h

        # Draw rounded translucent background pill with glowing border in platform color accent
        draw.rounded_rectangle(
            [box_x0, box_y0, box_x1, box_y1],
            radius=20,
            fill=(12, 14, 20, 235),       # Dark Slate pill
            outline=plat_cfg["border"],     # Platform signature glowing border
            width=3
        )

        start_y = box_y0 + 20

        # Draw Streamer badge in platform colors
        if has_badge:
            cur_badge_x = (self.canvas_width - (draw.textlength(prefix_text, font=badge_font) + draw.textlength(streamer_text, font=badge_font))) / 2
            draw.text((cur_badge_x, start_y), prefix_text, font=badge_font, fill=plat_cfg["prefix_color"])
            cur_badge_x += draw.textlength(prefix_text, font=badge_font)
            draw.text((cur_badge_x, start_y), streamer_text, font=badge_font, fill=plat_cfg["text"])
            start_y += badge_h + gap

        # Draw Hook Headline
        for i, line_str in enumerate(lines):
            line_tokens = tokenize_text_with_emojis(line_str)
            w_px = self._measure_tokens(line_tokens, draw, headline_font, emoji_font)
            cur_x = (self.canvas_width - w_px) / 2
            cur_y = start_y + (i * line_h)

            for chunk, is_em in line_tokens:
                if is_em and emoji_font:
                    draw.text(
                        (cur_x, cur_y + 3),
                        chunk,
                        font=emoji_font,
                        fill=(0, 0, 0, 255),
                        embedded_color=True
                    )
                    cur_x += draw.textlength(chunk, font=emoji_font)
                else:
                    draw.text(
                        (cur_x, cur_y),
                        chunk,
                        font=headline_font,
                        fill=(255, 255, 255, 255)
                    )
                    cur_x += draw.textlength(chunk, font=headline_font)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        logger.info("🎨 Rendered 9:16 full-bleed hook banner -> %s", output_path)
        return output_path
