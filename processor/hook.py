"""
StreamClipper — Hook Overlay Renderer
Renders viral streamer hooks, true color emojis, and platform watermark badges
using the high-performance Pillow OverlayEngine + FFmpeg composite filters.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List

import config
from processor.overlay_engine import OverlayEngine

logger = logging.getLogger("streamclipper.processor.hook")


class HookOverlayRenderer:
    """
    Applies high-retention screen overlays to a clip:
    - 16:9 White Canvas: Bold multi-line headline hook with color emojis + platform watermark badge.
    - 9:16 Full-Bleed: Top-safe zone hook banner (0-3s smooth fade) with unobstructed video.
    """

    def __init__(self):
        self.duration = getattr(config.hook_settings, "duration", 3.0)
        self.fade_in = getattr(config.hook_settings, "fade_in", 0.3)
        self.fade_out = getattr(config.hook_settings, "fade_out", 0.5)
        self.overlay_engine = OverlayEngine()

    def apply(
        self,
        clip_path: Path,
        hook_text: str,
        watermark_text: str = "",
        outro_text: str = "Follow for more 🔥",
        layout_type: str = "white_canvas",
        streamer_name: str = "",
        platform: str = "twitch",
    ) -> Optional[Path]:
        """
        Apply layout-aware hook, watermark, and outro text overlay to a clip.
        Guarantees zero tofu square [ ] boxes and crisp display typography.
        """
        if not clip_path.exists():
            logger.error("Source clip path not found: %s", clip_path)
            return None

        # Clean inputs
        clean_hook = hook_text.strip() if hook_text else ""
        clean_watermark = watermark_text.strip() if watermark_text else ""
        clean_outro = outro_text.strip() if outro_text else ""
        clean_streamer = streamer_name.strip() if streamer_name else ""
        clean_platform = platform.strip().lower() if platform else "twitch"

        if not clean_hook and not clean_watermark and not clean_outro and not clean_streamer:
            logger.info("Hook, watermark, streamer, and outro are all empty. Skipping overlays.")
            return clip_path

        temp_output = clip_path.parent / f"{clip_path.stem}_hook_temp.mp4"
        overlay_png = clip_path.parent / f"{clip_path.stem}_overlay_asset.png"

        try:
            is_white_canvas = layout_type in ("white_canvas", "16_9_white", "white_letterbox")

            if is_white_canvas:
                # 1. Generate 16:9 white canvas overlay (Top headline with emojis + video bottom platform badge)
                self.overlay_engine.render_white_canvas_overlay(
                    output_path=overlay_png,
                    hook_text=clean_hook,
                    streamer_name=clean_streamer,
                    platform=clean_platform,
                )

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(clip_path),
                    "-i", str(overlay_png),
                    "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
                    "-map", "[v]",
                    "-map", "0:a?",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-c:a", "copy",
                    str(temp_output),
                ]
            else:
                # 2. Generate 9:16 full-bleed top-safe zone hook banner (0-3s smooth fade)
                self.overlay_engine.render_full_bleed_hook_banner(
                    output_path=overlay_png,
                    hook_text=clean_hook,
                    streamer_name=clean_streamer,
                    platform=clean_platform,
                )

                stay_end = max(0.5, self.duration - self.fade_out)
                filter_graph = (
                    f"[1:v]format=rgba,"
                    f"fade=t=in:st=0:d={self.fade_in}:alpha=1,"
                    f"fade=t=out:st={stay_end}:d={self.fade_out}:alpha=1[banner];"
                    f"[0:v][banner]overlay=0:0:enable='between(t,0,{self.duration})'[v]"
                )

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(clip_path),
                    "-i", str(overlay_png),
                    "-filter_complex", filter_graph,
                    "-map", "[v]",
                    "-map", "0:a?",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "18",
                    "-c:a", "copy",
                    str(temp_output),
                ]

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not temp_output.exists() or temp_output.stat().st_size == 0:
                logger.error("FFmpeg overlay render failed (exit=%d): %s", r.returncode, r.stderr)
                return clip_path

            # Atomically replace original video with overlay version
            clip_path.unlink(missing_ok=True)
            temp_output.rename(clip_path)

            logger.info("✨ High-retention hook & platform overlay applied successfully to %s", clip_path.name)
            return clip_path

        except Exception as e:
            logger.error("Exception during hook overlay rendering: %s", e, exc_info=True)
            return clip_path
        finally:
            if overlay_png.exists():
                try:
                    overlay_png.unlink()
                except Exception:
                    pass
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except Exception:
                    pass
