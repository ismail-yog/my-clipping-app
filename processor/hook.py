"""
StreamClipper — Hook Overlay Renderer
Adds MrBeast-style hook overlay (3-second attention grabber) + watermark + outro.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("streamclipper.processor.hook")


class HookOverlayRenderer:
    """
    Applies screen overlays to a clip: animated hook, watermark, and outro text.
    """

    def __init__(self):
        # Read from config.hook_settings or default
        self.duration = getattr(config.hook_settings, "duration", 3.0)
        self.font_size = getattr(config.hook_settings, "font_size", 72)
        self.font_color = getattr(config.hook_settings, "font_color", "white")
        self.border_width = getattr(config.hook_settings, "border_width", 4)
        self.fade_in = getattr(config.hook_settings, "fade_in", 0.3)
        self.fade_out = getattr(config.hook_settings, "fade_out", 0.5)

    def apply(
        self,
        clip_path: Path,
        hook_text: str,
        watermark_text: str = "",
        outro_text: str = "Follow for more 🔥"
    ) -> Optional[Path]:
        """
        Apply hook, watermark, and outro text overlay to a clip.
        If everything is empty, returns the original path.
        """
        if not clip_path.exists():
            logger.error("Source clip path not found: %s", clip_path)
            return None

        # Clean inputs
        clean_hook = hook_text.strip() if hook_text else ""
        clean_watermark = watermark_text.strip() if watermark_text else ""
        clean_outro = outro_text.strip() if outro_text else ""

        # If everything is empty, skip and return original path
        if not clean_hook and not clean_watermark and not clean_outro:
            logger.info("Hook, watermark, and outro are all empty. Skipping overlays.")
            return clip_path

        temp_output = clip_path.parent / f"{clip_path.stem}_hook_temp.mp4"

        try:
            cmd = self._build_ffmpeg_command(
                input_path=clip_path,
                output_path=temp_output,
                hook_text=clean_hook,
                watermark_text=clean_watermark,
                outro_text=clean_outro
            )

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not temp_output.exists():
                logger.error("FFmpeg hook render failed: %s", r.stderr)
                # Return original path if overlay fails (don't break pipeline)
                return clip_path

            # Replace original video with overlay version
            try:
                clip_path.unlink()
                temp_output.rename(clip_path)
            except Exception as e:
                logger.error("Failed to overwrite original file with hook overlay: %s", e)
                return clip_path

            logger.info("✨ Hook overlay, watermark & outro applied successfully to %s", clip_path.name)
            return clip_path

        except Exception as e:
            logger.error("Exception during hook overlay rendering: %s", e, exc_info=True)
            return clip_path
        finally:
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except Exception:
                    pass

    def _build_ffmpeg_command(
        self,
        input_path: Path,
        output_path: Path,
        hook_text: str,
        watermark_text: str,
        outro_text: str
    ) -> list[str]:
        """Build the FFmpeg drawtext command for applying the overlays."""
        duration = self._get_video_duration(input_path)
        filters = []

        # 1. Add drawtext filter for hook (first 3s, animated)
        if hook_text:
            escaped_hook = self._escape_text(hook_text.upper())
            stay_end = self.duration - self.fade_out
            hook_filter = (
                f"drawtext=text='{escaped_hook}':"
                f"fontsize={self.font_size}:"
                f"fontcolor={self.font_color}:"
                f"borderw={self.border_width}:"
                f"bordercolor=black:"
                f"x=(w-text_w)/2:"
                f"y=(h-text_h)/2:"
                f"enable='between(t,0,{self.duration})':"
                f"alpha='if(lt(t,{self.fade_in}),t/{self.fade_in},"
                f"if(gt(t,{stay_end}),({self.duration}-t)/{self.fade_out},1))'"
            )
            filters.append(hook_filter)

        # 2. Add drawtext for watermark (always visible, top-right corner, small)
        if watermark_text:
            escaped_watermark = self._escape_text(watermark_text)
            watermark_filter = (
                f"drawtext=text='{escaped_watermark}':"
                f"fontsize=24:"
                f"fontcolor=white@0.7:"
                f"borderw=2:"
                f"bordercolor=black:"
                f"x=w-text_w-20:"
                f"y=20"
            )
            filters.append(watermark_filter)

        # 3. Add drawtext for outro (last 2s, bottom center)
        if outro_text:
            escaped_outro = self._escape_text(outro_text)
            outro_filter = (
                f"drawtext=text='{escaped_outro}':"
                f"fontsize=48:"
                f"fontcolor=white:"
                f"borderw=3:"
                f"bordercolor=black:"
                f"x=(w-text_w)/2:"
                f"y=h-100:"
                f"enable='between(t,{duration}-2,{duration})'"
            )
            filters.append(outro_filter)

        vf_filter = ",".join(filters)

        return [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-crf", "23",
            "-c:a", "copy",
            str(output_path)
        ]

    def _get_video_duration(self, video_path: Path) -> float:
        """Get the duration of a video file using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 30.0  # Fallback duration if query fails

    @staticmethod
    def _escape_text(text: str) -> str:
        r"""Escape special characters for ffmpeg drawtext: ' : , \ %"""
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "\\'")
        text = text.replace(":", "\\:")
        text = text.replace(",", "\\,")
        text = text.replace("%", "\\%")
        return text
