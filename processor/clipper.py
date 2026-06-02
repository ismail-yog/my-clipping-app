"""
StreamClipper — Clipper
Extracts highlight clips, crops to 9:16 portrait, and burns viral-style captions.
"""

import os
import time
import json
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List

import config

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

    # Optional fields for backward compatibility
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
        start_offset: float,
        duration: int,
        moment_score: float,
        transcript_segments: Optional[list] = None,
        emotion: str = "",
        custom_clip_id: Optional[str] = None,
        layout_type: str = "gamer"
    ) -> Optional[ClipMetadata]:
        """
        Create a processed clip from source video.
        1. Cut the segment
        2. Reframe to 9:16 vertical
        3. Burn animated captions if transcript is provided
        """
        streamer_name = streamer.name if streamer else "vod"
        clip_id = custom_clip_id or f"{streamer_name}_{int(time.time())}"
        output_path = config.CLIPS_DIR / f"{clip_id}.mp4"

        logger.info("Creating clip: %s (duration=%ds, start_offset=%.1fs)", clip_id, duration, start_offset)

        temp_cut = config.CLIPS_DIR / f"{clip_id}_temp_cut.mp4"

        try:
            # Step 1: Cut segment with ffmpeg (using stream copy for speed)
            cut_cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_offset),
                "-i", str(source_video),
                "-t", str(duration),
                "-c", "copy",
                str(temp_cut)
            ]
            r = subprocess.run(cut_cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not temp_cut.exists():
                logger.error("FFmpeg cut failed: %s", r.stderr)
                return None

            # Step 2: Reframe to 9:16 (1080x1920)
            reframe_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_cut),
                "-vf", f"scale={self.settings.output_width}:{self.settings.output_height}:force_original_aspect_ratio=increase,crop={self.settings.output_width}:{self.settings.output_height}",
                "-c:v", self.settings.video_codec,
                "-preset", "medium",
                "-crf", str(self.settings.crf),
                "-c:a", self.settings.audio_codec,
                "-b:a", "128k",
                str(output_path)
            ]
            r = subprocess.run(reframe_cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not output_path.exists():
                logger.error("FFmpeg reframe failed: %s", r.stderr)
                return None

            # Step 3: Burn captions if transcript is provided
            has_captions = False
            transcript_text = ""
            burn_enabled = getattr(config.vod_settings, "burn_captions", True)

            if transcript_segments and burn_enabled:
                ass_path = self._generate_ass_captions(clip_id, transcript_segments)
                if ass_path:
                    captioned_path = self._burn_captions(output_path, ass_path)
                    if captioned_path:
                        has_captions = True
                
                # Extract clean transcript text
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
                duration=float(duration),
                moment_score=moment_score,
                transcript=transcript_text,
                has_captions=has_captions,
                emotion=emotion,
                source_streamer=streamer_name,
                source_platform=streamer.platform if streamer else "custom"
            )

            # Save metadata JSON sidecar
            meta_path = config.CLIPS_DIR / f"{clip_id}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(asdict(metadata), f, indent=2)

            self._clips.append(metadata)
            logger.info("Clip creation successful: %s", output_path.name)
            return metadata

        except Exception as e:
            logger.error("Error during clip creation for %s: %s", clip_id, e, exc_info=True)
            return None
        finally:
            # Cleanup temp file
            if temp_cut.exists():
                try:
                    temp_cut.unlink()
                except Exception:
                    pass

    def _generate_ass_captions(self, clip_id: str, transcript_segments: list) -> Optional[Path]:
        """Generate a .ass subtitle file with word-by-word highlighting and pop-in animation."""
        s = self.settings
        ass_path = config.CLIPS_DIR / f"{clip_id}.ass"

        # ASS Header and Styles
        header = f"""[Script Info]
Title: {clip_id}
ScriptType: v4.00+
PlayResX: {s.output_width}
PlayResY: {s.output_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,250,0

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

        # Group words into 3-5 word chunks
        chunks = []
        current_chunk = []
        for w in all_words:
            w_word = w.word if hasattr(w, "word") else w.get("word", "")
            w_start = w.start if hasattr(w, "start") else w.get("start", 0.0)
            w_end = w.end if hasattr(w, "end") else w.get("end", 0.0)
            w_prob = w.probability if hasattr(w, "probability") else w.get("probability", 1.0)
            
            w_dict = {"word": w_word, "start": w_start, "end": w_end, "prob": w_prob}
            
            if current_chunk and (w_dict["start"] - current_chunk[-1]["end"] > 1.5 or len(current_chunk) >= 4):
                chunks.append(current_chunk)
                current_chunk = []
            current_chunk.append(w_dict)
            
        if current_chunk:
            chunks.append(current_chunk)

        if chunks:
            # Word-by-word highlights
            for chunk in chunks:
                for i, active_word in enumerate(chunk):
                    start_ts = self._seconds_to_ass_time(active_word["start"])
                    end_ts = self._seconds_to_ass_time(active_word["end"])

                    text_parts = []
                    for j, w in enumerate(chunk):
                        word_str = w["word"].upper()
                        if j == i:
                            # Yellow text, bold, slightly scaled up
                            text_parts.append(f"{{\\b1\\fscx115\\fscy115\\3c&H00FFFF&}}{word_str}{{\\r}}")
                        else:
                            text_parts.append(word_str)

                    full_text = " ".join(text_parts)
                    lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{full_text}")
        else:
            # Fallback to segment level
            for seg in transcript_segments:
                seg_text = seg.text if hasattr(seg, "text") else seg.get("text", "")
                seg_start = seg.start if hasattr(seg, "start") else seg.get("start", 0.0)
                seg_end = seg.end if hasattr(seg, "end") else seg.get("end", 0.0)
                
                start_ts = self._seconds_to_ass_time(seg_start)
                end_ts = self._seconds_to_ass_time(seg_end)
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
        
        # Format the ASS path for the ffmpeg subtitle filter (handle Windows escaping)
        ass_filter_path = str(ass_path.absolute()).replace("\\", "/").replace(":", "\\:")
        
        burn_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{ass_filter_path}'",
            "-c:v", self.settings.video_codec,
            "-crf", str(self.settings.crf),
            "-c:a", "copy",
            str(output_captioned)
        ]

        try:
            r = subprocess.run(burn_cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not output_captioned.exists():
                logger.error("FFmpeg burn captions failed: %s", r.stderr)
                return None
            
            # Replace original video with captioned version
            try:
                video_path.unlink()
                output_captioned.rename(video_path)
            except Exception as e:
                logger.error("Failed to overwrite video with captioned version: %s", e)
                return None

            return video_path
        except Exception as e:
            logger.error("Exception burning captions: %s", e)
            return None
        finally:
            # Clean up .ass file
            if ass_path.exists():
                try:
                    ass_path.unlink()
                except Exception:
                    pass

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """Convert float seconds to ASS timestamp format (H:MM:SS.CC)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @property
    def clips(self) -> list[ClipMetadata]:
        return list(self._clips)

    @property
    def recent_clips(self) -> list[ClipMetadata]:
        cutoff = time.time() - 3600
        return [c for c in self._clips if c.timestamp >= cutoff]
