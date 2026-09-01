"""
StreamClipper — Task Queue
Lightweight SQLite-backed async job queue with retry logic, scheduling, and cancellation.
Thread-safe, non-blocking execution with automatic resource reclamation.
"""

import time
import logging
import threading
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass

from database import Database, JobStatus
from processor.subprocess_utils import free_vram

logger = logging.getLogger("streamclipper.queue")


@dataclass
class JobResult:
    success: bool
    result: str = ""
    error: str = ""


class TaskQueue:
    """
    Lightweight task queue backed by SQLite.
    - Polls the `jobs` table for pending work
    - Executes handlers registered per job_type
    - Supports retry with exponential backoff
    - Supports scheduled execution (delayed jobs)
    - Supports cancellation, retry, and statistics inspection
    """

    def __init__(self, db: Database, poll_interval: float = 5.0):
        self.db = db
        self.poll_interval = poll_interval
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_heartbeat: float = time.time()
        self._current_job_id: Optional[int] = None
        self._lock = threading.Lock()

    def register(self, job_type: str, handler: Callable):
        """Register a handler function for a job type."""
        with self._lock:
            self._handlers[job_type] = handler
        logger.debug("Registered handler for job type: %s", job_type)

    def submit(
        self,
        job_type: str,
        clip_id: str = "",
        payload: Optional[dict] = None,
        priority: int = 5,
        delay_seconds: float = 0,
    ) -> int:
        """Submit a new job to the queue."""
        scheduled_for = time.time() + delay_seconds if delay_seconds > 0 else None

        job_id = self.db.create_job(
            job_type=job_type,
            clip_id=clip_id,
            payload=payload,
            priority=priority,
            scheduled_for=scheduled_for,
        )

        logger.info(
            "Job submitted: #%d type=%s clip=%s priority=%d delay=%.0fs",
            job_id, job_type, clip_id or "(none)", priority, delay_seconds,
        )
        return job_id

    def cancel(self, job_id: int) -> bool:
        """Cancel a pending or processing job."""
        logger.info("Cancelling job #%d", job_id)
        return self.db.cancel_job(job_id)

    def retry(self, job_id: int) -> bool:
        """Retry a failed job."""
        logger.info("Retrying job #%d", job_id)
        return self.db.retry_job(job_id)

    def delete(self, job_id: int) -> bool:
        """Delete a job."""
        logger.info("Deleting job #%d", job_id)
        return self.db.delete_job(job_id)

    def start(self):
        """Start the queue worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True

        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="task-queue"
        )
        self._worker_thread.start()
        logger.info("Task queue started (poll every %.1fs)", self.poll_interval)

    def stop(self):
        """Stop the queue worker."""
        with self._lock:
            self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        logger.info("Task queue stopped")

    def _worker_loop(self):
        """Main worker loop — polls for jobs and executes them."""
        while True:
            with self._lock:
                if not self._running:
                    break
            self._last_heartbeat = time.time()

            try:
                job = self.db.get_next_job()
                if job:
                    self._execute_job(job)
                else:
                    self._interruptible_sleep(self.poll_interval)
            except Exception as e:
                logger.error("Queue worker error: %s", e)
                self._interruptible_sleep(self.poll_interval)

    def _execute_job(self, job: dict):
        """Execute a single job with resource safeguards."""
        job_type = job["job_type"]
        job_id = job["id"]
        self._current_job_id = job_id

        with self._lock:
            handler = self._handlers.get(job_type)

        if not handler:
            logger.error("No handler for job type: %s (job #%d)", job_type, job_id)
            self.db.fail_job(job_id, error=f"No handler for type: {job_type}")
            self._current_job_id = None
            return

        logger.info(
            "Executing job #%d: type=%s clip=%s (attempt %d/%d)",
            job_id, job_type, job.get("clip_id", ""),
            job["retries"] + 1, job["max_retries"],
        )

        try:
            result = handler(job)

            latest = self.db.get_job(job_id)
            if latest and latest.get("status") == "failed" and "Cancelled" in (latest.get("error") or ""):
                logger.info("Job #%d was cancelled during execution, skipping queue completion updates", job_id)
                return

            if isinstance(result, JobResult):
                if result.success:
                    self.db.complete_job(job_id, result=result.result)
                    logger.info("Job #%d completed: %s", job_id, result.result[:100])
                else:
                    self.db.fail_job(job_id, error=result.error)
                    logger.warning("Job #%d failed: %s", job_id, result.error[:100])
            else:
                self.db.complete_job(job_id, result=str(result) if result else "")

        except Exception as e:
            logger.error("Job #%d exception: %s", job_id, e, exc_info=True)
            self.db.fail_job(job_id, error=str(e))
        finally:
            self._current_job_id = None
            free_vram()

    def _interruptible_sleep(self, seconds: float):
        """Sleep in small increments so we can stop quickly."""
        intervals = max(1, int(seconds / 0.5))
        for _ in range(intervals):
            with self._lock:
                if not self._running:
                    return
            time.sleep(0.5)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def current_job_id(self) -> Optional[int]:
        return self._current_job_id

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    def get_queue_stats(self) -> dict:
        """Get current queue statistics."""
        return {
            "pending": self.db.count_jobs(JobStatus.PENDING),
            "processing": self.db.count_jobs(JobStatus.PROCESSING),
            "completed": self.db.count_jobs(JobStatus.COMPLETED),
            "failed": self.db.count_jobs(JobStatus.FAILED),
            "scheduled": self.db.count_jobs(JobStatus.SCHEDULED),
            "registered_handlers": list(self._handlers.keys()),
            "is_running": self._running,
            "current_job_id": self._current_job_id,
            "last_heartbeat": self._last_heartbeat,
        }
