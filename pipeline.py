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
from processor.clipper import Clipper, ClipMetadata
from processor.seo import SEOGenerator
from processor.hook import HookOverlayRenderer
from processor.thumbnail import ThumbnailGenerator
from uploader.youtube import YouTubeUploader

logger = logging.getLogger("streamclipper.pipeline")


class StreamPipeline:
    """
    Manages the full pipeline for a single active stream:
    Capture → Detect → Score → Clip → SEO → Hook → Thumbnail → Queue → Upload
    """

    def __init__(self, status: StreamStatus, db: Database, task_queue: TaskQueue):
        self.status = status
        self.streamer = status.streamer
        self.db = db
        self.task_queue = task_queue

        # Components
        self.capture = StreamCapture(self.streamer)
        self.audio_detector = AudioDetector()
        self.chat_monitor = create_chat_monitor(self.streamer)
        self.sentiment_detector = SentimentDetector()
        self.scorer = Scorer(on_trigger=self._on_moment_triggered)
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
        logger.info("🎬 Processing highlight moment (score=%.2f)", moment.combined_score)

        try:
            # Determine how far back to look
            duration = config.clip_settings.default_duration
            lookback = duration + 10  # Extra buffer

            # Get concatenated video from buffer
            start_time = time.time() - lookback
            source_video = self.capture.get_concat_file(start_time, lookback)
            if not source_video:
                logger.error("Failed to get source video from buffer")
                return

            # Get transcript for captions
            audio_path = self.capture.extract_audio(source_video)
            transcript_segments = []
            if audio_path:
                transcript_segments = self.sentiment_detector.transcribe(audio_path)

            # Determine primary emotion
            emotion = ""
            if moment.sentiment_events:
                emotion = moment.sentiment_events[0].emotion

            # Create the clip (crop + caption)
            clip_meta = self.clipper.create_clip(
                source_video=source_video,
                streamer=self.streamer,
                start_offset=5.0,  # Skip first 5s of buffer padding
                duration=duration,
                moment_score=moment.combined_score,
                transcript_segments=transcript_segments,
                emotion=emotion,
            )

            if not clip_meta:
                logger.error("Clip creation failed")
                return

            self._clips_created += 1

            # Automatically approve and upload every detected highlight clip
            auto_approve = True
            logger.info("🎬 Auto-approving clip %s for immediate upload", clip_meta.clip_id)

            # Save clip to database
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
            )

            # Generate SEO metadata (Ollama or template)
            seo_meta = self.seo.generate(
                transcript=clip_meta.transcript,
                streamer_name=self.streamer.name,
                emotion=emotion,
                platform=self.streamer.platform,
            )

            clip_meta.title = seo_meta.title
            clip_meta.description = seo_meta.description
            clip_meta.tags = seo_meta.tags
            clip_meta.seo_ready = True

            # Save SEO to database
            self.db.update_clip_seo(
                clip_id=clip_meta.clip_id,
                title=seo_meta.title,
                description=seo_meta.description,
                tags=seo_meta.tags,
                hook_text=seo_meta.hook_text,
                seo_method=seo_meta.generated_by,
            )

            logger.info(
                "SEO generated (%s): %s | Hook: '%s'",
                seo_meta.generated_by, seo_meta.title, seo_meta.hook_text,
            )

            # Apply hook, watermark, and outro overlay
            clip_path = Path(clip_meta.clip_path)
            hook_result = self.hook_renderer.apply(
                clip_path,
                seo_meta.hook_text,
                watermark_text=f"@{self.streamer.name}",
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
                )
                logger.info("📤 Auto-approved clip queued for upload: %s", clip_meta.clip_id)
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

        # Register queue handlers
        self._uploader = YouTubeUploader()
        self.task_queue.register("upload", self._handle_upload_job)
        self.task_queue.register("vod_process", self._handle_vod_job)

    def _handle_vod_job(self, job: dict) -> JobResult:
        """Handle VOD processing job."""
        from processor.vod import VODProcessor
        url = job.get("payload", {}).get("url")
        layout_type = job.get("payload", {}).get("layout_type", "gamer")
        job_id = str(job.get("id", ""))
        if not url:
            return JobResult(success=False, error="No URL provided")
            
        processor = VODProcessor(self.db, self.task_queue)
        success = processor.process_url(url, job_id, layout_type=layout_type)
        if success:
            return JobResult(success=True, result="VOD processed successfully")
        return JobResult(success=False, error="VOD processing failed")

    def _handle_upload_job(self, job: dict) -> JobResult:
        """Handle an upload job from the queue."""
        payload = job.get("payload", {})
        clip_id = job.get("clip_id", "")

        clip_path = Path(payload.get("clip_path", ""))
        title = payload.get("title", "")
        description = payload.get("description", "")
        tags = payload.get("tags", [])
        thumbnail_path = payload.get("thumbnail_path", "")

        if not clip_path.exists():
            return JobResult(success=False, error=f"Clip file not found: {clip_path}")

        # Check daily quota
        uploads_today = self.db.count_uploads_today()
        if uploads_today >= config.UPLOAD_MAX_PER_DAY:
            # Reschedule for later
            self.task_queue.submit(
                job_type="upload",
                clip_id=clip_id,
                payload=payload,
                priority=5,
                delay_seconds=3600,  # Try again in 1 hour
            )
            return JobResult(
                success=False,
                error=f"Daily quota reached ({uploads_today}/{config.UPLOAD_MAX_PER_DAY}), rescheduled",
            )

        # Update clip status
        self.db.update_clip_status(clip_id, ClipStatus.UPLOADING)

        # Upload
        upload_result = self._uploader.upload(
            video_path=clip_path,
            title=title,
            description=description,
            tags=tags,
        )

        # Set thumbnail if upload succeeded and thumbnail exists
        if upload_result.success and thumbnail_path and Path(thumbnail_path).exists():
            try:
                self._uploader.set_thumbnail(
                    upload_result.video_id, Path(thumbnail_path)
                )
            except Exception as e:
                logger.warning("Thumbnail upload failed: %s", e)

        # Record in database
        self.db.save_upload(
            clip_id=clip_id,
            success=upload_result.success,
            video_id=upload_result.video_id,
            video_url=upload_result.video_url,
            error=upload_result.error,
        )

        if upload_result.success:
            return JobResult(
                success=True,
                result=f"Uploaded: {upload_result.video_url}",
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

        self.is_active = False
        logger.info("Pipeline manager stopped")

    def _on_streamer_live(self, status: StreamStatus):
        """Called when a streamer goes live — start a pipeline."""
        key = f"{status.streamer.platform}:{status.streamer.channel}"

        with self._lock:
            if key in self._pipelines:
                logger.warning("Pipeline already running for %s", key)
                return

            pipeline = StreamPipeline(status, self.db, self.task_queue)
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

        # Idempotency check
        if clip.get("status") in [ClipStatus.APPROVED, ClipStatus.UPLOADING, ClipStatus.UPLOADED]:
            logger.info("Clip %s is already in status %s — skipping redundant approval", clip_id, clip["status"])
            return True

        if not self.db.update_clip_status(clip_id, ClipStatus.APPROVED):
            return False

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
        )
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
