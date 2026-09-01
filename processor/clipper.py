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
    ) -> Optional[ClipMetadata]:
        """
        Create a processed clip from source video.
        Uses exact millisecond offsets and CFR conversion.
        """
        streamer_name = streamer.name if streamer else "vod"
        clip_id = custom_clip_id or f"{streamer_name}_{int(time.time())}"
        output_path = config.CLIPS_DIR / f"{clip_id}.mp4"

        start_offset_ms = seconds_to_ms(start_offset)
        duration_ms = seconds_to_ms(duration)

        logger.info(
            "Creating clip: %s (duration_ms=%d, start_offset_ms=%d)",
            clip_id, duration_ms, start_offset_ms,
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

            # Step 2: Reframe to 9:16 (1080x1920)
            reframe_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_cut),
                "-vf", f"scale={self.settings.output_width}:{self.settings.output_height}:force_original_aspect_ratio=increase,crop={self.settings.output_width}:{self.settings.output_height},fps=fps=60",
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
                ass_path = self._generate_ass_captions(clip_id, transcript_segments, base_offset_ms=start_offset_ms)
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
    ) -> Optional[Path]:
        """Generate a .ass subtitle file with word-by-word highlighting and pop-in animation."""
        s = self.settings
        ass_path = config.CLIPS_DIR / f"{clip_id}.ass"

        header = f"""[Script Info]
Title: {clip_id}
ScriptType: v4.00+
PlayResX: {s.output_width}
PlayResY: {s.output_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,30,30,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]

        # Flatten all words
        all_words = []
        for seg in transcript_segments:
            if hasattr(seg, "words") and seg.words:
                all_words.extend(seg.words)
            elif isinstance(seg, dict) and "words" in seg:
                all_words.extend(seg["words"])

        # Group words into chunks
        chunks = []
        current_chunk = []
        for w in all_words:
            w_word = getattr(w, "word", None) or (w.get("word", "") if isinstance(w, dict) else "")
            w_start_sec = getattr(w, "start", None) if hasattr(w, "start") else (w.get("start", 0.0) if isinstance(w, dict) else 0.0)
            w_end_sec = getattr(w, "end", None) if hasattr(w, "end") else (w.get("end", 0.0) if isinstance(w, dict) else 0.0)
            w_prob = getattr(w, "probability", 1.0) if hasattr(w, "probability") else (w.get("probability", 1.0) if isinstance(w, dict) else 1.0)

            w_start_ms = max(0, seconds_to_ms(w_start_sec) - base_offset_ms)
            w_end_ms = max(w_start_ms + 10, seconds_to_ms(w_end_sec) - base_offset_ms)

            w_dict = {"word": w_word, "start_ms": w_start_ms, "end_ms": w_end_ms, "prob": w_prob}

            if current_chunk and (w_dict["start_ms"] - current_chunk[-1]["end_ms"] > 1500 or len(current_chunk) >= 4):
                chunks.append(current_chunk)
                current_chunk = []
            current_chunk.append(w_dict)

        if current_chunk:
            chunks.append(current_chunk)

        if chunks:
            for chunk in chunks:
                for i, active_word in enumerate(chunk):
                    start_ts = ms_to_ass_timestamp(active_word["start_ms"])
                    end_ts = ms_to_ass_timestamp(active_word["end_ms"])

                    text_parts = []
                    for j, w in enumerate(chunk):
                        word_str = str(w["word"]).strip().upper()
                        if j == i:
                            text_parts.append(f"{{\\b1\\fscx115\\fscy115\\3c&H00FFFF&}}{word_str}{{\\r}}")
                        else:
                            text_parts.append(word_str)

                    full_text = " ".join(text_parts)
                    lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{full_text}")
        else:
            for seg in transcript_segments:
                seg_text = getattr(seg, "text", "") if hasattr(seg, "text") else (seg.get("text", "") if isinstance(seg, dict) else "")
                seg_start_sec = getattr(seg, "start", 0.0) if hasattr(seg, "start") else (seg.get("start", 0.0) if isinstance(seg, dict) else 0.0)
                seg_end_sec = getattr(seg, "end", 0.0) if hasattr(seg, "end") else (seg.get("end", 0.0) if isinstance(seg, dict) else 0.0)

                start_ms = max(0, seconds_to_ms(seg_start_sec) - base_offset_ms)
                end_ms = max(start_ms + 10, seconds_to_ms(seg_end_sec) - base_offset_ms)

                start_ts = ms_to_ass_timestamp(start_ms)
                end_ts = ms_to_ass_timestamp(end_ms)
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{seg_text}")

        try:
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return ass_path
        except Exception as e:
            logger.error("Failed to write ASS file: %s", e)
            return None

    def _burn_captions(self, video_path: Path, ass_path: Path) -> Optional[Path]:
        """Burn ASS subtitles into the video using ffmpeg."""
        output_captioned = video_path.parent / f"{video_path.stem}_captioned.mp4"
        ass_filter_path = str(ass_path.absolute()).replace("\\", "/").replace(":", "\\:")

        burn_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{ass_filter_path}'",
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
