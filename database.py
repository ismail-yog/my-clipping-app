"""
StreamClipper — Database
SQLite persistence layer for streams, clips, jobs, uploads, and sessions.
Thread-safe with connection-per-thread pattern.
"""

import json
import time
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager

import config

logger = logging.getLogger("streamclipper.database")

# ── Schema ──────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS streamers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    platform    TEXT NOT NULL,
    channel     TEXT NOT NULL,
    url         TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    auto_approve INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer_id INTEGER NOT NULL REFERENCES streamers(id),
    started_at  REAL NOT NULL,
    ended_at    REAL,
    title       TEXT DEFAULT '',
    game        TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'recording',
    segments    INTEGER DEFAULT 0,
    FOREIGN KEY (streamer_id) REFERENCES streamers(id)
);

CREATE TABLE IF NOT EXISTS clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id         TEXT NOT NULL UNIQUE,
    session_id      INTEGER REFERENCES sessions(id),
    streamer_name   TEXT NOT NULL,
    platform        TEXT NOT NULL,
    clip_path       TEXT NOT NULL,
    thumbnail_path  TEXT DEFAULT '',
    duration        REAL NOT NULL,
    moment_score    REAL NOT NULL DEFAULT 0.0,
    emotion         TEXT DEFAULT '',
    transcript      TEXT DEFAULT '',
    title           TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    hook_text       TEXT DEFAULT '',
    has_captions    INTEGER DEFAULT 0,
    has_hook        INTEGER DEFAULT 0,
    has_thumbnail   INTEGER DEFAULT 0,
    seo_ready       INTEGER DEFAULT 0,
    seo_method      TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending_review',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS uploads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id     TEXT NOT NULL REFERENCES clips(clip_id),
    video_id    TEXT DEFAULT '',
    video_url   TEXT DEFAULT '',
    success     INTEGER NOT NULL DEFAULT 0,
    error       TEXT DEFAULT '',
    uploaded_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type    TEXT NOT NULL,
    clip_id     TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    priority    INTEGER NOT NULL DEFAULT 5,
    payload     TEXT DEFAULT '{}',
    result      TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    retries     INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    created_at  REAL NOT NULL,
    started_at  REAL,
    completed_at REAL,
    scheduled_for REAL
);

CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);
CREATE INDEX IF NOT EXISTS idx_clips_streamer ON clips(streamer_name);
CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_uploads_clip ON uploads(clip_id);
CREATE INDEX IF NOT EXISTS idx_sessions_streamer ON sessions(streamer_id);
"""


# ── Job States ──────────────────────────────────────────────────────────────

class ClipStatus:
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"

    VALID_TRANSITIONS = {
        PENDING_REVIEW: [APPROVED, REJECTED],
        APPROVED: [PROCESSING, UPLOADING],
        PROCESSING: [APPROVED, FAILED],
        UPLOADING: [UPLOADED, FAILED],
        UPLOADED: [],
        REJECTED: [PENDING_REVIEW],  # Allow un-reject
        FAILED: [PENDING_REVIEW, APPROVED],  # Allow retry
    }


class JobStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SCHEDULED = "scheduled"


# ── Database Class ──────────────────────────────────────────────────────────


class Database:
    """Thread-safe SQLite database for StreamClipper."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(config.BASE_DIR / "streamclipper.db")
        self.db_path = str(Path(self.db_path).absolute())
        self._local = threading.local()
        self._init_schema()
        logger.info("Database initialized at: %s", self.db_path)

    @contextmanager
    def _conn(self):
        """Get a thread-local connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield self._local.connection
            self._local.connection.commit()
        except Exception:
            self._local.connection.rollback()
            raise

    def _init_schema(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
            # Set schema version
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            logger.debug("Schema initialized (v%d)", SCHEMA_VERSION)

    # ── Streamers ───────────────────────────────────────────────────────────

    def add_streamer(
        self,
        name: str,
        platform: str,
        channel: str,
        url: str,
        enabled: bool = True,
        auto_approve: bool = False,
    ) -> int:
        """Add a new streamer. Returns the streamer ID."""
        now = time.time()
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO streamers (name, platform, channel, url, enabled, auto_approve, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, platform, channel, url, int(enabled), int(auto_approve), now, now),
            )
            logger.info("Added streamer: %s (%s/%s)", name, platform, channel)
            return cursor.lastrowid

    def get_streamers(self, enabled_only: bool = False) -> list[dict]:
        """Get all streamers, optionally filtered to enabled only."""
        with self._conn() as conn:
            if enabled_only:
                cursor = conn.execute(
                    "SELECT * FROM streamers WHERE enabled = 1 ORDER BY name"
                )
            else:
                cursor = conn.execute("SELECT * FROM streamers ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    def get_streamer(self, streamer_id: int) -> Optional[dict]:
        """Get a single streamer by ID."""
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM streamers WHERE id = ?", (streamer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_streamer(self, streamer_id: int, **kwargs) -> bool:
        """Update streamer fields."""
        allowed = {"name", "platform", "channel", "url", "enabled", "auto_approve"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        updates["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [streamer_id]

        with self._conn() as conn:
            conn.execute(
                f"UPDATE streamers SET {set_clause} WHERE id = ?", values
            )
        return True

    def delete_streamer(self, streamer_id: int) -> bool:
        """Delete a streamer."""
        with self._conn() as conn:
            conn.execute("DELETE FROM streamers WHERE id = ?", (streamer_id,))
        return True

    # ── Sessions ────────────────────────────────────────────────────────────

    def start_session(
        self, streamer_id: int, title: str = "", game: str = ""
    ) -> int:
        """Start a new recording session. Returns session ID."""
        now = time.time()
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO sessions (streamer_id, started_at, title, game, status)
                   VALUES (?, ?, ?, ?, 'recording')""",
                (streamer_id, now, title, game),
            )
            return cursor.lastrowid

    def end_session(self, session_id: int):
        """End a recording session."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = ?, status = 'completed' WHERE id = ?",
                (now, session_id),
            )

    def get_active_sessions(self) -> list[dict]:
        """Get all currently recording sessions."""
        with self._conn() as conn:
            cursor = conn.execute(
                """SELECT s.*, st.name as streamer_name, st.platform
                   FROM sessions s JOIN streamers st ON s.streamer_id = st.id
                   WHERE s.status = 'recording'
                   ORDER BY s.started_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]

    # ── Clips ───────────────────────────────────────────────────────────────

    def save_clip(
        self,
        clip_id: str,
        streamer_name: str,
        platform: str,
        clip_path: str,
        duration: float,
        moment_score: float = 0.0,
        emotion: str = "",
        transcript: str = "",
        has_captions: bool = False,
        session_id: Optional[int] = None,
        auto_approve: bool = False,
    ) -> int:
        """Save a new clip. Returns the row ID."""
        now = time.time()
        status = ClipStatus.APPROVED if auto_approve else ClipStatus.PENDING_REVIEW

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO clips
                   (clip_id, session_id, streamer_name, platform, clip_path,
                    duration, moment_score, emotion, transcript, has_captions,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clip_id, session_id, streamer_name, platform, clip_path,
                    duration, moment_score, emotion, transcript[:2000],
                    int(has_captions), status, now, now,
                ),
            )
            logger.info("Clip saved: %s (status=%s)", clip_id, status)
            return cursor.lastrowid

    def update_clip_seo(
        self,
        clip_id: str,
        title: str,
        description: str,
        tags: list[str],
        hook_text: str = "",
        seo_method: str = "ollama",
    ):
        """Update clip with SEO metadata."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """UPDATE clips SET title = ?, description = ?, tags = ?,
                   hook_text = ?, seo_ready = 1, seo_method = ?, updated_at = ?
                   WHERE clip_id = ?""",
                (title, description, json.dumps(tags), hook_text, seo_method, now, clip_id),
            )

    def update_clip_status(self, clip_id: str, new_status: str) -> bool:
        """Transition a clip to a new status (validates state machine)."""
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT status FROM clips WHERE clip_id = ?", (clip_id,)
            )
            row = cursor.fetchone()
            if not row:
                logger.error("Clip not found: %s", clip_id)
                return False

            current = row["status"]
            valid = ClipStatus.VALID_TRANSITIONS.get(current, [])
            if new_status not in valid:
                logger.warning(
                    "Invalid transition %s → %s for clip %s",
                    current, new_status, clip_id,
                )
                return False

            conn.execute(
                "UPDATE clips SET status = ?, updated_at = ? WHERE clip_id = ?",
                (new_status, time.time(), clip_id),
            )
            logger.info("Clip %s: %s → %s", clip_id, current, new_status)
            return True

    def update_clip_hook(self, clip_id: str, has_hook: bool = True):
        """Mark clip as having hook overlay applied."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE clips SET has_hook = ?, updated_at = ? WHERE clip_id = ?",
                (int(has_hook), time.time(), clip_id),
            )

    def update_clip_thumbnail(self, clip_id: str, thumbnail_path: str):
        """Set the thumbnail path for a clip."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE clips SET thumbnail_path = ?, has_thumbnail = 1, updated_at = ? WHERE clip_id = ?",
                (thumbnail_path, time.time(), clip_id),
            )

    def get_clip(self, clip_id: str) -> Optional[dict]:
        """Get a single clip by clip_id."""
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["tags"] = json.loads(d.get("tags") or "[]")
                return d
            return None

    def get_clips(
        self,
        status: Optional[str] = None,
        streamer: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get clips with optional filters."""
        query = "SELECT * FROM clips WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if streamer:
            query += " AND streamer_name = ?"
            params.append(streamer)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._conn() as conn:
            cursor = conn.execute(query, params)
            clips = []
            for row in cursor.fetchall():
                d = dict(row)
                d["tags"] = json.loads(d.get("tags") or "[]")
                clips.append(d)
            return clips

    def get_clips_pending_review(self) -> list[dict]:
        """Get all clips awaiting review."""
        return self.get_clips(status=ClipStatus.PENDING_REVIEW)

    def get_clips_approved(self) -> list[dict]:
        """Get all approved clips ready for upload."""
        return self.get_clips(status=ClipStatus.APPROVED)

    def count_clips(self, status: Optional[str] = None) -> int:
        """Count clips, optionally by status."""
        with self._conn() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM clips WHERE status = ?", (status,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM clips")
            return cursor.fetchone()[0]

    def delete_clip(self, clip_id: str) -> bool:
        """Delete a clip from database and disk."""
        clip = self.get_clip(clip_id)
        if not clip:
            logger.info("Clip %s not found (already deleted), treating as success", clip_id)
            return True

        # 1. Delete files on disk
        clip_path_str = clip.get("clip_path")
        if clip_path_str:
            try:
                Path(clip_path_str).unlink(missing_ok=True)
            except Exception as e:
                logger.error("Failed to delete clip file %s: %s", clip_path_str, e)

        thumb_path_str = clip.get("thumbnail_path")
        if thumb_path_str:
            try:
                Path(thumb_path_str).unlink(missing_ok=True)
            except Exception as e:
                logger.error("Failed to delete thumbnail file %s: %s", thumb_path_str, e)

        # Delete subtitles file (.ass) if it exists
        try:
            ass_path = config.CLIPS_DIR / f"{clip_id}.ass"
            ass_path.unlink(missing_ok=True)
        except Exception as e:
            logger.error("Failed to delete ass subtitle file: %s", e)

        # 2. Delete database records
        with self._conn() as conn:
            conn.execute("DELETE FROM uploads WHERE clip_id = ?", (clip_id,))
            conn.execute("DELETE FROM jobs WHERE clip_id = ?", (clip_id,))
            conn.execute("DELETE FROM clips WHERE clip_id = ?", (clip_id,))
        
        logger.info("Clip %s deleted successfully from DB and disk", clip_id)
        return True

    # ── Uploads ─────────────────────────────────────────────────────────────

    def save_upload(
        self,
        clip_id: str,
        success: bool,
        video_id: str = "",
        video_url: str = "",
        error: str = "",
    ) -> int:
        """Record an upload attempt."""
        now = time.time()
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO uploads (clip_id, video_id, video_url, success, error, uploaded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (clip_id, video_id, video_url, int(success), error, now),
            )

            # Update clip status
            if success:
                conn.execute(
                    "UPDATE clips SET status = 'uploaded', updated_at = ? WHERE clip_id = ?",
                    (now, clip_id),
                )

            return cursor.lastrowid

    def get_uploads(self, limit: int = 50) -> list[dict]:
        """Get recent uploads."""
        with self._conn() as conn:
            cursor = conn.execute(
                """SELECT u.*, c.title, c.streamer_name, c.platform, c.thumbnail_path
                   FROM uploads u LEFT JOIN clips c ON u.clip_id = c.clip_id
                   ORDER BY u.uploaded_at DESC LIMIT ?""",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_uploads_today(self) -> int:
        """Count successful uploads in the last 24 hours."""
        cutoff = time.time() - 86400
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM uploads WHERE success = 1 AND uploaded_at >= ?",
                (cutoff,),
            )
            return cursor.fetchone()[0]

    # ── Jobs ────────────────────────────────────────────────────────────────

    def create_job(
        self,
        job_type: str,
        clip_id: str = "",
        payload: Optional[dict] = None,
        priority: int = 5,
        scheduled_for: Optional[float] = None,
    ) -> int:
        """Create a new job in the queue."""
        now = time.time()
        status = JobStatus.SCHEDULED if scheduled_for else JobStatus.PENDING

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO jobs
                   (job_type, clip_id, status, priority, payload, created_at, scheduled_for)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_type, clip_id, status, priority,
                    json.dumps(payload or {}), now, scheduled_for,
                ),
            )
            return cursor.lastrowid

    def get_next_job(self) -> Optional[dict]:
        """Get the next pending job (highest priority, oldest first)."""
        now = time.time()
        with self._conn() as conn:
            cursor = conn.execute(
                """SELECT * FROM jobs
                   WHERE status IN ('pending', 'scheduled')
                   AND (scheduled_for IS NULL OR scheduled_for <= ?)
                   ORDER BY priority ASC, created_at ASC
                   LIMIT 1""",
                (now,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["payload"] = json.loads(d.get("payload") or "{}")
                # Mark as processing
                conn.execute(
                    "UPDATE jobs SET status = 'processing', started_at = ? WHERE id = ?",
                    (now, d["id"]),
                )
                return d
            return None

    def get_job(self, job_id: int) -> Optional[dict]:
        """Get a job by its ID."""
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["payload"] = json.loads(d.get("payload") or "{}")
                return d
            return None

    def complete_job(self, job_id: int, result: str = ""):
        """Mark a job as completed."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                (result, time.time(), job_id),
            )

    def fail_job(self, job_id: int, error: str = ""):
        """Mark a job as failed. Increments retry count."""
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET
                   status = CASE WHEN retries + 1 < max_retries THEN 'pending' ELSE 'failed' END,
                   error = ?, retries = retries + 1, completed_at = ?
                   WHERE id = ?""",
                (error, time.time(), job_id),
            )

    def reset_processing_jobs(self):
        """Reset any jobs stuck in 'processing' state back to 'pending' on startup."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'pending' WHERE status = 'processing'"
            )

    def get_jobs(
        self, status: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        """Get jobs with optional status filter."""
        query = "SELECT * FROM jobs"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            cursor = conn.execute(query, params)
            jobs = []
            for row in cursor.fetchall():
                d = dict(row)
                d["payload"] = json.loads(d.get("payload") or "{}")
                jobs.append(d)
            return jobs

    def count_jobs(self, status: Optional[str] = None) -> int:
        """Count jobs, optionally by status."""
        with self._conn() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            return cursor.fetchone()[0]

    # ── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall system stats."""
        with self._conn() as conn:
            stats = {
                "total_clips": 0,
                "pending_review": 0,
                "approved": 0,
                "uploaded": 0,
                "rejected": 0,
                "failed": 0,
                "total_uploads": 0,
                "uploads_today": 0,
                "pending_jobs": 0,
                "active_sessions": 0,
                "total_streamers": 0,
                "enabled_streamers": 0,
            }

            cursor = conn.execute("SELECT COUNT(*) FROM clips")
            stats["total_clips"] = cursor.fetchone()[0]

            for s in [ClipStatus.PENDING_REVIEW, ClipStatus.APPROVED,
                       ClipStatus.UPLOADED, ClipStatus.REJECTED, ClipStatus.FAILED]:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM clips WHERE status = ?", (s,)
                )
                key = s.replace("pending_review", "pending_review")
                stats[s] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM uploads WHERE success = 1")
            stats["total_uploads"] = cursor.fetchone()[0]

            stats["uploads_today"] = self.count_uploads_today()

            cursor = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('pending', 'processing', 'scheduled')"
            )
            stats["pending_jobs"] = cursor.fetchone()[0]

            cursor = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = 'recording'"
            )
            stats["active_sessions"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM streamers")
            stats["total_streamers"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM streamers WHERE enabled = 1")
            stats["enabled_streamers"] = cursor.fetchone()[0]

            return stats

    def close(self):
        """Close the thread-local connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
