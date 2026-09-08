"""
StreamClipper — Clipper
Extracts highlight clips, crops to 9:16 portrait, and burns viral-style captions.
Enforces integer millisecond timestamp calculations and CFR transcoding to avoid A/V desynchronization.
"""

import os
import time
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union

import config
from processor.subprocess_utils import (
    run_command_safely,
    safe_unlink,
    ms_to_ass_timestamp,
    ms_to_timestamp,
    seconds_to_ms,
    SubprocessExecutionError,
    MediaProcessingError,
)
from processor.captions_engine import CaptionsEngine, SubtitleStyle, normalize_subtitle_style

logger = logging.getLogger("streamclipper.processor.clipper")


@dataclass
class ClipMetadata:
    """Metadata for a processed clip."""
    clip_id: str
    clip_path: str
    duration: float
    moment_score: float
    transcript: str
    has_captions: bool
    emotion: str
    title: str = ""
    description: str = ""
    tags: list = field(default_factory=list)
    seo_ready: bool = False
    archetype: str = ""
    editorial_reasoning: str = ""

    # Fields for pipeline tracking
    source_streamer: str = "vod"
    source_platform: str = "custom"
    timestamp: float = field(default_factory=time.time)
    width: int = 1080
    height: int = 1920
    uploaded: bool = False
    upload_url: str = ""


class Clipper:
    """
    Cuts clips from stream buffer, reframes to 9:16 vertical, and burns animated captions.
    """

    def __init__(self, settings: Optional[config.ClipSettings] = None):
        self.settings = settings or config.clip_settings
        self.captions_engine = CaptionsEngine()
        self._clips: List[ClipMetadata] = []

    def create_clip(
        self,
        source_video: Path,
        streamer: Optional[config.StreamerConfig],
        start_offset: Union[int, float],
        duration: Union[int, float],
        moment_score: float,
        transcript_segments: Optional[list] = None,
        emotion: str = "",
        custom_clip_id: Optional[str] = None,
        layout_type: str = "gamer",
        subtitle_style: Union[SubtitleStyle, str] = SubtitleStyle.GLACIER_GLOW,
    ) -> Optional[ClipMetadata]:
        """
        Create a processed clip from source video.
        Uses exact millisecond offsets and CFR conversion.
        Strictly rejects and dumps any clip with moment_score < 0.65.
        """
        if moment_score < 0.65:
            logger.info(
                "🗑️ Dropping clip immediately: moment_score=%.2f < 0.65 (65%%) viral threshold",
                moment_score,
            )
            return None

        streamer_name = streamer.name if streamer else "vod"
        clip_id = custom_clip_id or f"{streamer_name}_{int(time.time())}"
        output_path = config.CLIPS_DIR / f"{clip_id}.mp4"

        start_offset_ms = seconds_to_ms(start_offset)
        duration_ms = seconds_to_ms(duration)

        logger.info(
            "Creating clip: %s (score=%.2f, duration_ms=%d, start_offset_ms=%d)",
            clip_id, moment_score, duration_ms, start_offset_ms,
        )

        temp_cut = config.CLIPS_DIR / f"{clip_id}_temp_cut.mp4"

        try:
            # Step 1: Cut segment with ffmpeg (re-encode with CFR 60fps for accurate keyframe alignment)
            start_ts = ms_to_timestamp(start_offset_ms)
            duration_ts = ms_to_timestamp(duration_ms)

            cut_cmd = [
                "ffmpeg", "-y",
                "-ss", start_ts,
                "-i", str(source_video),
                "-t", duration_ts,
                "-vf", "fps=fps=60",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                str(temp_cut),
            ]
            run_command_safely(cut_cmd, timeout=90.0)

            if not temp_cut.exists() or temp_cut.stat().st_size == 0:
                logger.error("FFmpeg cut produced empty or missing file for %s", clip_id)
                return None

            # Step 2: Reframe using SmartCrop (white_canvas, gamer, speaker, center, etc.)
            from processor.smart_crop import SmartCrop
            smart_crop = SmartCrop()
            crop_filter = smart_crop.get_crop_filter(
                video_path=temp_cut,
                start_sec=0.0,
                target_width=self.settings.output_width,
                target_height=self.settings.output_height,
                layout_type=layout_type,
                duration=float(duration_ms / 1000.0),
            )
            reframe_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_cut),
                "-vf", f"{crop_filter},fps=fps=60",
                "-c:v", self.settings.video_codec,
                "-preset", "medium",
                "-crf", str(self.settings.crf),
                "-c:a", self.settings.audio_codec,
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path),
            ]
            run_command_safely(reframe_cmd, timeout=120.0)

            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error("FFmpeg reframe produced empty or missing file for %s", clip_id)
                return None

            # Step 3: Burn captions if transcript is provided
            has_captions = False
            transcript_text = ""
            burn_enabled = getattr(config.vod_settings, "burn_captions", True)

            if transcript_segments and burn_enabled:
                style_enum = normalize_subtitle_style(subtitle_style)
                ass_path = self._generate_ass_captions(
                    clip_id,
                    transcript_segments,
                    base_offset_ms=start_offset_ms,
                    style=style_enum,
                    layout_type=layout_type,
                )
                if ass_path:
                    captioned_path = self._burn_captions(output_path, ass_path)
                    if captioned_path:
                        has_captions = True

                texts = []
                for s in transcript_segments:
                    if hasattr(s, "text"):
                        texts.append(s.text)
                    elif isinstance(s, dict) and "text" in s:
                        texts.append(s["text"])
                transcript_text = " ".join(texts)

            metadata = ClipMetadata(
                clip_id=clip_id,
                clip_path=str(output_path),
                duration=float(duration_ms / 1000.0),
                moment_score=moment_score,
                transcript=transcript_text,
                has_captions=has_captions,
                emotion=emotion,
                source_streamer=streamer_name,
                source_platform=streamer.platform if streamer else "custom",
            )

            # Save metadata JSON sidecar
            meta_path = config.CLIPS_DIR / f"{clip_id}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(asdict(metadata), f, indent=2)

            self._clips.append(metadata)
            logger.info("Clip creation successful: %s", output_path.name)
            return metadata

        except SubprocessExecutionError as err:
            logger.error("FFmpeg subprocess failed for %s: %s", clip_id, err.stderr)
            safe_unlink(output_path)
            return None
        except Exception as e:
            logger.error("Error during clip creation for %s: %s", clip_id, e, exc_info=True)
            safe_unlink(output_path)
            return None
        finally:
            safe_unlink(temp_cut)

    def _generate_ass_captions(
        self,
        clip_id: str,
        transcript_segments: list,
        base_offset_ms: int = 0,
        style: SubtitleStyle = SubtitleStyle.GLACIER_GLOW,
        layout_type: str = "white_canvas",
    ) -> Optional[Path]:
        """Generate a .ass subtitle file with word-by-word highlighting and pop-in animation using CaptionsEngine."""
        try:
            ass_path = config.CLIPS_DIR / f"{clip_id}.ass"
            return self.captions_engine.generate_ass(
                clip_id=clip_id,
                transcript_segments=transcript_segments,
                output_path=ass_path,
                style=style,
                base_offset_ms=base_offset_ms,
                layout_type=layout_type,
            )
        except Exception as e:
            logger.error("Failed to generate ASS subtitles via CaptionsEngine: %s", e)
            return None

    def _burn_captions(self, video_path: Path, ass_path: Path) -> Optional[Path]:
        output_captioned = video_path.parent / f"{video_path.stem}_captioned.mp4"
        # Windows-safe path formatting for libavfilter ass filter
        try:
            rel_path = str(ass_path.relative_to(Path.cwd())).replace("\\", "/")
            ass_filter = f"ass='{rel_path}'"
        except Exception:
            abs_escaped = str(ass_path.absolute()).replace("\\", "/").replace(":", "\\:")
            ass_filter = f"ass=filename='{abs_escaped}'"

        burn_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", ass_filter,
            "-c:v", self.settings.video_codec,
            "-crf", str(self.settings.crf),
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_captioned),
        ]

        try:
            run_command_safely(burn_cmd, timeout=120.0)
            if not output_captioned.exists() or output_captioned.stat().st_size == 0:
                logger.error("FFmpeg burn captions produced empty or missing file.")
                return None

            video_path.unlink(missing_ok=True)
            output_captioned.rename(video_path)
            return video_path
        except SubprocessExecutionError as err:
            logger.error("Exception burning captions: %s", err.stderr)
            safe_unlink(output_captioned)
            return None
        except Exception as e:
            logger.error("Exception burning captions: %s", e)
            safe_unlink(output_captioned)
            return None
        finally:
            safe_unlink(ass_path)

    @property
    def clips(self) -> List[ClipMetadata]:
        return list(self._clips)

    @property
    def recent_clips(self) -> List[ClipMetadata]:
        cutoff = time.time() - 3600
        return [c for c in self._clips if c.timestamp >= cutoff]
