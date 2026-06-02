"""
StreamClipper — Thumbnail Generator
Extracts a frame from the clip, overlays bold text, adds visual effects (zoom, contrast),
and saves it as a 1280x720 JPG.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

import config

logger = logging.getLogger("streamclipper.processor.thumbnail")


class ThumbnailGenerator:
    """
    Generates YouTube-optimized thumbnails from video clip frames.
    """

    def __init__(self):
        # Read settings from config.thumbnail_settings
        self.width = getattr(config.thumbnail_settings, "width", 1280)
        self.height = getattr(config.thumbnail_settings, "height", 720)
        self.quality = getattr(config.thumbnail_settings, "quality", 90)
        self.frame_timestamp = getattr(config.thumbnail_settings, "frame_timestamp", 1.5)

    def generate(self, clip_path: Path, title_text: str, streamer_name: str) -> Optional[Path]:
        """
        Extract frame from clip, add text overlays, apply enhancements, and save to output path.
        """
        if not clip_path.exists():
            logger.error("Source clip path not found: %s", clip_path)
            return None

        # Output path: config.THUMBS_DIR / f"{clip_path.stem}.jpg"
        output_path = config.THUMBS_DIR / f"{clip_path.stem}.jpg"
        temp_png = config.THUMBS_DIR / f"{clip_path.stem}_temp_frame.png"

        try:
            # 1. Extract frame at frame_timestamp
            success = self._extract_frame(clip_path, temp_png)
            if not success or not temp_png.exists():
                logger.error("Failed to extract frame for thumbnail")
                return None

            # 2. Add text overlay and enhance image
            result_path = self._add_text_overlay(temp_png, title_text, streamer_name, output_path)
            return result_path

        except Exception as e:
            logger.error("Exception during thumbnail generation: %s", e, exc_info=True)
            return None
        finally:
            # Cleanup temp png frame
            if temp_png.exists():
                try:
                    temp_png.unlink()
                except Exception:
                    pass

    def _extract_frame(self, video_path: Path, output_path: Path) -> bool:
        """Extract a single frame from the video at the configured timestamp using FFmpeg."""
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(self.frame_timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(output_path)
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return r.returncode == 0
        except Exception as e:
            logger.error("FFmpeg frame extraction failed: %s", e)
            return False

    def _add_text_overlay(self, image_path: Path, text: str, streamer_name: str, output_path: Path) -> Optional[Path]:
        """Open the frame image, resize, apply dark gradient, write stroke/shadow text, enhance colors, and save."""
        try:
            img = Image.open(image_path).convert("RGB")
            
            # Resize to target resolution (1280x720) if needed
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

            # Create gradient overlay for text readability
            gradient = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            g_draw = ImageDraw.Draw(gradient)
            
            # Subtle top gradient
            for y in range(200):
                alpha = int(120 * (1.0 - (y / 200.0)))
                g_draw.line([(0, y), (self.width, y)], fill=(0, 0, 0, alpha))
                
            # Subtle bottom gradient
            for y in range(self.height - 200, self.height):
                alpha = int(120 * ((y - (self.height - 200)) / 200.0))
                g_draw.line([(0, y), (self.width, y)], fill=(0, 0, 0, alpha))

            # Composite the gradient box
            img = Image.alpha_composite(img.convert("RGBA"), gradient).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Load Arial bold or fallback
            title_font = self._get_font(size=60, bold=True)
            name_font = self._get_font(size=32, bold=True)

            # 1. Draw Title Text (centered at top, 60pt bold, white, 4px black stroke, shadow)
            title_str = text.strip().upper()
            bbox = draw.textbbox((0, 0), title_str, font=title_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            title_x = (self.width - text_w) // 2
            title_y = 60

            # Draw shadow first
            draw.text(
                (title_x + 3, title_y + 3),
                title_str,
                font=title_font,
                fill="black",
                stroke_width=4,
                stroke_fill="black"
            )
            # Draw main text
            draw.text(
                (title_x, title_y),
                title_str,
                font=title_font,
                fill="white",
                stroke_width=4,
                stroke_fill="black"
            )

            # 2. Draw Streamer Name (bottom-right, 32pt, white, 2px black stroke)
            if streamer_name:
                name_str = f"@{streamer_name.strip()}"
                n_bbox = draw.textbbox((0, 0), name_str, font=name_font)
                n_w = n_bbox[2] - n_bbox[0]
                n_h = n_bbox[3] - n_bbox[1]
                name_x = self.width - n_w - 40
                name_y = self.height - n_h - 40

                draw.text(
                    (name_x, name_y),
                    name_str,
                    font=name_font,
                    fill="white",
                    stroke_width=2,
                    stroke_fill="black"
                )

            # 3. Enhance Image (+20% saturation, +15% contrast, +30% sharpness)
            img = ImageEnhance.Color(img).enhance(1.2)
            img = ImageEnhance.Contrast(img).enhance(1.15)
            img = ImageEnhance.Sharpness(img).enhance(1.3)

            # Save JPEG
            img.save(output_path, "JPEG", quality=self.quality)
            logger.info("🖼️ Thumbnail generated: %s", output_path.name)
            return output_path

        except Exception as e:
            logger.error("PIL composition or enhancement failed: %s", e)
            return None

    def _get_font(self, size: int, bold: bool = False) -> ImageFont:
        """Try loading Arial/Impact bold from system paths, fallback to default font."""
        font_names = ["arialbd.ttf", "arial.ttf", "Arial-Bold", "Arial"] if bold else ["arial.ttf", "Arial"]
        for name in font_names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue

        # System paths for Windows
        import sys
        if sys.platform == "win32":
            paths = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"] if bold else ["C:/Windows/Fonts/arial.ttf"]
            for path in paths:
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue

        return ImageFont.load_default()
