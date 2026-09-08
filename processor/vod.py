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


from processor.captions_engine import CaptionsEngine, SubtitleStyle, normalize_subtitle_style

class VODClipper(Clipper):
    """Custom Clipper subclass for VOD processing with multi-style animated subtitle engine."""

    def __init__(self, settings=None, subtitle_style: str = "hormozi"):
        super().__init__(settings)
        self.current_start_offset_ms: int = 0
        self.subtitle_style = normalize_subtitle_style(subtitle_style)
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

    @staticmethod
    def _detect_streamer_and_platform(url: str) -> Tuple[str, str]:
        """Detect streamer channel name and broadcast platform from URL."""
        clean_url = str(url or "").strip()
        lower_url = clean_url.lower()
        if "kick.com/" in lower_url:
            parts = lower_url.split("kick.com/")[1].split("/")[0].split("?")[0]
            name = parts.strip()
            return (name if name else "Streamer"), "kick"
        if "twitch.tv/" in lower_url:
            parts = lower_url.split("twitch.tv/")[1].split("/")[0].split("?")[0]
            name = parts.strip()
            return (name if name else "Streamer"), "twitch"
        if "youtube.com/" in lower_url or "youtu.be/" in lower_url:
            if "@" in lower_url:
                parts = lower_url.split("@")[1].split("/")[0].split("?")[0]
                name = parts.strip()
                return (name if name else "Creator"), "youtube"
            return "Creator", "youtube"
        if "tiktok.com/" in lower_url:
            if "@" in lower_url:
                parts = lower_url.split("@")[1].split("/")[0].split("?")[0]
                name = parts.strip()
                return (name if name else "Creator"), "tiktok"
            return "Creator", "tiktok"
        return "Streamer", "custom"

    def process_url(self, url: str, job_id: str = "", layout_type: str = "gamer", subtitle_style: str = "hormozi") -> bool:
        """Process URL to extract viral clips."""
        if job_id:
            with ACTIVE_PROCESSORS_LOCK:
                ACTIVE_PROCESSORS[job_id] = self

        self._current_vid = str(uuid.uuid4())[:8]
        detected_streamer, detected_platform = self._detect_streamer_and_platform(url)

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
            progress(55, "Analyzing transcripts with HookScorer (virality >= 65%)...")
            candidates = self._find_viral_moments(self._current_segments, duration=duration)
            if not candidates:
                logger.info("No moments in VOD reached >= 0.65 viral score. Dumping all sub-65% content.")
                progress(100, "Done! No clips met the >= 65% viral threshold (sub-65% moments dumped).")
                return True

            logger.info("Found %d viral candidate moments (>= 65%% score)", len(candidates))

            # ── 4. EXTRACT CLIPS (Parallel renders) ─────────────────────────────
            progress(65, f"Extracting and rendering {len(candidates)} clips in parallel...")
            clips = self._cut_clips_parallel(
                video_path,
                candidates,
                layout_type,
                total_duration=duration,
                subtitle_style=subtitle_style,
                streamer_name=detected_streamer,
                platform=detected_platform,
            )

            if not clips:
                progress(100, "No clips met the >= 65% viral threshold (all dumped).")
                return True

            # ── 5. SAVE AND ORCHESTRATE SEO / UPLOADS ───────────────────────────
            success_count = 0
            for clip in clips:
                if clip.moment_score < 0.65:
                    logger.info("🗑️ VOD clip %s score %.2f < 0.65 — dumping immediately", clip.clip_id, clip.moment_score)
                    try:
                        safe_unlink(Path(clip.clip_path))
                    except Exception:
                        pass
                    continue

                auto_approve = clip.moment_score >= 0.65
                saved_id = self.db.save_clip(
                    clip_id=clip.clip_id,
                    streamer_name=detected_streamer,
                    platform=detected_platform,
                    clip_path=clip.clip_path,
                    duration=clip.duration,
                    moment_score=clip.moment_score,
                    emotion=clip.emotion,
                    transcript=clip.transcript[:500],
                    has_captions=clip.has_captions,
                    auto_approve=auto_approve,
                )
                if not saved_id:
                    logger.info("Clip %s refused by database — dumping immediately", clip.clip_id)
                    try:
                        safe_unlink(Path(clip.clip_path))
                    except Exception:
                        pass
                    continue

                try:
                    from processor.seo import SEOGenerator
                    seo_gen = SEOGenerator()
                    seo_meta = seo_gen.generate(
                        transcript=clip.transcript,
                        streamer_name=detected_streamer,
                        emotion=clip.emotion,
                        platform=detected_platform,
                    )
                    final_title = clip.title or seo_meta.title
                    final_hook = seo_meta.hook_text or final_title
                except Exception as e:
                    logger.error("SEO Generator failed: %s", e)
                    from processor.seo import SEOMetadata
                    final_title = clip.title or self._generate_title(clip.transcript, clip.emotion)
                    final_hook = final_title
                    seo_meta = SEOMetadata(
                        title=final_title,
                        description=clip.transcript[:200],
                        tags=["shorts", "viral", "clips", clip.emotion],
                        hook_text=final_hook,
                        thumbnail_prompt="",
                        generated_by="template",
                    )

                self.db.update_clip_seo(
                    clip_id=clip.clip_id,
                    title=final_title,
                    description=seo_meta.description,
                    tags=seo_meta.tags,
                    hook_text=final_hook,
                    seo_method=seo_meta.generated_by,
                )

                try:
                    from processor.hook import HookOverlayRenderer
                    hook_renderer = HookOverlayRenderer()
                    hook_res = hook_renderer.apply(
                        clip_path=Path(clip.clip_path),
                        hook_text=final_hook,
                        watermark_text=f"@{detected_streamer}",
                        layout_type=layout_type,
                        streamer_name=detected_streamer,
                        platform=detected_platform,
                    )
                    if hook_res:
                        self.db.update_clip_hook(clip.clip_id, has_hook=True)
                except Exception as hook_exc:
                    logger.warning("VOD hook overlay failed (non-fatal): %s", hook_exc)

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
                    delay_sec = 0.0
                    try:
                        from processor.scheduler import calculate_next_upload_delay
                        delay_sec = calculate_next_upload_delay(self.db)
                    except Exception as exc:
                        logger.warning("Failed to calculate upload schedule delay: %s", exc)

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
                        delay_seconds=delay_sec,
                    )
                    logger.info("🔥 High viral score (%.2f) — VOD clip %s queued for upload (delay: %.1fs)", clip.moment_score, clip.clip_id, delay_sec)

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
        """Download VOD with yt-dlp and fallback to streamlink with continuous progress telemetry."""
        import re
        test_path = config.TEMP_MEDIA_DIR / f"vod_{self._current_vid}" / "video.mp4"
        if test_path.exists():
            logger.info("Found pre-existing mock VOD video at %s", test_path)
            return test_path, ""

        timestamp = int(time.time())
        output_template = str(config.RAW_DIR / f"vod_{timestamp}.%(ext)s")
        target_mp4 = config.RAW_DIR / f"vod_{timestamp}.mp4"
        res = config.vod_settings.download_resolution

        def parse_line(line: str):
            if not progress_callback:
                return
            clean = line.strip()
            if not clean:
                return

            # 1. Custom yt-dlp progress template
            tpl_match = re.search(r"download-progress:\s*([0-9\.]+)%", clean)
            if tpl_match:
                dl_pct = float(tpl_match.group(1))
                mapped = 5 + int((dl_pct / 100.0) * 20.0)
                progress_callback(mapped, f"Downloading video stream ({dl_pct:.1f}%)...")
                return

            # 2. Standard yt-dlp percentage (supports 100%, 45.2%, etc.)
            pct_match = re.search(r"\[download\]\s+([0-9\.]+)%", clean)
            if pct_match:
                dl_pct = float(pct_match.group(1))
                mapped = 5 + int((dl_pct / 100.0) * 20.0)
                progress_callback(mapped, f"Downloading video stream ({dl_pct:.1f}%)...")
                return

            # 3. Informative milestone updates
            if "[youtube]" in clean and "Extracting" in clean:
                progress_callback(6, "Connecting to YouTube media servers...")
            elif "[youtube]" in clean and "Downloading" in clean:
                progress_callback(8, "Fetching player manifest and metadata...")
            elif "[info]" in clean and "Downloading" in clean:
                progress_callback(10, "Resolving video and audio tracks...")
            elif "Destination:" in clean:
                progress_callback(12, "Writing video chunks to disk...")
            elif "frame=" in clean:
                progress_callback(22, "Muxing video & audio streams...")

        # 1. Try yt-dlp
        cmd = [
            "yt-dlp",
            "--newline",
            "--no-colors",
            "--no-playlist",
            "--no-check-certificate",
            "--extractor-args", "youtube:player_client=default,web,android",
            "--concurrent-fragments", "4",
            "--buffer-size", "16K",
            "--progress-template", "download-progress:%(progress._percent_str)s:%(progress._eta_str)s:%(progress._speed_str)s",
            "--merge-output-format", "mp4",
            "-f", f"bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={res}]+bestaudio/best[height<={res}]/best",
            "-o", output_template,
            url,
        ]

        try:
            logger.info("Running yt-dlp download: %s", " ".join(cmd))
            r = self.run_subprocess(cmd, timeout=900, line_callback=parse_line)

            if target_mp4.exists() and target_mp4.stat().st_size > 0:
                progress_callback(25, "Download and stream ingest complete!")
                return target_mp4, ""

            pattern = f"vod_{timestamp}*"
            matches = [p for p in config.RAW_DIR.glob(pattern) if p.is_file() and not p.name.endswith(".part")]
            if matches:
                chosen = max(matches, key=lambda p: p.stat().st_size)
                if chosen.stat().st_size > 0:
                    logger.info("Found downloaded video via file pattern match: %s", chosen)
                    progress_callback(25, "Download and stream ingest complete!")
                    return chosen, ""

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
                    "--output", str(target_mp4),
                    url,
                    "best",
                    "--hls-duration", "120",
                ]
                sr = self.run_subprocess(streamlink_cmd, timeout=180)
                if target_mp4.exists() and target_mp4.stat().st_size > 0:
                    progress_callback(25, "Streamlink ingest complete!")
                    return target_mp4, ""
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

    def _find_viral_moments(self, transcript: list[TranscriptSegment], duration: float = 0.0) -> list:
        """Score transcript with HookScorer (LLM + semantic virality engine) and return top candidates."""
        if not transcript:
            return []

        from processor.hook_scorer import HookScorer, HookCandidate
        hook_scorer = HookScorer(min_hook_score=65)
        candidates = hook_scorer.score_transcript(
            transcript_segments=transcript,
            streamer_name="VOD_Clipper",
            window_sec=getattr(config.vod_settings, "clip_duration", 35) or 35,
            step_sec=15
        )

        # Strictly enforce >= 65% viral threshold
        candidates = [c for c in candidates if c.hook_score >= 65]
        max_clips = config.vod_settings.max_clips
        selected = candidates[:max_clips]

        if not selected:
            logger.info("No moments in VOD achieved >= 0.65 viral score — zero clips will be created")
            return []

        return selected

    def _cut_clips_parallel(
        self,
        video_path: Path,
        items: list,
        layout_type: str,
        total_duration: float = 0.0,
        subtitle_style: str = "hormozi",
        streamer_name: str = "Streamer",
        platform: str = "custom",
    ) -> list[ClipMetadata]:
        """Cut clips in parallel using ThreadPoolExecutor and Clipper with millisecond offsets."""
        clipper = VODClipper(subtitle_style=subtitle_style)
        results: list[ClipMetadata] = []
        results_lock = threading.Lock()
        configured_duration = max(30, min(45, int(config.vod_settings.clip_duration)))

        def extract_one(i: int, item: Any) -> Optional[ClipMetadata]:
            if self.cancelled:
                return None
            clip_id = f"vod_{self._current_vid}_{i}"

            from processor.hook_scorer import HookCandidate
            if isinstance(item, HookCandidate):
                ts = float(item.start_ms / 1000.0)
                ts_ms = item.start_ms
                actual_duration = item.duration_sec
                score = round(item.hook_score / 100.0, 3)
                hook_title = item.title
                hook_text = item.hook_text
                emotion = "joy"
            else:
                ts = float(item)
                ts_ms = seconds_to_ms(ts)
                target_ms = seconds_to_ms(configured_duration)
                min_ms = 30000
                max_ms = 45000
                chosen_dur_ms = target_ms
                if self._current_segments:
                    valid_ends = [
                        seconds_to_ms(s.end) - ts_ms
                        for s in self._current_segments
                        if min_ms <= (seconds_to_ms(s.end) - ts_ms) <= max_ms
                    ]
                    if valid_ends:
                        chosen_dur_ms = valid_ends[-1]
                actual_duration = float(chosen_dur_ms / 1000.0)
                score = self._timestamp_scores.get(ts, 0.85)
                emotion = self._timestamp_emotions.get(ts, "joy")
                hook_title = self._generate_title("", emotion)
                hook_text = "WAIT FOR IT 💀"

            # Enforce strictly 30-45s clip duration
            actual_duration = max(30.0, min(45.0, actual_duration))

            # Adjust duration if video is shorter than configured duration
            if total_duration > 0 and (ts + actual_duration) > total_duration:
                remaining = total_duration - ts
                actual_duration = max(30.0, remaining) if remaining >= 30.0 else max(5.0, remaining)

            clip_dur_ms = seconds_to_ms(actual_duration)

            segments = []
            if self._current_segments:
                segments = [
                    s for s in self._current_segments
                    if seconds_to_ms(s.start) >= ts_ms and seconds_to_ms(s.end) <= ts_ms + clip_dur_ms
                ]

            clipper.current_start_offset_ms = ts_ms

            try:
                from config import StreamerConfig
                s_cfg = StreamerConfig(name=streamer_name, platform=platform, channel=streamer_name, url="")
                metadata = clipper.create_clip(
                    source_video=video_path,
                    streamer=s_cfg,
                    start_offset=ts,
                    duration=actual_duration,
                    moment_score=score,
                    transcript_segments=segments,
                    emotion=emotion,
                    custom_clip_id=clip_id,
                    layout_type=layout_type,
                    subtitle_style=subtitle_style,
                )
                if metadata:
                    metadata.title = hook_title
                    output_path = Path(metadata.clip_path)
                    try:
                        from processor.hook import HookOverlayRenderer
                        hook_renderer = HookOverlayRenderer()
                        hooked_output = hook_renderer.apply(
                            clip_path=output_path,
                            hook_text=hook_text or hook_title,
                            watermark_text=f"@{streamer_name}",
                            layout_type=layout_type,
                            streamer_name=streamer_name,
                            platform=platform,
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
            futures = {executor.submit(extract_one, i, item): item for i, item in enumerate(items)}
            for future in as_completed(futures):
                if self.cancelled:
                    break
                meta = future.result()
                if meta:
                    with results_lock:
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
        """Generate a high-CTR, modern Gen-Z title directly from speech context."""
        words = [w for w in transcript.strip().split() if w]
        snippet = " ".join(words[:6]).strip('",.?!')
        
        if len(words) >= 3 and len(snippet) > 6:
            snip_lower = snippet.lower()
            if any(k in snip_lower for k in ["i ", "my ", "me ", "we "]):
                return f"bro really said \"{snip_lower}\" 💀"[:75]
            elif emotion in ("surprise", "fear"):
                return f"ain't no way {snip_lower} 😭"[:75]
            elif emotion in ("anger", "rage"):
                return f"nah he actually lost it over this 💀"[:75]
            elif emotion in ("joy", "win"):
                return f"bro thought he was him 👑"[:75]
            else:
                return f"wait for it... \"{snip_lower}\" 💀"[:75]

        fallbacks = [
            "bro thought he was him 💀",
            "ain't no way he did this 😭",
            "nah chat is cooking him rn 💀",
            "bro sold the bag so fast 😭",
            "he was NOT ready for this 💀",
            "wait till the ending bro i'm crying 😭",
        ]
        import random
        return random.choice(fallbacks)
