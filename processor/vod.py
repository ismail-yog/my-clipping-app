"""
StreamClipper — VOD Processor (Hardened & Optimized)
Downloads a video, transcribes it with Whisper, finds viral moments, and extracts clips with captions.
Enforces integer millisecond timestamps, CFR transcoding, strict subprocess execution, and immediate VRAM deallocation.
"""

import time
import uuid
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from database import Database
from task_queue import TaskQueue
from processor.clipper import Clipper, ClipMetadata
from detector.sentiment import TranscriptSegment, TranscriptWord
from processor.subprocess_utils import (
    run_command_safely,
    safe_unlink,
    ms_to_ass_timestamp,
    ms_to_timestamp,
    seconds_to_ms,
    free_vram,
    SubprocessExecutionError,
    MediaProcessingError,
)

logger = logging.getLogger("streamclipper.processor.vod")

# Global progress tracker for WebSocket/API polling
VOD_PROGRESS: dict[str, dict] = {}

# Global registry of active processors for cancellation: job_id -> VODProcessor instance
ACTIVE_PROCESSORS: dict[str, 'VODProcessor'] = {}
ACTIVE_PROCESSORS_LOCK = threading.Lock()


def _get_video_duration(path: Path) -> float:
    """Get video duration in seconds using ffprobe safely."""
    try:
        res = run_command_safely(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            timeout=15.0,
        )
        data = json.loads(res.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


from processor.captions_engine import CaptionsEngine, SubtitleStyle

class VODClipper(Clipper):
    """Custom Clipper subclass for VOD processing with multi-style animated subtitle engine."""

    def __init__(self, settings=None, subtitle_style: str = "hormozi"):
        super().__init__(settings)
        self.current_start_offset_ms: int = 0
        try:
            self.subtitle_style = SubtitleStyle(subtitle_style.lower())
        except Exception:
            self.subtitle_style = SubtitleStyle.HORMOZI
        self.captions_engine = CaptionsEngine(default_style=self.subtitle_style)

    def _generate_ass_captions(self, clip_id: str, transcript_segments: list, base_offset_ms: int = 0) -> Optional[Path]:
        """Generate ASS subtitle file with word-level karaoke animation using CaptionsEngine."""
        if not transcript_segments:
            return None

        base_time_ms = base_offset_ms if base_offset_ms > 0 else self.current_start_offset_ms
        sub_path = config.CLIPS_DIR / f"{clip_id}.ass"

        try:
            return self.captions_engine.generate_ass(
                clip_id=clip_id,
                transcript_segments=transcript_segments,
                output_path=sub_path,
                style=self.subtitle_style,
                base_offset_ms=base_time_ms
            )
        except Exception as e:
            logger.error("Failed to generate ASS subtitles in VODClipper: %s", e)
            return None

    def _burn_captions(self, video_path: Path, ass_path: Path) -> Optional[Path]:
        """Burn captions into the clip preserving backup copy for verification if needed."""
        import shutil
        temp_copy = ass_path.parent / f"{ass_path.name}.bak"
        try:
            shutil.copy(ass_path, temp_copy)
        except Exception:
            temp_copy = None

        res = super()._burn_captions(video_path, ass_path)

        if temp_copy and temp_copy.exists():
            try:
                shutil.move(temp_copy, ass_path)
            except Exception:
                pass
        return res


class VODProcessor:
    """Processes VOD URLs to extract viral clips from past streams."""

    def __init__(self, db: Database, task_queue: Optional[TaskQueue] = None):
        self.db = db
        self.task_queue = task_queue
        self._whisper_model = None
        self.cancelled = False
        self.active_processes = set()
        self._lock = threading.Lock()
        self._current_vid = ""
        self._current_segments = []
        self._timestamp_scores = {}
        self._timestamp_emotions = {}

    def cancel(self):
        """Cancel the active VOD processing task."""
        with self._lock:
            self.cancelled = True
            for proc in list(self.active_processes):
                try:
                    logger.info("Killing active subprocess for cancelled job: PID %d", proc.pid)
                    proc.kill()
                except Exception as e:
                    logger.error("Failed to kill subprocess: %s", e)

    @classmethod
    def cancel_job(cls, job_id: str) -> bool:
        """Cancel VOD processing job by ID."""
        with ACTIVE_PROCESSORS_LOCK:
            processor = ACTIVE_PROCESSORS.get(job_id)
            if processor:
                processor.cancel()
                return True
        return False

    def run_subprocess(self, cmd: list[str], timeout: Optional[int] = None, capture_output: bool = True, text: bool = True, line_callback = None) -> subprocess.CompletedProcess:
        """Run subprocess supporting cancellation and real-time line parsing."""
        if self.cancelled:
            raise RuntimeError("Job cancelled")

        kwargs = {}
        if capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT if line_callback else subprocess.PIPE
        if text:
            kwargs["text"] = True

        with self._lock:
            if self.cancelled:
                raise RuntimeError("Job cancelled")
            proc = subprocess.Popen(cmd, **kwargs)
            self.active_processes.add(proc)

        stdout_lines = []
        stderr_lines = []
        try:
            if line_callback and proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if self.cancelled:
                        proc.kill()
                        break
                    stdout_lines.append(line)
                    try:
                        line_callback(line)
                    except Exception:
                        pass
                proc.wait(timeout=timeout)
            else:
                stdout_text, stderr_text = proc.communicate(timeout=timeout)
                if stdout_text:
                    stdout_lines.append(stdout_text)
                if stderr_text:
                    stderr_lines.append(stderr_text)

            ret = proc.returncode
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=ret,
                stdout="".join(stdout_lines),
                stderr="".join(stderr_lines),
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            raise SubprocessExecutionError(
                cmd=cmd,
                returncode=-1,
                stdout="".join(stdout_lines),
                stderr="".join(stderr_lines),
                message=f"Subprocess timed out after {timeout} seconds",
            )
        finally:
            with self._lock:
                self.active_processes.discard(proc)

    def process_url(self, url: str, job_id: str = "", layout_type: str = "gamer") -> bool:
        """Process URL to extract viral clips."""
        if job_id:
            with ACTIVE_PROCESSORS_LOCK:
                ACTIVE_PROCESSORS[job_id] = self

        self._current_vid = str(uuid.uuid4())[:8]

        def progress(pct: int, msg: str):
            if job_id:
                VOD_PROGRESS[job_id] = {"url": url, "progress": pct, "status": msg}
            logger.info("[%d%%] %s", pct, msg)

        video_path = None
        try:
            # ── 1. DOWNLOAD ─────────────────────────────────────────────────────
            progress(5, f"Downloading video ({config.vod_settings.download_resolution}p)...")
            video_path, err_msg = self._download_vod(url, progress_callback=progress)
            if not video_path:
                logger.error("VOD download failed for URL: %s (Reason: %s)", url, err_msg)
                progress(0, f"Download failed: {err_msg or 'Invalid URL or unavailable video'}")
                return False

            duration = _get_video_duration(video_path)
            logger.info("VOD details: path=%s, duration=%.1fs", video_path, duration)

            # ── 2. TRANSCRIBE ───────────────────────────────────────────────────
            progress(25, "Extracting audio and transcribing VOD...")
            self._current_segments = self._transcribe_vod(video_path, progress_callback=progress)
            if not self._current_segments:
                logger.warning("No transcript segments generated, using fallback segments")
                self._current_segments = self._create_fallback_segments(duration)

            # ── 3. FIND VIRAL MOMENTS ───────────────────────────────────────────
            progress(55, "Analyzing transcripts and identifying viral highlights...")
            timestamps = self._find_viral_moments(self._current_segments, duration=duration)
            if not timestamps:
                timestamps = [0.0]

            logger.info("Found %d viral timestamps: %s", len(timestamps), timestamps)

            # ── 4. EXTRACT CLIPS (Parallel renders) ─────────────────────────────
            progress(65, f"Extracting and rendering {len(timestamps)} clips in parallel...")
            clips = self._cut_clips_parallel(video_path, timestamps, layout_type, total_duration=duration)

            if not clips:
                progress(0, "Clip rendering produced 0 clips")
                return False

            # ── 5. SAVE AND ORCHESTRATE SEO / UPLOADS ───────────────────────────
            success_count = 0
            for clip in clips:
                auto_approve = clip.moment_score >= 0.8
                self.db.save_clip(
                    clip_id=clip.clip_id,
                    streamer_name="VOD_Clipper",
                    platform="custom",
                    clip_path=clip.clip_path,
                    duration=clip.duration,
                    moment_score=clip.moment_score,
                    emotion=clip.emotion,
                    transcript=clip.transcript[:500],
                    has_captions=clip.has_captions,
                    auto_approve=auto_approve,
                )

                try:
                    from processor.seo import SEOGenerator
                    seo_gen = SEOGenerator()
                    seo_meta = seo_gen.generate(
                        transcript=clip.transcript,
                        streamer_name="VOD_Clipper",
                        emotion=clip.emotion,
                        platform="custom",
                    )
                except Exception as e:
                    logger.error("SEO Generator failed: %s", e)
                    from processor.seo import SEOMetadata
                    seo_meta = SEOMetadata(
                        title=self._generate_title(clip.transcript, clip.emotion),
                        description=clip.transcript[:200],
                        tags=["shorts", "viral", "clips", clip.emotion],
                        hook_text=self._generate_title(clip.transcript, clip.emotion),
                        thumbnail_prompt="",
                        generated_by="template",
                    )

                self.db.update_clip_seo(
                    clip_id=clip.clip_id,
                    title=seo_meta.title,
                    description=seo_meta.description,
                    tags=seo_meta.tags,
                    hook_text=seo_meta.hook_text,
                    seo_method=seo_meta.generated_by,
                )

                thumbnail_path = ""
                try:
                    from processor.thumbnail import ThumbnailGenerator
                    thumb_gen = ThumbnailGenerator()
                    thumb_res = thumb_gen.generate(
                        clip_path=Path(clip.clip_path),
                        title_text=seo_meta.title,
                        streamer_name="VOD_Clipper",
                    )
                    if thumb_res:
                        thumbnail_path = str(thumb_res)
                except Exception as e:
                    logger.error("Failed to generate thumbnail for VOD clip: %s", e)

                if auto_approve and self.task_queue:
                    self.task_queue.submit(
                        job_type="upload",
                        clip_id=clip.clip_id,
                        payload={
                            "clip_path": clip.clip_path,
                            "title": seo_meta.title,
                            "description": seo_meta.description,
                            "tags": seo_meta.tags,
                            "thumbnail_path": thumbnail_path,
                        },
                        priority=3,
                    )
                    logger.info("🔥 High viral score (%.2f) — VOD clip %s queued for auto-upload", clip.moment_score, clip.clip_id)

                success_count += 1

            progress(100, f"Done! {success_count} clips generated")
            return success_count > 0

        except Exception as e:
            logger.error("VOD processing pipeline error: %s", e, exc_info=True)
            progress(0, f"Error: {e}")
            return False
        finally:
            if job_id:
                with ACTIVE_PROCESSORS_LOCK:
                    ACTIVE_PROCESSORS.pop(job_id, None)
            if video_path and video_path.exists() and "vod_testvod" not in str(video_path):
                try:
                    safe_unlink(video_path)
                    logger.info("Cleaned up raw downloaded VOD: %s", video_path)
                except Exception as e:
                    logger.error("Failed to delete raw VOD: %s", e)
            if job_id:
                threading.Timer(30, lambda: VOD_PROGRESS.pop(job_id, None)).start()

    def _download_vod(self, url: str, progress_callback = None) -> Tuple[Optional[Path], str]:
        """Download VOD with yt-dlp and fallback to streamlink for live/kick/twitch."""
        import re
        test_path = config.TEMP_MEDIA_DIR / f"vod_{self._current_vid}" / "video.mp4"
        if test_path.exists():
            logger.info("Found pre-existing mock VOD video at %s", test_path)
            return test_path, ""

        timestamp = int(time.time())
        output_path = config.RAW_DIR / f"vod_{timestamp}.mp4"
        res = config.vod_settings.download_resolution

        def parse_line(line: str):
            match = re.search(r"\[download\]\s+(\d+\.\d+)%", line)
            if match and progress_callback:
                dl_pct = float(match.group(1))
                mapped = 5 + int((dl_pct / 100.0) * 20.0)
                progress_callback(mapped, f"Downloading VOD ({dl_pct:.1f}%)...")

        # 1. Try yt-dlp
        cmd = [
            "yt-dlp",
            "--newline",
            "--no-colors",
            "--no-playlist",
            "--no-check-certificate",
            "--merge-output-format", "mp4",
            "-f", f"bestvideo[height<={res}]+bestaudio/best[height<={res}]/best",
            "-o", str(output_path),
            url,
        ]

        try:
            logger.info("Running yt-dlp download: %s", " ".join(cmd))
            r = self.run_subprocess(cmd, timeout=600, line_callback=parse_line)
            if output_path.exists() and output_path.stat().st_size > 0:
                return output_path, ""

            pattern = f"vod_{timestamp}*"
            matches = list(config.RAW_DIR.glob(pattern))
            if matches and matches[0].exists() and matches[0].stat().st_size > 0:
                logger.info("Found downloaded video via match: %s", matches[0])
                return matches[0], ""

            err_out = (r.stderr or "").strip()
            if "404" in err_out:
                return None, "Video not found (HTTP 404) or stream expired"
            elif "Private video" in err_out:
                return None, "Video is private or restricted"
        except Exception as e:
            logger.warning("yt-dlp attempt failed: %s", e)

        # 2. Fallback to Streamlink for Kick / Twitch / HLS Streams
        if any(domain in url for domain in ["kick.com", "twitch.tv"]):
            try:
                logger.info("Attempting Streamlink fallback for %s...", url)
                streamlink_cmd = [
                    "streamlink",
                    "--output", str(output_path),
                    url,
                    "best",
                    "--hls-duration", "120",
                ]
                sr = self.run_subprocess(streamlink_cmd, timeout=180)
                if output_path.exists() and output_path.stat().st_size > 0:
                    return output_path, ""
            except Exception as e:
                logger.error("Streamlink fallback also failed: %s", e)

        return None, "Could not extract stream. Ensure URL is public and valid."

    def _transcribe_vod(self, video_path: Path, progress_callback = None) -> list[TranscriptSegment]:
        """Extract audio first, then transcribe entire video with Whisper and enforce immediate VRAM release."""
        temp_dir = video_path.parent
        audio_path = temp_dir / f"audio_{int(time.time() * 1000)}.wav"

        audio_cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ]
        try:
            logger.info("Extracting mono audio for Whisper...")
            r = self.run_subprocess(audio_cmd, timeout=120)
            if r.returncode != 0 or not audio_path.exists():
                logger.error("Audio extraction failed")
                return []
        except Exception as e:
            logger.error("Audio extraction exception: %s", e)
            return []

        model = None
        try:
            try:
                from faster_whisper import WhisperModel
                logger.info("Loading Whisper model: %s on device: %s (%s)...",
                            config.WHISPER_MODEL, config.WHISPER_DEVICE, config.WHISPER_COMPUTE_TYPE)
                model = WhisperModel(
                    config.WHISPER_MODEL,
                    device=config.WHISPER_DEVICE,
                    compute_type=config.WHISPER_COMPUTE_TYPE,
                )
            except Exception as e:
                logger.warning("Whisper primary load failed (%s), falling back to base CPU...", e)
                import whisper
                model = whisper.load_model("base")

            logger.info("Transcribing VOD audio with Whisper...")
            if hasattr(model, "transcribe") and not hasattr(model, "encoder"):
                segs, info = model.transcribe(
                    str(audio_path),
                    word_timestamps=True,
                    language="en",
                    vad_filter=True,
                    beam_size=3,
                    temperature=0.0,
                    condition_on_previous_text=True,
                )
                total_duration = getattr(info, "duration", 1.0) or 1.0
                result = []
                for seg in segs:
                    if self.cancelled:
                        logger.info("Transcription cancelled")
                        break
                    words = []
                    if seg.words:
                        words = [TranscriptWord(word=w.word.strip(), start=w.start, end=w.end, probability=w.probability)
                                 for w in seg.words]
                    result.append(TranscriptSegment(
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                        words=words,
                    ))
                    if progress_callback and total_duration > 0:
                        whisper_pct = min(1.0, seg.end / total_duration)
                        mapped = 25 + int(whisper_pct * 30.0)
                        progress_callback(mapped, f"Transcribing audio ({int(whisper_pct * 100)}%)...")
                return result
            else:
                out = model.transcribe(str(audio_path), word_timestamps=True)
                result = []
                for s in out.get("segments", []):
                    words = []
                    for w in s.get("words", []):
                        words.append(TranscriptWord(
                            word=w.get("word", "").strip(),
                            start=w.get("start", 0.0),
                            end=w.get("end", 0.0),
                            probability=w.get("probability", 1.0),
                        ))
                    result.append(TranscriptSegment(
                        start=s.get("start", 0.0),
                        end=s.get("end", 0.0),
                        text=s.get("text", "").strip(),
                        words=words,
                    ))
                return result
        except Exception as e:
            logger.error("Whisper transcription error: %s", e)
            return []
        finally:
            if model is not None:
                del model
                model = None
            free_vram()
            safe_unlink(audio_path)

    def _find_viral_moments(self, transcript: list[TranscriptSegment], duration: float = 0.0) -> list[float]:
        """Score each 30-second window and return top N timestamps with millisecond precision."""
        if not transcript:
            return [0.0]

        hype_words = [
            "insane", "crazy", "wtf", "omg", "lol", "lmao", "no way", "unbelievable", "huge", "shocking",
            "screaming", "died", "ruined", "secret", "never", "finally", "broke", "scared", "impossible",
            "win", "clutch", "epic", "perfect", "destroy", "rage", "crying", "hacker", "aimbot", "glitch",
            "broken", "holy",
        ]

        scored_windows = []
        self._timestamp_scores = {}
        self._timestamp_emotions = {}

        for seg in transcript:
            start_ms = seconds_to_ms(seg.start)
            end_ms = start_ms + 30000

            win_segs = [s for s in transcript if seconds_to_ms(s.start) >= start_ms and seconds_to_ms(s.start) < end_ms]
            if not win_segs:
                continue

            text = " ".join(s.text for s in win_segs)
            text_lower = text.lower()

            score = 0.0
            for word in hype_words:
                score += text_lower.count(word) * 1.5

            score += text.count("!") * 1.0

            words = text.split()
            caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)
            score += caps_words * 0.5

            dur_sec = max((end_ms - start_ms) / 1000.0, 1.0)
            wps = len(words) / dur_sec
            wps_score = min(1.0, wps / 4.0)
            score += wps_score * 2.0

            normalized_score = round(min(1.0, max(0.3, score / 10.0)), 3)

            if wps > 3.0:
                emotion = "surprise"
            elif len(words) > 15:
                emotion = "joy"
            else:
                emotion = "neutral"

            start_sec = start_ms / 1000.0
            scored_windows.append((start_sec, normalized_score, emotion))

        scored_windows.sort(key=lambda x: x[1], reverse=True)

        max_clips = config.vod_settings.max_clips
        selected_timestamps = []
        for ts, score, emotion in scored_windows:
            if len(selected_timestamps) >= max_clips:
                break

            overlap = any(abs(seconds_to_ms(ts) - seconds_to_ms(sel)) < 30000 for sel in selected_timestamps)
            if not overlap:
                selected_timestamps.append(ts)
                self._timestamp_scores[ts] = score
                self._timestamp_emotions[ts] = emotion

        # Guaranteed fallback if no moment was scored
        if not selected_timestamps:
            selected_timestamps = [0.0]
            self._timestamp_scores[0.0] = 0.85
            self._timestamp_emotions[0.0] = "joy"

        return selected_timestamps

    def _cut_clips_parallel(
        self,
        video_path: Path,
        timestamps: list[float],
        layout_type: str,
        total_duration: float = 0.0,
    ) -> list[ClipMetadata]:
        """Cut clips in parallel using ThreadPoolExecutor and Clipper with millisecond offsets."""
        clipper = VODClipper()
        results: list[ClipMetadata] = []
        lock = threading.Lock()
        configured_duration = config.vod_settings.clip_duration

        def extract_one(i: int, ts: float) -> Optional[ClipMetadata]:
            if self.cancelled:
                return None
            clip_id = f"vod_{self._current_vid}_{i}"
            ts_ms = seconds_to_ms(ts)

            # Adjust duration if video is shorter than configured duration
            actual_duration = configured_duration
            if total_duration > 0 and (ts + configured_duration) > total_duration:
                actual_duration = max(5.0, total_duration - ts)

            clip_dur_ms = seconds_to_ms(actual_duration)

            segments = []
            if self._current_segments:
                segments = [
                    s for s in self._current_segments
                    if seconds_to_ms(s.start) >= ts_ms and seconds_to_ms(s.end) <= ts_ms + clip_dur_ms
                ]

            score = self._timestamp_scores.get(ts, 0.85)
            emotion = self._timestamp_emotions.get(ts, "joy")

            clipper.current_start_offset_ms = ts_ms

            try:
                metadata = clipper.create_clip(
                    source_video=video_path,
                    streamer=None,
                    start_offset=ts,
                    duration=actual_duration,
                    moment_score=score,
                    transcript_segments=segments,
                    emotion=emotion,
                    custom_clip_id=clip_id,
                    layout_type=layout_type,
                )
                if metadata:
                    output_path = Path(metadata.clip_path)
                    try:
                        from processor.hook import HookOverlayRenderer
                        hook_renderer = HookOverlayRenderer()
                        title = self._generate_title(metadata.transcript or "VIRAL MOMENT", emotion)
                        hooked_output = hook_renderer.apply(
                            clip_path=output_path,
                            hook_text=title,
                            watermark_text="@StreamClipper",
                        )
                        if hooked_output:
                            metadata.clip_path = str(hooked_output)
                    except Exception as e:
                        logger.error("Failed to apply hook overlay in VODProcessor for %s: %s", clip_id, e)

                    return metadata
            except Exception as e:
                logger.error("Clip extraction failed for timestamp %.1f: %s", ts, e)
            return None

        parallel_renders = config.vod_settings.parallel_renders
        with ThreadPoolExecutor(max_workers=parallel_renders) as executor:
            futures = {executor.submit(extract_one, i, ts): ts for i, ts in enumerate(timestamps)}
            for future in as_completed(futures):
                if self.cancelled:
                    break
                meta = future.result()
                if meta:
                    with lock:
                        results.append(meta)

        return results

    def _create_fallback_segments(self, duration: float) -> list[TranscriptSegment]:
        """Create evenly-spaced segments when transcription fails."""
        segs = []
        step = min(30, max(5, int(duration))) if duration > 0 else 30
        for t in range(0, max(1, int(duration)), step):
            segs.append(TranscriptSegment(
                start=float(t),
                end=float(min(t + step, duration)),
                text="",
                words=[],
            ))
        return segs

    def _generate_title(self, transcript: str, emotion: str) -> str:
        """Generate a quick title from transcript."""
        words = transcript.split()
        if len(words) <= 5:
            return transcript.strip().upper() or "VIRAL MOMENT"

        fragment = " ".join(words[:8]).strip()
        if len(fragment) > 60:
            fragment = fragment[:57] + "..."

        prefixes = {
            "surprise": "WAIT FOR THIS - ",
            "joy": "BEST MOMENT - ",
            "anger": "THIS IS INSANE - ",
            "neutral": "",
        }
        prefix = prefixes.get(emotion, "")
        return (prefix + fragment).upper()
