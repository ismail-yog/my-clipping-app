"""
StreamClipper — Clipper
Extracts highlight clips, crops to 9:16, and burns viral-style captions.
"""

import json
import time
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

import config
from detector.sentiment import TranscriptSegment, TranscriptWord
from processor.scene_detector import SceneDetector
from processor.smart_crop import SmartCrop
from processor.audio_engine import AudioEngine

logger = logging.getLogger("streamclipper.clipper")


@dataclass
class ClipMetadata:
    """Metadata for a processed clip."""
    clip_id: str
    source_streamer: str
    source_platform: str
    clip_path: str
    duration: float
    timestamp: float
    moment_score: float
    transcript: str
    emotion: str
    width: int
    height: int
    has_captions: bool
    seo_ready: bool = False
    uploaded: bool = False
    upload_url: str = ""
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)


class Clipper:
    """
    Extracts clips from the rolling buffer, crops to 9:16 portrait,
    and burns word-level captions in a viral TikTok/Shorts style.
    """

    def __init__(self, settings: Optional[config.ClipSettings] = None):
        self.settings = settings or config.clip_settings
        self._clips: list[ClipMetadata] = []
        self._scene_detector = SceneDetector()
        self._smart_crop = SmartCrop()
        self._audio_engine = AudioEngine()

    def create_clip(
        self,
        source_video: Path,
        streamer: Optional[config.StreamerConfig],
        start_offset: float = 0.0,
        duration: Optional[int] = None,
        moment_score: float = 0.0,
        transcript_segments: Optional[list[TranscriptSegment]] = None,
        emotion: str = "",
        custom_clip_id: Optional[str] = None,
        layout_type: str = "gamer",
    ) -> Optional[ClipMetadata]:
        """
        Create a processed clip from source video.

        1. Cut the relevant section
        2. Crop/pad to 9:16 (1080x1920)
        3. Burn captions if transcript available
        4. Save with metadata sidecar
        """
        clip_duration = duration or self.settings.default_duration
        streamer_channel = streamer.channel if streamer else "vod"
        clip_id = custom_clip_id or f"{streamer_channel}_{int(time.time())}"
        output_path = config.CLIPS_DIR / f"{clip_id}.{self.settings.output_format}"

        logger.info(
            "Creating clip: %s (%.0fs from offset %.1f)",
            clip_id, clip_duration, start_offset,
        )

        try:
            # Step 1: Snap to nearest scene boundaries
            end_offset = start_offset + clip_duration
            adj_start, adj_end = self._scene_detector.find_nearest_scenes(
                source_video, start_offset, end_offset
            )
            
            # If the clip became too short, revert
            if adj_end - adj_start < 5.0:
                adj_start, adj_end = start_offset, end_offset
                
            final_start = adj_start
            final_duration = int(adj_end - adj_start)
            
            # Step 2: Generate caption subtitle file if we have transcript
            subtitle_path = None
            transcript_text = ""
            if transcript_segments:
                subtitle_path = self._generate_ass_subtitles(
                    transcript_segments, clip_id
                )
                transcript_text = " ".join(s.text for s in transcript_segments)

            # Step 3: Build FFmpeg command
            cmd = self._build_ffmpeg_cmd(
                source_video, output_path, final_start,
                final_duration, subtitle_path,
                layout_type=layout_type,
            )

            # Step 4: Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error("FFmpeg clip failed: %s", result.stderr[-500:])
                return None

            if not output_path.exists():
                logger.error("Clip file not created")
                return None

            # Step 4: Create metadata
            metadata = ClipMetadata(
                clip_id=clip_id,
                source_streamer=streamer.name if streamer else "vod",
                source_platform=streamer.platform if streamer else "custom",
                clip_path=str(output_path),
                duration=clip_duration,
                timestamp=time.time(),
                moment_score=moment_score,
                transcript=transcript_text[:1000],
                emotion=emotion,
                width=self.settings.output_width,
                height=self.settings.output_height,
                has_captions=subtitle_path is not None,
            )

            # Save metadata sidecar
            meta_path = config.CLIPS_DIR / f"{clip_id}.json"
            with open(meta_path, "w") as f:
                json.dump(asdict(metadata), f, indent=2)

            self._clips.append(metadata)
            logger.info("✅ Clip created: %s (%.1fs)", output_path.name, clip_duration)
            return metadata

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timed out creating clip")
            return None
        except Exception as e:
            logger.error("Clip creation failed: %s", e)
            return None

    def _build_ffmpeg_cmd(
        self,
        source: Path,
        output: Path,
        start_offset: float,
        duration: int,
        subtitle_path: Optional[Path],
        layout_type: str = "gamer",
    ) -> list[str]:
        """Build the FFmpeg command for clip extraction + formatting."""
        s = self.settings

        # Get crop/split filter
        filter_complex = self._smart_crop.get_crop_filter(
            source, start_offset, s.output_width, s.output_height, layout_type=layout_type, duration=duration
        )

        # Label the video filter complex
        video_filter = "[0:v]" + filter_complex + "[v_out]"

        # Burn subtitles if available
        if subtitle_path and subtitle_path.exists():
            # Windows ASS filter needs specific escaping
            sub_path_escaped = str(subtitle_path.absolute()).replace("\\", "/").replace(":", "\\:")
            video_filter += f";[v_out]ass='{sub_path_escaped}'[v_captioned]"
            v_output_label = "[v_captioned]"
        else:
            v_output_label = "[v_out]"

        # Build audio filter graph and get extra input files (BGM, SFX)
        audio_filter, extra_inputs = self._audio_engine.build_audio_filter(
            duration=duration,
            has_sfx=True,
            sfx_name="vine_boom",
            sfx_offset_sec=duration * 0.7,
        )

        # Combine video and audio filter complex
        full_filter_complex = video_filter + ";" + audio_filter

        # Construct FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(max(0, start_offset)),
            "-i", str(source),
        ]
        
        # Append extra inputs (BGM/SFX)
        cmd.extend(extra_args if 'extra_args' in locals() else extra_inputs)

        cmd.extend([
            "-t", str(duration),
            "-filter_complex", full_filter_complex,
            "-map", v_output_label,
            "-map", "[a_out]",
            "-c:v", s.video_codec,
            "-crf", str(s.crf),
            "-preset", "fast",
            "-c:a", s.audio_codec,
            "-b:a", "128k",
            "-r", str(s.output_fps),
            "-movflags", "+faststart",
            str(output),
        ])

        return cmd

    def _generate_ass_subtitles(
        self,
        segments: list[TranscriptSegment],
        clip_id: str,
    ) -> Optional[Path]:
        """Generate an ASS subtitle file with viral-style word-by-word captions."""
        s = self.settings
        ass_path = config.CLIPS_DIR / f"{clip_id}.ass"

        # Emojis dictionary
        emoji_map = {
            "insane": "🤯", "crazy": "🤯", "wtf": "🤬", "oh my god": "😱", "omg": "😱",
            "dead": "💀", "died": "💀", "kill": "💀", "fire": "🔥", "lit": "🔥",
            "win": "🏆", "clutch": "👑", "epic": "⚡", "love": "❤️", "hype": "🔥",
            "laugh": "😂", "funny": "😂", "lol": "😂", "screaming": "😱", "shot": "💥",
            "aim": "🎯", "headshot": "🎯", "ez": "😎", "easy": "😎", "noob": "🤡",
            "hacker": "🤖", "money": "💰", "cash": "💰", "run": "🏃", "fast": "⚡",
            "stream": "💻", "live": "🔴", "speed": "⚡", "rage": "😡", "angry": "😡",
        }

        def clean_word(w: str) -> str:
            return "".join(c for c in w.lower() if c.isalnum())

        def get_word_with_emoji(word: str) -> str:
            cw = clean_word(word)
            emoji = emoji_map.get(cw)
            return f"{word} {emoji}" if emoji else word

        # ASS header with thicker black outline (Outline=6, Shadow=2) and bold Arial Black font
        font_name = "Arial Black"
        header = f"""[Script Info]
Title: {clip_id}
ScriptType: v4.00+
PlayResX: {s.output_width}
PlayResY: {s.output_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},90,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        lines = [header]

        # Flatten all words from all segments
        all_words = []
        for seg in segments:
            if seg.words:
                all_words.extend(seg.words)

        # Chunk words into groups of max 3 words
        chunks = []
        current_chunk = []
        for w in all_words:
            if current_chunk and (w.start - current_chunk[-1].end > 1.0 or len(current_chunk) >= 3):
                chunks.append(current_chunk)
                current_chunk = []
            current_chunk.append(w)
        if current_chunk:
            chunks.append(current_chunk)

        if chunks:
            # Word-by-word highlight style for chunks
            for chunk in chunks:
                for i, active_word in enumerate(chunk):
                    start_ts = self._seconds_to_ass_time(active_word.start)
                    end_ts = self._seconds_to_ass_time(active_word.end)

                    # Build line with active word capitalized and highlighted yellow
                    text_parts = []
                    for j, w in enumerate(chunk):
                        word_text = get_word_with_emoji(w.word)
                        if j == i:
                            text_parts.append(f"{{\\c&H00FFFF&}}{word_text.upper()}{{\\c&HFFFFFF&}}")
                        else:
                            text_parts.append(word_text)

                    full_text = " ".join(text_parts)
                    lines.append(
                        f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{full_text}"
                    )
        else:
            # Fallback to segment levels if no word timings
            for seg in segments:
                start_ts = self._seconds_to_ass_time(seg.start)
                end_ts = self._seconds_to_ass_time(seg.end)
                lines.append(
                    f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{seg.text}"
                )

        try:
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return ass_path
        except Exception as e:
            logger.error("Failed to write ASS subtitles: %s", e)
            return None

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """Convert seconds to ASS timestamp format (H:MM:SS.CC)."""
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
