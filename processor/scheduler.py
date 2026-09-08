"""
StreamClipper — Upload Timing & Scheduling Engine
Calculates optimal publishing delay based on peak hour windows or stagger spacing.
"""

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import config

logger = logging.getLogger("streamclipper.processor.scheduler")

SETTINGS_FILE = config.BASE_DIR / "settings.json"


def get_schedule_settings() -> dict:
    """Load scheduling settings from settings.json."""
    default = {
        "upload_schedule_mode": "immediate",
        "upload_peak_hours": ["12:00", "16:00", "20:00"],
        "upload_stagger_minutes": 120,
    }
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            pass
    return default


def calculate_next_upload_delay(db) -> float:
    """
    Determine delay_seconds (0 or positive float) for an upcoming upload job.
    Supports:
    1. 'immediate': 0 delay.
    2. 'stagger': Guarantees at least N minutes between consecutive uploads.
    3. 'peak_hours': Schedules for the next available hour from upload_peak_hours.
    """
    settings = get_schedule_settings()
    mode = settings.get("upload_schedule_mode", "immediate")

    now = time.time()
    now_dt = datetime.fromtimestamp(now)

    if mode == "immediate":
        return 0.0

    elif mode == "stagger":
        stagger_sec = max(60, int(settings.get("upload_stagger_minutes", 120)) * 60)

        # Query latest scheduled or running upload job in task queue
        with db._conn() as conn:
            row = conn.execute(
                """SELECT MAX(COALESCE(scheduled_for, created_at))
                   FROM jobs
                   WHERE job_type = 'upload'
                   AND status IN ('pending', 'scheduled', 'processing')"""
            ).fetchone()
            latest_queued = row[0] if row and row[0] else None

            # Also check last completed upload time
            row_u = conn.execute("SELECT MAX(uploaded_at) FROM uploads WHERE success = 1").fetchone()
            latest_uploaded = row_u[0] if row_u and row_u[0] else None

        latest_anchor = max(filter(None, [latest_queued, latest_uploaded, now]))

        if latest_anchor > now:
            # Another job is already queued in the future — stagger after it
            target_time = latest_anchor + stagger_sec
        elif latest_anchor + stagger_sec > now:
            # An upload finished recently — wait remaining stagger time
            target_time = latest_anchor + stagger_sec
        else:
            target_time = now

        delay = max(0.0, target_time - now)
        logger.info(
            "Stagger schedule: target in %.1f minutes (anchor: %s)",
            delay / 60,
            datetime.fromtimestamp(latest_anchor).strftime("%H:%M:%S")
        )
        return delay

    elif mode == "peak_hours":
        peak_hours: List[str] = settings.get("upload_peak_hours", ["12:00", "16:00", "20:00"])
        if not peak_hours:
            return 0.0

        # Parse target timeslots for today and tomorrow
        candidates = []
        for h_str in peak_hours:
            try:
                parts = h_str.strip().split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                dt_today = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                dt_tomorrow = dt_today + timedelta(days=1)
                candidates.append(dt_today)
                candidates.append(dt_tomorrow)
            except Exception:
                continue

        candidates.sort()

        # Find future slots (at least 2 minutes in the future)
        future_slots = [c for c in candidates if c.timestamp() > now + 120]
        if not future_slots:
            return 0.0

        # Query existing scheduled jobs to avoid slot collision
        with db._conn() as conn:
            rows = conn.execute(
                """SELECT scheduled_for FROM jobs
                   WHERE job_type = 'upload'
                   AND status IN ('pending', 'scheduled')
                   AND scheduled_for IS NOT NULL"""
            ).fetchall()
            existing_scheduled = [r[0] for r in rows if r[0]]

        # In a 3-account setup (18 videos/day), each of the 6 peak windows can host
        # up to 3 uploads (1 per account), staggered by 180s (3 minutes).
        max_uploads_per_window = 3
        selected_slot_time = None

        for slot in future_slots:
            slot_ts = slot.timestamp()
            # Count existing jobs scheduled in this window (within 45 minutes)
            window_jobs = [sched for sched in existing_scheduled if abs(slot_ts - sched) < 2700]
            if len(window_jobs) < max_uploads_per_window:
                # Stagger by 3 minutes per job already booked in this peak window
                selected_slot_time = slot_ts + (len(window_jobs) * 180)
                break

        if not selected_slot_time:
            # Fallback to next earliest slot
            selected_slot_time = (future_slots[0].timestamp() if future_slots else now) + 180

        delay = max(0.0, selected_slot_time - now)
        logger.info(
            "Multi-account peak schedule: selected slot at %s (in %.1f hours)",
            datetime.fromtimestamp(selected_slot_time).strftime("%Y-%m-%d %H:%M:%S"),
            delay / 3600,
        )
        return delay

    return 0.0
