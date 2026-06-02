"""
StreamClipper — Thumbnail Generator
Extracts the best frame from a clip and overlays bold text
to create eye-catching YouTube Shorts thumbnails.
Uses ffmpeg for frame extraction and PIL/Pillow for text compositing.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("streamclipper.thumbnail")

# Directory for thumbnail output
THUMBS_DIR = config.BASE_DIR / "thumbs"
THUMBS_DIR.mkdir(exist_ok=True)


class ThumbnailGenerator:
    """
    Generates YouTube-optimized thumbnails for clips.

    1. Extracts the best frame (at peak moment) via ffmpeg
    2. Overlays bold text using PIL/Pillow
    3. Outputs a 1280x720 JPEG thumbnail
    """

    def __init__(self):
        self.width: int = 1280
        self.height: int = 720
        self.quality: int = 90  # JPEG quality

    def generate(
        self,
        clip_path: Path,
        title_text: str,
        streamer_name: str = "",
        timestamp: float = 1.5,  # seconds into clip for best frame
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Generate a thumbnail for a clip.

        Args:
            clip_path: Path to the clip video
            title_text: Bold text to overlay (e.g. "INSANE PLAY")
            streamer_name: Streamer name for branding
            timestamp: Time in seconds to extract the frame from
            output_path: Custom output path. Defaults to thumbs/<clip_stem>.jpg

        Returns:
            Path to the generated thumbnail, or None on failure.
        """
        if not clip_path.exists():
            logger.error("Clip not found: %s", clip_path)
            return None

        if not output_path:
            output_path = THUMBS_DIR / f"{clip_path.stem}_thumb.jpg"

        try:
            # Step 1: Extract frame via ffmpeg
            frame_path = self._extract_frame(clip_path, timestamp)
            if not frame_path:
                return None

            # Step 2: Overlay text using PIL
            result = self._compose_thumbnail(
                frame_path, output_path, title_text, streamer_name
            )

            # Cleanup temp frame
            try:
                frame_path.unlink(missing_ok=True)
            except Exception:
                pass

            if result:
                logger.info("🖼️ Thumbnail generated: %s", output_path.name)

            return result

        except Exception as e:
            logger.error("Thumbnail generation failed: %s", e)
            return None

    def _extract_frame(
        self, clip_path: Path, timestamp: float
    ) -> Optional[Path]:
        """Extract a single frame from the clip at the given timestamp."""
        frame_path = Path(tempfile.mktemp(suffix=".png"))

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(max(0, timestamp)),
            "-i", str(clip_path),
            "-vframes", "1",
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                   f"crop={self.width}:{self.height}",
            str(frame_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                logger.error("Frame extraction failed: %s", result.stderr[-200:])
                return None

            if frame_path.exists():
                return frame_path

            return None

        except subprocess.TimeoutExpired:
            logger.error("Frame extraction timed out")
            return None

    def _compose_thumbnail(
        self,
        frame_path: Path,
        output_path: Path,
        title_text: str,
        streamer_name: str,
    ) -> Optional[Path]:
        """Compose the final thumbnail with text overlays using PIL."""
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
        except ImportError:
            logger.warning("Pillow not installed — using ffmpeg-only thumbnail")
            return self._compose_ffmpeg_fallback(
                frame_path, output_path, title_text, streamer_name
            )

        try:
            # Open the extracted frame
            img = Image.open(frame_path).convert("RGB")
            img = img.resize((self.width, self.height), Image.LANCZOS)

            # Boost contrast slightly for more visual pop
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.15)

            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.1)

            draw = ImageDraw.Draw(img)

            # Load fonts (try system fonts, fall back to default)
            title_font = self._get_font(size=72, bold=True)
            name_font = self._get_font(size=36, bold=True)

            # Add semi-transparent dark gradient at bottom
            gradient = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            gradient_draw = ImageDraw.Draw(gradient)
            for y in range(self.height // 2, self.height):
                alpha = int(180 * (y - self.height // 2) / (self.height // 2))
                gradient_draw.line(
                    [(0, y), (self.width, y)],
                    fill=(0, 0, 0, min(alpha, 180)),
                )
            img = Image.alpha_composite(img.convert("RGBA"), gradient).convert("RGB")
            draw = ImageDraw.Draw(img)

            # Draw title text (centered, near bottom)
            title_upper = title_text.upper()[:30]
            bbox = draw.textbbox((0, 0), title_upper, font=title_font)
            text_w = bbox[2] - bbox[0]
            text_x = (self.width - text_w) // 2
            text_y = self.height - 160

            # Text shadow
            for offset in [(2, 2), (-2, -2), (2, -2), (-2, 2)]:
                draw.text(
                    (text_x + offset[0], text_y + offset[1]),
                    title_upper,
                    font=title_font,
                    fill=(0, 0, 0),
                )

            # Main text (white with slight yellow tint)
            draw.text(
                (text_x, text_y),
                title_upper,
                font=title_font,
                fill=(255, 255, 240),
            )

            # Draw streamer name if provided
            if streamer_name:
                name_text = f"@{streamer_name}"
                bbox = draw.textbbox((0, 0), name_text, font=name_font)
                name_w = bbox[2] - bbox[0]
                name_x = (self.width - name_w) // 2
                name_y = self.height - 80

                draw.text(
                    (name_x + 1, name_y + 1),
                    name_text,
                    font=name_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    (name_x, name_y),
                    name_text,
                    font=name_font,
                    fill=(200, 200, 255),
                )

            # Save
            img.save(str(output_path), "JPEG", quality=self.quality)
            return output_path

        except Exception as e:
            logger.error("PIL thumbnail composition failed: %s", e)
            return self._compose_ffmpeg_fallback(
                frame_path, output_path, title_text, streamer_name
            )

    def _compose_ffmpeg_fallback(
        self,
        frame_path: Path,
        output_path: Path,
        title_text: str,
        streamer_name: str,
    ) -> Optional[Path]:
        """Fallback: use ffmpeg drawtext for thumbnail composition."""
        title_clean = title_text.upper()[:30]
        title_clean = title_clean.replace("'", "").replace(":", "")

        filters = [
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height}",
            f"eq=contrast=1.15:saturation=1.1",
            f"drawtext=text='{title_clean}':"
            f"fontsize=72:fontcolor=white:"
            f"borderw=4:bordercolor=black:"
            f"x=(w-text_w)/2:y=h-160:"
            f"shadowcolor=black@0.6:shadowx=3:shadowy=3",
        ]

        if streamer_name:
            name_clean = f"@{streamer_name}"
            filters.append(
                f"drawtext=text='{name_clean}':"
                f"fontsize=36:fontcolor=#C8C8FF:"
                f"borderw=2:bordercolor=black:"
                f"x=(w-text_w)/2:y=h-80"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(frame_path),
            "-vf", ",".join(filters),
            "-q:v", "2",
            str(output_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and output_path.exists():
                return output_path
            return None
        except Exception:
            return None

    @staticmethod
    def _get_font(size: int = 48, bold: bool = False):
        """Try to load a system font, fall back to PIL default."""
        from PIL import ImageFont

        # Try common font paths
        font_names = [
            "Impact",       # Best for thumbnails
            "Arial Black",
            "Helvetica Bold",
            "DejaVuSans-Bold",
            "Arial",
        ] if bold else [
            "Arial",
            "Helvetica",
            "DejaVuSans",
        ]

        for name in font_names:
            try:
                return ImageFont.truetype(name, size)
            except (OSError, IOError):
                continue

        # Try common system paths
        import sys
        font_paths = []
        if sys.platform == "win32":
            font_paths = [
                "C:/Windows/Fonts/impact.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/arial.ttf",
            ]
        elif sys.platform == "darwin":
            font_paths = [
                "/System/Library/Fonts/Supplemental/Impact.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ]

        for path in font_paths:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue

        # Final fallback
        logger.debug("Using PIL default font (no system fonts found)")
        return ImageFont.load_default()
