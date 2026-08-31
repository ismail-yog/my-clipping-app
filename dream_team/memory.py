"""Dream Team — Shared Memory
SQLite-backed persistent key-value store shared across all agents.
Supports categories, timestamps, search, and automatic expiry.
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dream_team import config

logger = logging.getLogger("dreamteam.memory")

# Valid categories for organised storage
VALID_CATEGORIES = ("clips", "patterns", "user_feedback", "errors", "performance")

# Default retention period
DEFAULT_EXPIRY_DAYS = 30


class SharedMemory:
    """Thread-safe SQLite memory store for the Dream Team.

    Usage::

        mem = SharedMemory()
        mem.store("top_clip", {"id": 42, "score": 0.95}, category="clips")
        value = mem.retrieve("top_clip")
        results = mem.search(category="clips", limit=10)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (config.DREAM_TEAM_DIR / "dream_team_memory.db")
        self._local = threading.local()  # per-thread connections
        self._init_lock = threading.Lock()
        self._init_db()
        logger.info("SharedMemory initialised — db: %s", self.db_path)

    # ──────────────────────────────────────────────────────────────────
    # Connection management (one connection per thread)
    # ──────────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        """Create the memory table if it doesn't exist."""
        with self._init_lock:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    key       TEXT PRIMARY KEY,
                    value     TEXT NOT NULL,
                    category  TEXT NOT NULL DEFAULT 'clips',
                    agent     TEXT DEFAULT '',
                    created   TEXT NOT NULL,
                    updated   TEXT NOT NULL,
                    expires   TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_updated ON memory(updated)
            """)
            conn.commit()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def store(
        self,
        key: str,
        value: Any,
        category: str = "clips",
        agent: str = "",
        expiry_days: int = DEFAULT_EXPIRY_DAYS,
    ) -> None:
        """Store or update a key-value pair.

        Args:
            key: Unique identifier.
            value: Any JSON-serialisable value.
            category: One of VALID_CATEGORIES.
            agent: Name of the agent storing the value.
            expiry_days: Days until auto-expiry (default 30).
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of {VALID_CATEGORIES}"
            )

        now = datetime.utcnow().isoformat()
        expires = (datetime.utcnow() + timedelta(days=expiry_days)).isoformat()
        serialised = json.dumps(value)

        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO memory (key, value, category, agent, created, updated, expires)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value   = excluded.value,
                category = excluded.category,
                agent   = excluded.agent,
                updated = excluded.updated,
                expires = excluded.expires
            """,
            (key, serialised, category, agent, now, now, expires),
        )
        conn.commit()
        logger.debug("store(%s) — category=%s, agent=%s", key, category, agent)

    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value by key. Returns ``None`` if not found or expired."""
        self._cleanup_expired()
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def search(
        self,
        category: str = "clips",
        limit: int = 20,
        agent: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search memory entries by category.

        Returns a list of dicts with keys: key, value, category, agent, created, updated.
        """
        self._cleanup_expired()
        conn = self._get_conn()

        query = "SELECT * FROM memory WHERE category = ?"
        params: list = [category]

        if agent:
            query += " AND agent = ?"
            params.append(agent)

        query += " ORDER BY updated DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            results.append({
                "key": row["key"],
                "value": json.loads(row["value"]),
                "category": row["category"],
                "agent": row["agent"],
                "created": row["created"],
                "updated": row["updated"],
            })
        return results

    def delete(self, key: str) -> bool:
        """Delete a memory entry by key. Returns True if something was deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM memory WHERE key = ?", (key,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug("delete(%s) — removed", key)
        return deleted

    def count(self, category: Optional[str] = None) -> int:
        """Count entries, optionally filtered by category."""
        conn = self._get_conn()
        if category:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory WHERE category = ?", (category,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM memory").fetchone()
        return row["cnt"] if row else 0

    def clear(self, category: Optional[str] = None) -> int:
        """Clear all entries or entries in a specific category. Returns count deleted."""
        conn = self._get_conn()
        if category:
            cursor = conn.execute("DELETE FROM memory WHERE category = ?", (category,))
        else:
            cursor = conn.execute("DELETE FROM memory")
        conn.commit()
        logger.info("clear(category=%s) — removed %d entries", category, cursor.rowcount)
        return cursor.rowcount

    # ──────────────────────────────────────────────────────────────────
    # Expiry
    # ──────────────────────────────────────────────────────────────────

    def _cleanup_expired(self) -> None:
        """Remove entries whose expiry timestamp has passed."""
        now = datetime.utcnow().isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM memory WHERE expires IS NOT NULL AND expires < ?", (now,)
        )
        if cursor.rowcount:
            conn.commit()
            logger.info("Expired %d stale memory entries", cursor.rowcount)

    # ──────────────────────────────────────────────────────────────────
    # Stats
    # ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return a summary of memory usage by category."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM memory GROUP BY category"
        ).fetchall()
        stats = {row["category"]: row["cnt"] for row in rows}
        stats["total"] = sum(stats.values())
        return stats

    def __repr__(self) -> str:
        return f"<SharedMemory db={self.db_path} entries={self.count()}>"
