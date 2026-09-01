"""
StreamClipper — Test Suite for Pipeline Engine, Subprocesses, Memory Eviction, and Task Queue.
"""

import os
import sys
import time
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root workspace is in sys.path
BASE_DIR = Path(__file__).parent.parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from database import Database, JobStatus
from task_queue import TaskQueue, JobResult
from processor.subprocess_utils import (
    run_command_safely,
    safe_unlink,
    ms_to_timestamp,
    ms_to_ass_timestamp,
    seconds_to_ms,
    free_vram,
    SubprocessExecutionError,
)
from processor.clipper import Clipper, ClipMetadata
from processor.vod import VODProcessor, VODClipper
from watcher.capture import StreamCapture
from detector.sentiment import SentimentDetector, TranscriptSegment, TranscriptWord
from dream_team.tools import check_profanity, calculate_hook_strength, format_hashtag_string


class TestSubprocessUtils(unittest.TestCase):
    """Verify subprocess safety, error wrapping, and millisecond timestamp arithmetic."""

    def test_ms_timestamp_conversions(self):
        self.assertEqual(seconds_to_ms(1.5), 1500)
        self.assertEqual(seconds_to_ms(0), 0)
        self.assertEqual(seconds_to_ms(65.123), 65123)

        self.assertEqual(ms_to_timestamp(0), "00:00:00.000")
        self.assertEqual(ms_to_timestamp(65123), "00:01:05.123")
        self.assertEqual(ms_to_timestamp(3665123), "01:01:05.123")

        self.assertEqual(ms_to_ass_timestamp(0), "0:00:00.00")
        self.assertEqual(ms_to_ass_timestamp(65123), "0:01:05.12")
        self.assertEqual(ms_to_ass_timestamp(3665123), "1:01:05.12")

    def test_safe_unlink(self):
        tmp_file = config.TEMP_MEDIA_DIR / f"test_unlink_{int(time.time() * 1000)}.tmp"
        tmp_file.write_text("temporary data")
        self.assertTrue(tmp_file.exists())
        self.assertTrue(safe_unlink(tmp_file))
        self.assertFalse(tmp_file.exists())
        # Should not raise exception on non-existent file
        self.assertFalse(safe_unlink(tmp_file))

    def test_run_command_safely_success(self):
        res = run_command_safely(["python", "-c", "print('Antigravity_Test_OK')"], timeout=10.0)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Antigravity_Test_OK", res.stdout)

    def test_run_command_safely_failure_raises_typed_error(self):
        with self.assertRaises(SubprocessExecutionError) as ctx:
            run_command_safely(["python", "-c", "import sys; sys.stderr.write('Fatal_Error_Test'); sys.exit(2)"], timeout=10.0)
        self.assertEqual(ctx.exception.returncode, 2)
        self.assertIn("Fatal_Error_Test", ctx.exception.stderr)

    def test_free_vram_invocable(self):
        # Ensure free_vram runs deterministically without exception
        free_vram()


class TestTaskQueueAndDatabase(unittest.TestCase):
    """Verify task queue lifecycle, priority, cancellation, retry, and heartbeats."""

    def setUp(self):
        self.test_db_path = config.TEMP_MEDIA_DIR / f"test_streamclipper_{int(time.time() * 1000)}.db"
        self.db = Database(db_path=self.test_db_path)
        self.task_queue = TaskQueue(db=self.db, poll_interval=0.1)

    def tearDown(self):
        self.task_queue.stop()
        self.db.close()
        safe_unlink(self.test_db_path)

    def test_job_submission_and_execution(self):
        executed = []

        def dummy_handler(job):
            executed.append(job["id"])
            return JobResult(success=True, result="Processed OK")

        self.task_queue.register("test_dummy", dummy_handler)
        self.task_queue.start()

        job_id = self.task_queue.submit("test_dummy", clip_id="clip_123", payload={"k": "v"})
        self.assertGreater(job_id, 0)

        # Wait for worker loop
        for _ in range(30):
            job = self.db.get_job(job_id)
            if job and job["status"] == "completed":
                break
            time.sleep(0.1)

        job = self.db.get_job(job_id)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"], "Processed OK")
        self.assertIn(job_id, executed)

    def test_job_cancellation_and_retry(self):
        job_id = self.task_queue.submit("dummy_type", clip_id="clip_999")
        self.assertEqual(self.db.get_job(job_id)["status"], "pending")

        # Cancel
        ok = self.task_queue.cancel(job_id)
        self.assertTrue(ok)
        job = self.db.get_job(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("Cancelled", job["error"])

        # Retry
        ok_retry = self.task_queue.retry(job_id)
        self.assertTrue(ok_retry)
        job_retried = self.db.get_job(job_id)
        self.assertEqual(job_retried["status"], "pending")
        self.assertEqual(job_retried["retries"], 0)

    def test_queue_stats(self):
        self.task_queue.submit("type_a")
        self.task_queue.submit("type_b")
        stats = self.task_queue.get_queue_stats()
        self.assertEqual(stats["pending"], 2)
        self.assertIn("last_heartbeat", stats)


class TestDreamTeamTools(unittest.TestCase):
    """Verify Dream Team tool routines and text algorithms."""

    def test_check_profanity(self):
        res_clean = check_profanity("This is a totally clean stream moment")
        self.assertTrue(res_clean["clean"])
        self.assertEqual(res_clean["count"], 0)

        res_profane = check_profanity("What the fuck just happened")
        self.assertFalse(res_profane["clean"])
        self.assertIn("fuck", res_profane["flagged_words"])

    def test_calculate_hook_strength(self):
        res_strong = calculate_hook_strength("You will NEVER believe this insane clutch!")
        self.assertGreaterEqual(res_strong["score"], 0.7)
        self.assertEqual(res_strong["rating"], "strong")

        res_empty = calculate_hook_strength("")
        self.assertEqual(res_empty["score"], 0.0)

    def test_format_hashtag_string(self):
        tags = ["viral", "#shorts", "gaming moment!"]
        res = format_hashtag_string(tags)
        self.assertEqual(res, "#viral #shorts #gamingmoment")


if __name__ == "__main__":
    unittest.main()
