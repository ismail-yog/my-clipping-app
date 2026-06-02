"""
StreamClipper — Task Queue
Lightweight SQLite-backed async job queue with retry logic and scheduling.
No external dependencies (no Redis, no Celery) — runs on threads.
"""

import time
import logging
import threading
from typing import Callable, Optional
from dataclasses import dataclass

from database import Database, JobStatus

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
    - Thread-safe, runs a single worker thread

    Replaces Celery + Redis with zero external dependencies.
    """

    def __init__(self, db: Database, poll_interval: float = 5.0):
        self.db = db
        self.poll_interval = poll_interval
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def register(self, job_type: str, handler: Callable):
        """
        Register a handler function for a job type.

        The handler receives (job_dict) and must return a JobResult.
        """
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
        """
        Submit a new job to the queue.

        Args:
            job_type: Type of job (must have a registered handler)
            clip_id: Associated clip ID (if any)
            payload: JSON-serializable data for the handler
            priority: 1 (highest) to 10 (lowest), default 5
            delay_seconds: Delay before job becomes eligible

        Returns:
            Job ID
        """
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

    def start(self):
        """Start the queue worker thread."""
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
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        logger.info("Task queue stopped")

    def _worker_loop(self):
        """Main worker loop — polls for jobs and executes them."""
        while self._running:
            try:
                job = self.db.get_next_job()
                if job:
                    self._execute_job(job)
                else:
                    # No work — sleep before polling again
                    self._interruptible_sleep(self.poll_interval)
            except Exception as e:
                logger.error("Queue worker error: %s", e)
                self._interruptible_sleep(self.poll_interval)

    def _execute_job(self, job: dict):
        """Execute a single job."""
        job_type = job["job_type"]
        job_id = job["id"]

        handler = self._handlers.get(job_type)
        if not handler:
            logger.error("No handler for job type: %s (job #%d)", job_type, job_id)
            self.db.fail_job(job_id, error=f"No handler for type: {job_type}")
            return

        logger.info(
            "Executing job #%d: type=%s clip=%s (attempt %d/%d)",
            job_id, job_type, job.get("clip_id", ""), 
            job["retries"] + 1, job["max_retries"],
        )

        try:
            result = handler(job)

            # Check if job was cancelled during execution
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
                # If handler doesn't return JobResult, treat as success
                self.db.complete_job(job_id, result=str(result) if result else "")

        except Exception as e:
            logger.error("Job #%d exception: %s", job_id, e, exc_info=True)
            self.db.fail_job(job_id, error=str(e))

    def _interruptible_sleep(self, seconds: float):
        """Sleep in small increments so we can stop quickly."""
        intervals = int(seconds / 0.5)
        for _ in range(intervals):
            if not self._running:
                return
            time.sleep(0.5)

    @property
    def is_running(self) -> bool:
        return self._running

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
        }
