"""
StreamClipper — Pipeline
Core pipeline logic that ties detection, clipping, SEO, hook overlay,
thumbnail generation, and upload together. Now backed by SQLite database
and a lightweight task queue.
"""

import time
import logging
import threading
from pathlib import Path
from typing import Optional

import config
from database import Database, ClipStatus
from task_queue import TaskQueue, JobResult
from watcher.monitor import StreamMonitor, StreamStatus
from watcher.capture import StreamCapture
from detector.audio import AudioDetector
from detector.chat import create_chat_monitor
from detector.sentiment import SentimentDetector
from processor.scorer import Scorer, MomentScore
from processor.hook_scorer import HookScorer, HookCandidate
from processor.clipper import Clipper, ClipMetadata
from processor.seo import SEOGenerator
from processor.hook import HookOverlayRenderer
from processor.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader

# Dream Team integration
from dream_team import config as dt_config
from dream_team.director import Director

logger = logging.getLogger("streamclipper.pipeline")


def calculate_dynamic_clip_duration_ms(
    transcript_segments: list,
    start_offset_ms: int = 5000,
    min_duration_ms: int = 30000,
    max_duration_ms: int = 45000,
    default_duration_ms: int = 35000,
) -> int:
    """
    Calculate dynamic clip duration strictly between 30 and 45 seconds (integer ms).
    Snaps to the most natural sentence or phrase boundary within the [30s, 45s] window
    to avoid mid-word truncation and eliminate static 1-minute cuts.
    """
    if not transcript_segments:
        return min(max_duration_ms, max(min_duration_ms, default_duration_ms))

    min_boundary_ms = start_offset_ms + min_duration_ms
    max_boundary_ms = start_offset_ms + max_duration_ms

    viable_ends = []
    punctuated_ends = []

    for seg in transcript_segments:
        end_sec = getattr(seg, "end", None)
        if end_sec is None and isinstance(seg, dict):
            end_sec = seg.get("end", 0.0)
        if end_sec is None:
            continue

        end_ms = int(round(float(end_sec) * 1000.0))
        if min_boundary_ms <= end_ms <= max_boundary_ms:
            viable_ends.append(end_ms)
            text = (getattr(seg, "text", None) or (seg.get("text") if isinstance(seg, dict) else "") or "").strip()
            if text.endswith((".", "!", "?", "...", "—")):
                punctuated_ends.append(end_ms)

    if punctuated_ends:
        chosen_end_ms = punctuated_ends[-1]
    elif viable_ends:
        chosen_end_ms = viable_ends[-1]
    else:
        return min(max_duration_ms, max(min_duration_ms, default_duration_ms))

    calculated_duration_ms = chosen_end_ms - start_offset_ms
    return min(max_duration_ms, max(min_duration_ms, calculated_duration_ms))


class StreamPipeline:
    """
    Manages the full pipeline for a single active stream:
    Capture → Detect → Score → Clip → SEO → Hook → Thumbnail → Queue → Upload
    """

    def __init__(self, status: StreamStatus, db: Database, task_queue: TaskQueue,
                 director: Optional[Director] = None):
        self.status = status
        self.streamer = status.streamer
        self.db = db
        self.task_queue = task_queue
        self.director = director  # Dream Team Director

        # Components
        self.capture = StreamCapture(self.streamer)
        self.audio_detector = AudioDetector()
        self.chat_monitor = create_chat_monitor(self.streamer)
        self.sentiment_detector = SentimentDetector()
        self.scorer = Scorer(on_trigger=self._on_moment_triggered)
        self.hook_scorer = HookScorer(min_hook_score=65)
        self.clipper = Clipper()
        self.seo = SEOGenerator()
        self.hook_renderer = HookOverlayRenderer()
        self.thumbnail_gen = ThumbnailGenerator()
        self.uploader = YouTubeUploader()

        # State
        self._running = False
        self._detection_thread: Optional[threading.Thread] = None
        self._clips_created: int = 0
        self._session_id: Optional[int] = None

    def start(self):
        """Start the full pipeline for this stream."""
        if self._running:
            return

        self._running = True
        logger.info("▶ Starting pipeline for %s", self.streamer.name)

        # Record session in database
        streamer_row = self._ensure_streamer_in_db()
        if streamer_row:
            self._session_id = self.db.start_session(
                streamer_id=streamer_row["id"],
                title=self.status.title,
                game=self.status.game,
            )

        # Start capture
        self.capture.start()

        # Start chat monitor
        if self.chat_monitor:
            self.chat_monitor.start()

        # Start detection loop
        self._detection_thread = threading.Thread(
            target=self._detection_loop, daemon=True
        )
        self._detection_thread.start()

    def stop(self):
        """Stop the pipeline."""
        self._running = False

        self.capture.stop()
        if self.chat_monitor:
            self.chat_monitor.stop()

        # End session in database
        if self._session_id:
            self.db.end_session(self._session_id)

        logger.info(
            "⏹ Pipeline stopped for %s (%d clips created)",
            self.streamer.name,
            self._clips_created,
        )

    def _ensure_streamer_in_db(self) -> Optional[dict]:
        """Ensure the streamer exists in the database."""
        try:
            streamers = self.db.get_streamers()
            for s in streamers:
                if s["name"] == self.streamer.name:
                    return s

            # Add new streamer
            sid = self.db.add_streamer(
                name=self.streamer.name,
                platform=self.streamer.platform,
                channel=self.streamer.channel,
                url=self.streamer.url,
                enabled=self.streamer.enabled,
                auto_approve=getattr(self.streamer, "auto_approve", False),
            )
            return self.db.get_streamer(sid)
        except Exception as e:
            logger.error("Failed to register streamer in DB: %s", e)
            return None

    def _detection_loop(self):
        """
        Periodically analyze the rolling buffer for highlight moments.
        Runs every 10 seconds.
        """
        # Wait for initial buffer to fill
        logger.info("Waiting 30s for buffer to fill...")
        for _ in range(60):
            if not self._running:
                return
            time.sleep(0.5)

        while self._running:
            try:
                self._run_detection_cycle()
            except Exception as e:
                logger.error("Detection cycle error: %s", e)

            # Wait 10 seconds between cycles
            for _ in range(20):
                if not self._running:
                    return
                time.sleep(0.5)

    def _run_detection_cycle(self):
        """Run one detection cycle: analyze recent buffer, score, trigger."""
        # Get recent buffer segments
        buffer_files = self.capture.get_buffer_files(last_n_seconds=30)
        if not buffer_files:
            return

        # Get the most recent segment and extract audio
        latest_segment = buffer_files[-1]
        audio_path = self.capture.extract_audio(latest_segment)
        if not audio_path:
            return

        ref_time = latest_segment.stat().st_mtime

        # Run audio analysis
        audio_events = self.audio_detector.analyze(audio_path, reference_time=ref_time)

        # Run sentiment analysis (transcribe + classify)
        sentiment_events = self.sentiment_detector.analyze(
            audio_path, reference_time=ref_time
        )

        # Get chat events (already being collected in background)
        chat_events = []
        if self.chat_monitor:
            chat_events = self.chat_monitor.recent_events

        # Score the moment
        self.scorer.score_moment(
            audio_events=self.audio_detector.recent_events,
            chat_events=chat_events,
            sentiment_events=self.sentiment_detector.recent_events,
        )

        # Cleanup audio file
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _on_moment_triggered(self, moment: MomentScore):
        """Called when the scorer triggers a clip extraction."""
        if moment.combined_score < 0.65:
            logger.info("🗑️ Moment score %.2f < 0.65 (65%%) viral threshold — dumping immediately", moment.combined_score)
            return

        logger.info("🎬 Acoustic/chat trigger fired (score=%.2f >= 0.65). Extracting buffer for semantic validation...", moment.combined_score)

        try:
            lookback = 60.0  # 60s buffer is captured to allow 30-45s clip + margins
            start_time = time.time() - lookback
            source_video = self.capture.get_concat_file(start_time, lookback)
            if not source_video:
                logger.error("Failed to get source video from buffer")
                return

            # Get transcript for captions and semantic validation
            audio_path = self.capture.extract_audio(source_video)
            transcript_segments = []
            if audio_path:
                try:
                    transcript_segments = self.sentiment_detector.transcribe(audio_path)
                finally:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except Exception:
                        pass

            if not transcript_segments:
                logger.info("🗑️ Semantic gate rejected trigger: audio buffer contains no speech — dumping false trigger")
                return

            # Semantic Gate: Validate transcript using HookScorer (LLM / heuristic)
            candidate = self.hook_scorer.evaluate_moment_buffer(
                transcript_segments=transcript_segments,
                streamer_name=self.streamer.name,
                min_score=65,
            )

            if not candidate or candidate.hook_score < 65:
                score_val = candidate.hook_score if candidate else 0
                logger.info(
                    "🗑️ Semantic gate rejected trigger: hook score %d < 65%% (lacks narrative retention or punchline) — dumping false trigger",
                    score_val
                )
                return

            semantic_score = round(candidate.hook_score / 100.0, 3)
            fused_score = round(0.4 * moment.combined_score + 0.6 * semantic_score, 3)
            logger.info(
                "🔥 Moment validated by semantic gate: acoustic=%.2f, semantic=%.2f, fused=%.2f (reason: %s)",
                moment.combined_score, semantic_score, fused_score, candidate.reasoning
            )

            if fused_score < 0.65:
                logger.info("🗑️ Fused viral score %.2f < 0.65 — dumping immediately", fused_score)
                return

            # Dynamic clip duration strictly between 30 and 45 seconds (integer ms)
            start_offset_ms = candidate.start_ms
            duration_ms = candidate.end_ms - candidate.start_ms
            if duration_ms < 30000:
                duration_ms = 30000
            elif duration_ms > 45000:
                duration_ms = 45000

            duration = float(duration_ms / 1000.0)
            start_offset_sec = float(start_offset_ms / 1000.0)
            logger.info("🎬 Selected dynamic clip: start=%.2fs, duration=%.2fs (%d ms, bounds: 30-45s)", start_offset_sec, duration, duration_ms)

            # Determine primary emotion
            emotion = ""
            if moment.sentiment_events:
                emotion = moment.sentiment_events[0].emotion

            # Filter segments matching clip range
            clip_segments = [
                s for s in transcript_segments
                if (float(getattr(s, "start", 0.0) if not isinstance(s, dict) else s.get("start", 0.0)) * 1000.0) >= start_offset_ms
                and (float(getattr(s, "end", 0.0) if not isinstance(s, dict) else s.get("end", 0.0)) * 1000.0) <= (start_offset_ms + duration_ms)
            ]

            # Fetch latest streamer configuration directly from DB to prevent stale in-memory style overrides
            streamer_db = self.db.get_streamer_by_name(self.streamer.name) or {}
            stream_framing = streamer_db.get("framing_mode") or getattr(self.streamer, "framing_mode", "white_canvas")
            stream_subtitles = streamer_db.get("subtitle_style") or getattr(self.streamer, "subtitle_style", "glacier_glow")
            clip_meta = self.clipper.create_clip(
                source_video=source_video,
                streamer=self.streamer,
                start_offset=start_offset_sec,
                duration=duration,
                moment_score=fused_score,
                transcript_segments=clip_segments if clip_segments else transcript_segments,
                emotion=emotion,
                layout_type=stream_framing,
                subtitle_style=stream_subtitles,
            )

            if not clip_meta or clip_meta.moment_score < 0.65:
                logger.info("🗑️ Clip score < 0.65 — dumping immediately")
                if clip_meta and clip_meta.clip_path:
                    try:
                        Path(clip_meta.clip_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                return

            self._clips_created += 1

            # Only auto-approve if >= 0.65
            auto_approve = clip_meta.moment_score >= 0.65
            logger.info("🎬 Auto-approving clip %s (score=%.2f >= 0.65) for upload", clip_meta.clip_id, clip_meta.moment_score)

            # Save clip to database with archetype and editorial reasoning
            self.db.save_clip(
                clip_id=clip_meta.clip_id,
                streamer_name=self.streamer.name,
                platform=self.streamer.platform,
                clip_path=clip_meta.clip_path,
                duration=clip_meta.duration,
                moment_score=clip_meta.moment_score,
                emotion=emotion,
                transcript=clip_meta.transcript,
                has_captions=clip_meta.has_captions,
                session_id=self._session_id,
                auto_approve=auto_approve,
                archetype=getattr(candidate, "archetype", "Out-of-Context Absurdity"),
                editorial_reasoning=getattr(candidate, "editorial_reasoning", ""),
            )

            # Generate SEO metadata (Ollama or template), preserving candidate title & hook
            try:
                seo_meta = self.seo.generate(
                    transcript=clip_meta.transcript,
                    streamer_name=self.streamer.name,
                    emotion=emotion,
                    platform=self.streamer.platform,
                )
                final_title = candidate.title or seo_meta.title
                final_hook = candidate.hook_text or seo_meta.hook_text
            except Exception as e:
                logger.error("SEO Generator failed in pipeline: %s", e)
                final_title = candidate.title or f"{self.streamer.name} Viral Highlight"
                final_hook = candidate.hook_text or "WAIT FOR IT 💀"
                from processor.seo import SEOMetadata
                seo_meta = SEOMetadata(
                    title=final_title,
                    description=clip_meta.transcript[:200],
                    tags=["shorts", "viral", self.streamer.name.lower()],
                    hook_text=final_hook,
                    thumbnail_prompt="",
                    generated_by="fallback",
                )

            clip_meta.title = final_title
            clip_meta.description = seo_meta.description
            clip_meta.tags = seo_meta.tags
            clip_meta.seo_ready = True

            # Save SEO to database
            self.db.update_clip_seo(
                clip_id=clip_meta.clip_id,
                title=final_title,
                description=seo_meta.description,
                tags=seo_meta.tags,
                hook_text=final_hook,
                seo_method=seo_meta.generated_by,
            )

            logger.info(
                "SEO saved (%s): %s | Hook: '%s'",
                seo_meta.generated_by, final_title, final_hook,
            )

            # ── Dream Team Enhancement ───────────────────────────────
            # Run the clip through all Dream Team agents for AI-powered
            # viral scoring, SEO refinement, moderation, and visuals.
            if self.director and self.director.is_ready:
                try:
                    dt_clip_data = {
                        "clip_id": clip_meta.clip_id,
                        "clip_path": str(clip_meta.clip_path),
                        "transcript": clip_meta.transcript,
                        "emotion": emotion,
                        "streamer_name": self.streamer.name,
                        "chat_intensity": getattr(moment, "chat_score", 0.0),
                        "title": seo_meta.title,
                        "description": seo_meta.description,
                        "tags": seo_meta.tags,
                    }
                    dt_result = self.director.process_clip(dt_clip_data)

                    # Apply enhanced SEO if available
                    if dt_result.get("seo_enhanced"):
                        seo_meta.title = dt_result.get("title", seo_meta.title)
                        seo_meta.description = dt_result.get("description", seo_meta.description)
                        seo_meta.tags = dt_result.get("tags", seo_meta.tags)
                        # Update DB with enhanced SEO
                        self.db.update_clip_seo(
                            clip_id=clip_meta.clip_id,
                            title=seo_meta.title,
                            description=seo_meta.description,
                            tags=seo_meta.tags,
                            hook_text=dt_result.get("hook_text", seo_meta.hook_text),
                            seo_method=f"{seo_meta.generated_by}+dreamteam",
                        )

                    # Check moderation & virality result
                    if dt_result.get("viral_score", clip_meta.moment_score) < 0.65:
                        logger.info("🛡️ Dream Team viral score %.2f < 0.65 — dumping clip %s immediately", dt_result.get("viral_score", 0.0), clip_meta.clip_id)
                        self.db.delete_clip(clip_meta.clip_id)
                        return

                    mod_action = dt_result.get("moderation_action", "approve")
                    if mod_action == "reject":
                        auto_approve = False
                        logger.warning(
                            "🛡️ Sentinel REJECTED clip %s — flagged for review",
                            clip_meta.clip_id,
                        )
                    elif mod_action == "flag":
                        auto_approve = False
                        logger.info(
                            "🛡️ Sentinel FLAGGED clip %s — needs manual review",
                            clip_meta.clip_id,
                        )

                    logger.info(
                        "🤖 Dream Team processed clip %s — viral=%.2f, mod=%s",
                        clip_meta.clip_id,
                        dt_result.get("viral_score", 0.0),
                        mod_action,
                    )
                except Exception as dt_exc:
                    logger.warning("Dream Team processing failed (non-fatal): %s", dt_exc)

            # Apply hook, watermark, and outro overlay (layout-aware)
            streamer_db = self.db.get_streamer_by_name(self.streamer.name) or {}
            effective_framing = streamer_db.get("framing_mode") or getattr(self.streamer, "framing_mode", "white_canvas")
            effective_plat = streamer_db.get("platform") or getattr(self.streamer, "platform", "twitch")

            clip_path = Path(clip_meta.clip_path)
            hook_result = self.hook_renderer.apply(
                clip_path=clip_path,
                hook_text=seo_meta.hook_text,
                watermark_text=f"@{self.streamer.name}",
                layout_type=effective_framing,
                streamer_name=self.streamer.name,
                platform=effective_plat,
            )
            if hook_result:
                self.db.update_clip_hook(clip_meta.clip_id, has_hook=True)

            # Generate thumbnail
            thumb_path = self.thumbnail_gen.generate(
                clip_path=clip_path,
                title_text=seo_meta.thumbnail_prompt,
                streamer_name=self.streamer.name,
            )
            if thumb_path:
                self.db.update_clip_thumbnail(clip_meta.clip_id, str(thumb_path))

            # If auto-approved, submit upload job to queue
            if auto_approve:
                delay_sec = 0.0
                try:
                    from processor.scheduler import calculate_next_upload_delay
                    delay_sec = calculate_next_upload_delay(self.db)
                except Exception as exc:
                    logger.warning("Failed to calculate upload schedule delay: %s", exc)

                self.task_queue.submit(
                    job_type="upload",
                    clip_id=clip_meta.clip_id,
                    payload={
                        "clip_path": str(clip_path),
                        "title": seo_meta.title,
                        "description": seo_meta.description,
                        "tags": seo_meta.tags,
                        "thumbnail_path": str(thumb_path) if thumb_path else "",
                    },
                    priority=3,
                    delay_seconds=delay_sec,
                )
                logger.info(
                    "📤 Auto-approved clip queued for upload: %s (scheduled delay: %.1fs)",
                    clip_meta.clip_id,
                    delay_sec
                )
            else:
                logger.info(
                    "⏸ Clip awaiting review: %s (approve via dashboard)",
                    clip_meta.clip_id,
                )

            # Cleanup source concat file
            try:
                source_video.unlink(missing_ok=True)
                if audio_path:
                    audio_path.unlink(missing_ok=True)
            except Exception:
                pass

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)


class PipelineManager:
    """
    Manages multiple StreamPipelines and coordinates with the monitor,
    database, and task queue.
    """

    def __init__(self, db: Database, task_queue: TaskQueue):
        self.db = db
        self.task_queue = task_queue
        self._pipelines: dict[str, StreamPipeline] = {}
        self._monitor: Optional[StreamMonitor] = None
        self._lock = threading.Lock()
        self.is_active = False

        # Dream Team — AI agent orchestrator
        self._director: Optional[Director] = None
        if dt_config.DREAM_TEAM_ENABLED:
            try:
                self._director = Director()
                self._director.initialise()
                logger.info(
                    "🤖 Dream Team active — %d agents: %s",
                    len(self._director.active_agents),
                    self._director.active_agents,
                )
            except Exception as exc:
                logger.warning("Dream Team failed to initialise (non-fatal): %s", exc)
                self._director = None

        # Register queue handlers
        self._uploader = YouTubeUploader()
        self.task_queue.register("upload", self._handle_upload_job)
        self.task_queue.register("vod_process", self._handle_vod_job)

    @property
    def monitor(self) -> Optional[StreamMonitor]:
        """Return the active StreamMonitor instance."""
        return self._monitor

    def _handle_vod_job(self, job: dict) -> JobResult:
        """Handle VOD processing job."""
        from processor.vod import VODProcessor
        payload = job.get("payload", {})
        url = payload.get("url")
        layout_type = payload.get("layout_type", "white_canvas")
        subtitle_style = payload.get("subtitle_style", "hormozi")
        job_id = str(job.get("id", ""))
        if not url:
            return JobResult(success=False, error="No URL provided")
            
        processor = VODProcessor(self.db, self.task_queue)
        success = processor.process_url(url, job_id, layout_type=layout_type, subtitle_style=subtitle_style)
        if success:
            return JobResult(success=True, result="VOD processed successfully")
        return JobResult(success=False, error="VOD processing failed")

    def _handle_upload_job(self, job: dict) -> JobResult:
        """Handle an upload job from the queue with strict deduplication and idempotency safeguards."""
        payload = job.get("payload", {})
        clip_id = job.get("clip_id", "")

        clip_path = Path(payload.get("clip_path", ""))
        title = payload.get("title", "")
        description = payload.get("description", "")
        tags = payload.get("tags", [])
        thumbnail_path = payload.get("thumbnail_path", "")

        # 1. Check if clip was deleted from database
        clip = self.db.get_clip(clip_id)
        if not clip:
            logger.warning("Upload aborted: clip %s was deleted or does not exist in DB", clip_id)
            return JobResult(success=False, error=f"Clip {clip_id} not found in database (deleted)")

        # 2. Check if clip has already been uploaded (idempotency safeguard)
        if clip.get("status") == ClipStatus.UPLOADED:
            logger.info("Clip %s already marked as uploaded in database — skipping duplicate upload", clip_id)
            return JobResult(success=True, result="Clip already uploaded")

        with self.db._conn() as conn:
            existing_upload = conn.execute(
                "SELECT video_id, video_url FROM uploads WHERE clip_id = ? AND success = 1 AND video_id != ''",
                (clip_id,),
            ).fetchone()
            if existing_upload:
                logger.info(
                    "Clip %s already has recorded successful upload (ID: %s, URL: %s) — skipping duplicate upload",
                    clip_id, existing_upload[0], existing_upload[1],
                )
                self.db.update_clip_status(clip_id, ClipStatus.UPLOADED)
                return JobResult(success=True, result=f"Already uploaded: {existing_upload[1]}")

        # 3. Check viral threshold — if less than 65%, dump immediately
        if clip.get("moment_score", 0.0) < 0.65:
            logger.warning("Clip %s score %.2f is below 65%% threshold — aborting upload and dumping clip", clip_id, clip.get("moment_score", 0.0))
            self.db.delete_clip(clip_id)
            return JobResult(success=False, error="Clip moment score below 65% viral threshold")

        if not clip_path.exists():
            return JobResult(success=False, error=f"Clip file not found: {clip_path}")

        # Update clip status
        self.db.update_clip_status(clip_id, ClipStatus.UPLOADING)

        # Upload with automatic multi-account cascade (Account 1 -> Account 2 -> Account 3)
        upload_result = self._uploader.upload(
            video_path=clip_path,
            title=title,
            description=description,
            tags=tags,
        )

        account_id = getattr(upload_result, "account_id", "account1")

        # Set thumbnail if upload succeeded and thumbnail exists using the account that uploaded it
        if upload_result.success and thumbnail_path and Path(thumbnail_path).exists():
            try:
                self._uploader.set_thumbnail(
                    upload_result.video_id,
                    Path(thumbnail_path),
                    account_id=account_id,
                )
            except Exception as e:
                logger.warning("Thumbnail upload failed: %s", e)

        # Record in database with account attribution
        try:
            self.db.save_upload(
                clip_id=clip_id,
                success=upload_result.success,
                video_id=upload_result.video_id,
                video_url=upload_result.video_url,
                error=upload_result.error,
                account_id=account_id,
            )
        except Exception as e:
            logger.error("Failed to record upload in database: %s", e)
            if upload_result.success:
                self.db.update_clip_status(clip_id, ClipStatus.UPLOADED)
            else:
                self.db.update_clip_status(clip_id, ClipStatus.FAILED)

        if upload_result.success:
            return JobResult(
                success=True,
                result=f"Uploaded to {account_id}: {upload_result.video_url}",
            )
        else:
            return JobResult(success=False, error=upload_result.error)

    def start(self, streamers: list[config.StreamerConfig], poll_interval: int = 60):
        """Start monitoring and auto-pipeline creation."""
        # Start task queue
        self.task_queue.start()

        self._monitor = StreamMonitor(
            streamers=streamers,
            on_live=self._on_streamer_live,
            on_offline=self._on_streamer_offline,
            poll_interval=poll_interval,
        )
        self._monitor.start()
        self.is_active = True
        logger.info("Pipeline manager started")

    def stop(self):
        """Stop all pipelines, queue, and the monitor."""
        if self._monitor:
            self._monitor.stop()

        self.task_queue.stop()

        with self._lock:
            for key, pipeline in self._pipelines.items():
                pipeline.stop()
            self._pipelines.clear()

        # Shutdown Dream Team
        if self._director:
            self._director.shutdown()

        self.is_active = False
        logger.info("Pipeline manager stopped")

    def _on_streamer_live(self, status: StreamStatus):
        """Called when a streamer goes live — start a pipeline."""
        key = f"{status.streamer.platform}:{status.streamer.channel}"

        with self._lock:
            if key in self._pipelines:
                logger.warning("Pipeline already running for %s", key)
                return

            pipeline = StreamPipeline(
                status, self.db, self.task_queue, director=self._director
            )
            self._pipelines[key] = pipeline
            pipeline.start()

    def _on_streamer_offline(self, status: StreamStatus):
        """Called when a streamer goes offline — stop the pipeline."""
        key = f"{status.streamer.platform}:{status.streamer.channel}"

        with self._lock:
            pipeline = self._pipelines.pop(key, None)
            if pipeline:
                pipeline.stop()

    def approve_clip(self, clip_id: str) -> bool:
        """Approve a clip for upload and submit to queue."""
        clip = self.db.get_clip(clip_id)
        if not clip:
            return False

        # Strict rule: already uploaded clips can NEVER be re-approved or re-uploaded
        if clip.get("status") == ClipStatus.UPLOADED:
            logger.warning("Clip %s is already uploaded — re-upload forbidden", clip_id)
            return False

        # Idempotency check
        if clip.get("status") in [ClipStatus.APPROVED, ClipStatus.UPLOADING]:
            logger.info("Clip %s is already in status %s — skipping redundant approval", clip_id, clip["status"])
            return True

        if not self.db.update_clip_status(clip_id, ClipStatus.APPROVED):
            return False

        # Calculate scheduling delay
        delay_sec = 0.0
        try:
            from processor.scheduler import calculate_next_upload_delay
            delay_sec = calculate_next_upload_delay(self.db)
        except Exception as exc:
            logger.warning("Failed to calculate upload schedule delay: %s", exc)

        # Submit upload job
        self.task_queue.submit(
            job_type="upload",
            clip_id=clip_id,
            payload={
                "clip_path": clip["clip_path"],
                "title": clip["title"],
                "description": clip["description"],
                "tags": clip["tags"],
                "thumbnail_path": clip.get("thumbnail_path", ""),
            },
            priority=3,
            delay_seconds=delay_sec,
        )
        logger.info("Clip %s queued for upload (scheduled delay: %.1fs)", clip_id, delay_sec)
        return True

    def reject_clip(self, clip_id: str) -> bool:
        """Reject a clip — delete it from DB and disk."""
        return self.db.delete_clip(clip_id)

    @property
    def active_pipelines(self) -> dict[str, StreamPipeline]:
        return dict(self._pipelines)

    @property
    def monitor(self) -> Optional[StreamMonitor]:
        return self._monitor
