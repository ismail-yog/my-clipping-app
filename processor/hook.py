"""
StreamClipper — Hook Overlay Renderer
Burns a bold, attention-grabbing text overlay into the first 3 seconds
of a clip using ffmpeg drawtext. Also applies subtle corner watermarks
and a clean fade-out ending card at the end of the video.
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("streamclipper.hook")


class HookOverlayRenderer:
    """
    Applies viral-style screen components to a clip:
    1. Attention hook text at the start (first 3s)
    2. Sub-brand watermark in the corner (entire clip)
    3. Smooth fade-out outro transition (last 1.5s)
    """

    def __init__(self):
        self.hook_duration: float = 3.0  # seconds
        self.font_size: int = 72
        self.font_color: str = "white"
        self.border_color: str = "black"
        self.border_width: int = 4
        self.font: str = "Arial"
        self.y_position: str = "h*0.15"  # 15% from top
        self.fade_in: float = 0.3  # seconds
        self.fade_out: float = 0.5  # seconds

    def apply(
        self,
        clip_path: Path,
        hook_text: str,
        watermark_text: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """
        Apply hook overlay, watermark, and outro cards to a clip.
        """
        if not clip_path.exists():
            logger.error("Clip not found: %s", clip_path)
            return None

        # Clean and escape text
        clean_hook = self._escape_text(hook_text.strip().upper()) if hook_text else ""
        clean_watermark = self._escape_text(watermark_text.strip()) if watermark_text else ""

        # Get video duration for outro transition timing
        duration = self._get_video_duration(clip_path)

        # Determine output path
        replacing_original = output_path is None
        if replacing_original:
            output_path = clip_path.with_suffix(".hook.mp4")

        try:
            cmd = self._build_cmd(clip_path, output_path, clean_hook, clean_watermark, duration)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error("Hook overlay failed: %s", result.stderr[-300:])
                return None

            if not output_path.exists():
                logger.error("Hook output not created")
                return None

            # If replacing original, swap the files
            if replacing_original:
                clip_path.unlink()
                shutil.move(str(output_path), str(clip_path))
                logger.info("✨ Hook, watermark & outro applied successfully to %s", clip_path.name)
                return clip_path

            logger.info("✨ Hook, watermark & outro saved to %s", output_path.name)
            return output_path

        except subprocess.TimeoutExpired:
            logger.error("Hook overlay timed out")
            return None
        except Exception as e:
            logger.error("Hook overlay error: %s", e)
            return None

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
        except Exception as e:
            logger.warning("Failed to query clip duration: %s. Using default 30s.", e)
            return 30.0

    def _build_cmd(
        self,
        source: Path,
        output: Path,
        hook_text: str,
        watermark_text: str,
        duration: float,
    ) -> list[str]:
        """Build ffmpeg command for hook, watermark, and outro card overlays."""
        stay_end = self.hook_duration - self.fade_out

        video_filters = []

        # 1. Dark top gradient box (for hook readability)
        gradient_filter = (
            f"drawbox="
            f"x=0:y=0:w=iw:h=ih*0.35:"
            f"color=black@0.3:"
            f"t=fill:"
            f"enable='between(t,0,{self.hook_duration})'"
        )
        video_filters.append(gradient_filter)

        # 2. Hook text overlay
        if hook_text:
            drawtext_filter = (
                f"drawtext="
                f"text='{hook_text}':"
                f"fontfile='':"
                f"fontsize={self.font_size}:"
                f"fontcolor={self.font_color}:"
                f"borderw={self.border_width}:"
                f"bordercolor={self.border_color}:"
                f"x=(w-text_w)/2:"
                f"y={self.y_position}:"
                f"shadowcolor=black@0.6:shadowx=3:shadowy=3:"
                f"enable='between(t,0,{self.hook_duration})':"
                f"alpha='if(lt(t,{self.fade_in}),t/{self.fade_in},"
                f"if(lt(t,{stay_end}),1,"
                f"({self.hook_duration}-t)/{self.fade_out}))'"
            )
            video_filters.append(drawtext_filter)

        # 3. Subtle corner watermark (visible throughout entire video)
        if watermark_text:
            watermark_filter = (
                f"drawtext="
                f"text='{watermark_text}':"
                f"fontfile='':"
                f"fontsize=36:"
                f"fontcolor=white@0.35:"
                f"borderw=2:"
                f"bordercolor=black@0.3:"
                f"x=w-text_w-20:"
                f"y=20"
            )
            video_filters.append(watermark_filter)

        # 4. Outro transition: Fade video to black in last 1.5 seconds
        outro_fade_start = max(0.0, duration - 1.5)
        fade_filter = f"fade=t=out:st={outro_fade_start}:d=1.5"
        video_filters.append(fade_filter)

        # 5. Outro visual Call-To-Action (SUBSCRIBE FOR MORE)
        outro_text_filter = (
            f"drawtext="
            f"text='SUBSCRIBE FOR MORE':"
            f"fontfile='':"
            f"fontsize=64:"
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2:"
            f"enable='gt(t,{outro_fade_start})'"
        )
        video_filters.append(outro_text_filter)

        # Combine video filters
        vf_arg = ",".join(video_filters)

        # 6. Audio outro transition: Fade audio out in last 1.5 seconds
        af_arg = f"afade=t=out:st={outro_fade_start}:d=1.5"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-vf", vf_arg,
            "-af", af_arg,
            "-c:v", "libx264",
            "-crf", "20",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output),
        ]

        return cmd

    @staticmethod
    def _escape_text(text: str) -> str:
        """Escape special characters for ffmpeg drawtext."""
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "'\\\\\\''")
        text = text.replace(":", "\\:")
        text = text.replace("%", "%%")
        return text
