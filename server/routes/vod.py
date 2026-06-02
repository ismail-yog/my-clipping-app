"""
VOD / Clip Generator Routes — Download YouTube video, find viral moments, generate clips.
This is the core "Crayo-style" feature.
"""

import logging
import threading
import subprocess
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional

from server.deps import get_db, get_task_queue, get_pipeline_manager
from processor.vod import VODProcessor, VOD_PROGRESS

logger = logging.getLogger("streamclipper.api.vod")
router = APIRouter()

# Track active job state per URL
_active_jobs: dict[str, str] = {}  # url -> job_id


class VODRequest(BaseModel):
    url: str
    layout_type: Optional[str] = "gamer"


class VODStatusResponse(BaseModel):
    job_id: str
    url: str
    progress: int
    status: str


@router.post("/process")
async def process_vod(req: VODRequest):
    """
    Submit a YouTube/video URL for processing via task queue.
    """
    url = req.url.strip()
    layout_type = req.layout_type or "gamer"
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Validate URL format
    if not any(domain in url for domain in ["youtube.com", "youtu.be", "twitch.tv", "kick.com"]):
        # Allow any URL that yt-dlp might support, but warn
        logger.warning("Non-standard URL submitted: %s — yt-dlp will attempt anyway", url)

    db = get_db()
    tq = get_task_queue()
    pm = get_pipeline_manager()

    if not tq:
        raise HTTPException(status_code=500, detail="Task queue not initialized")

    # Auto-resume pipeline manager if it was stopped/inactive
    if pm and not pm.is_active:
        logger.info("Automatically resuming pipeline manager for new VOD process")
        import config
        streamers = config.get_streamers()
        pm.start(streamers)

    # Submit job to the task queue
    job_id = tq.submit(
        job_type="vod_process",
        payload={"url": url, "layout_type": layout_type},
        priority=2,
    )

    _active_jobs[url] = str(job_id)

    # Initialize progress
    VOD_PROGRESS[str(job_id)] = {"url": url, "progress": 5, "status": "Queued..."}

    return {
        "status": "accepted",
        "job_id": str(job_id),
        "message": "Processing started — clips will appear in the Clips tab when ready"
    }


@router.post("/cancel/{job_id}")
async def cancel_vod_job(job_id: str):
    """
    Cancel an active VOD processing job and stop/halt the pipeline manager
    until a new process is given.
    """
    logger.info("API: cancel_vod_job called for job ID %s", job_id)
    db = get_db()
    pm = get_pipeline_manager()
    tq = get_task_queue()

    # 1. Cancel the active running processor (if any)
    cancelled_ok = VODProcessor.cancel_job(job_id)

    # 2. Mark the job as failed/cancelled in the DB
    try:
        job_id_int = int(job_id)
        db.fail_job(job_id_int, error="Cancelled by user")
    except Exception as e:
        logger.error("Failed to update job status in DB on cancel: %s", e)

    # 3. Update VOD_PROGRESS state
    if job_id in VOD_PROGRESS:
        VOD_PROGRESS[job_id] = {
            "url": VOD_PROGRESS[job_id].get("url", ""),
            "progress": 0,
            "status": "Cancelled"
        }
        # Keep the "Cancelled" status visible for a short time, then remove
        threading.Timer(10, lambda: VOD_PROGRESS.pop(job_id, None)).start()

    # 4. Stop the system (PipelineManager and TaskQueue) so it halts until a new process is given
    if pm:
        logger.info("Manual cancel triggered: stopping/halting pipeline manager")
        pm.stop()

    return {
        "status": "cancelled",
        "job_id": job_id,
        "cancelled_active_thread": cancelled_ok,
        "message": "Job cancelled and system processing halted."
    }


@router.post("/process_streamer/{streamer_id}")
async def process_streamer(streamer_id: int):
    """Find the latest video for a streamer and start processing."""
    logger.info("API: process_streamer called for ID %d", streamer_id)
    db = get_db()
    streamer = db.get_streamer(streamer_id)
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")

    # Determine base URL based on platform
    platform = streamer.get("platform", "youtube").lower()
    channel = streamer.get("channel")
    url = streamer.get("url")

    if not url:
        if platform == "twitch":
            url = f"https://www.twitch.tv/{channel}/videos?filter=archives"
        elif platform == "kick":
            url = f"https://kick.com/{channel}/videos"
        else:
            url = f"https://www.youtube.com/@{channel}/videos"
    
    # Try to resolve latest video URL using yt-dlp
    try:
        # Use common flags for resolution too
        resolve_cmd = [
            "yt-dlp", "--get-id", "--playlist-items", "1", "--flat-playlist",
            "--no-check-certificate",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            url
        ]
        r = subprocess.run(resolve_cmd, capture_output=True, text=True, timeout=30)
        
        if r.returncode == 0 and r.stdout.strip():
            video_id = r.stdout.strip().split("\n")[0]
            if platform == "youtube":
                url = f"https://www.youtube.com/watch?v={video_id}"
            elif platform == "twitch":
                url = f"https://www.twitch.tv/videos/{video_id}"
            elif platform == "kick" and "kick.com" not in video_id:
                url = f"https://kick.com/video/{video_id}"
            
            logger.info("Resolved latest %s video for %s: %s", platform, streamer["name"], url)
        else:
            logger.warning("Could not resolve latest video for %s (code %d), using: %s", streamer["name"], r.returncode, url)
    except Exception as e:
        logger.error("Failed to resolve streamer URL for %s: %s", streamer["name"], e)

    # Re-use the existing process_vod logic
    return await process_vod(VODRequest(url=url))


@router.get("/progress")
async def get_vod_progress():
    """Get progress of all active VOD processing jobs."""
    return {"jobs": VOD_PROGRESS}


@router.get("/progress/{job_id}")
async def get_vod_job_progress(job_id: str):
    """Get progress of a specific VOD job."""
    if job_id in VOD_PROGRESS:
        return VOD_PROGRESS[job_id]
    # Job may have finished and been cleaned from progress tracker
    return {"url": "", "progress": 100, "status": "completed"}
