"""Clips routes with approve/reject workflow + file serving."""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import Optional
from server.deps import get_db, get_pipeline_manager, get_task_queue

import config

logger = logging.getLogger("streamclipper.api.clips")
router = APIRouter()


@router.get("/clips")
async def list_clips(
    status: Optional[str] = None,
    streamer: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    db = get_db()
    clips = db.get_clips(status=status, streamer=streamer, limit=limit, offset=offset)
    return {"clips": clips}


@router.get("/clips/{clip_id}")
async def get_clip(clip_id: str):
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {"clip": clip}


@router.get("/clips/{clip_id}/video")
async def serve_clip_video(clip_id: str):
    """Serve the actual clip video file for playback in the frontend."""
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip_path = Path(clip.get("clip_path", ""))
    if not clip_path.exists():
        # Try in clips directory by name
        clip_path = config.CLIPS_DIR / f"{clip_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found on disk")

    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=f"{clip_id}.mp4",
    )


@router.get("/clips/{clip_id}/thumbnail")
async def serve_clip_thumbnail(clip_id: str):
    """Serve clip thumbnail if available."""
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    thumb_path = Path(clip.get("thumbnail_path", ""))
    if not thumb_path.exists():
        thumb_path = config.THUMBS_DIR / f"{clip_id}.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.post("/clips/{clip_id}/approve")
async def approve_clip(clip_id: str):
    pm = get_pipeline_manager()
    db = get_db()
    tq = get_task_queue()

    success = False
    if pm:
        try:
            success = pm.approve_clip(clip_id)
        except Exception as e:
            logger.error("Failed to approve clip via pipeline manager: %s", e)

    if not success:
        # Fallback to direct DB and queue submission
        try:
            clip = db.get_clip(clip_id)
            if clip:
                from database import ClipStatus
                # Idempotency
                if clip["status"] in [ClipStatus.APPROVED, ClipStatus.UPLOADING, ClipStatus.UPLOADED]:
                    success = True
                elif db.update_clip_status(clip_id, ClipStatus.APPROVED):
                    if tq:
                        tq.submit(
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
                        success = True
        except Exception as e:
            logger.error("Fallback approval failed: %s", e)

    if success:
        return {"message": "Clip approved and queued for upload"}
    raise HTTPException(status_code=400, detail="Failed to approve clip")


@router.post("/clips/{clip_id}/reject")
async def reject_clip(clip_id: str):
    pm = get_pipeline_manager()
    db = get_db()
    
    success = False
    if pm:
        try:
            success = pm.reject_clip(clip_id)
        except Exception as e:
            logger.error("Failed to reject clip via pipeline manager: %s", e)
            success = db.delete_clip(clip_id)
    else:
        success = db.delete_clip(clip_id)
        
    if success:
        return {"message": "Clip rejected and deleted"}
        
    raise HTTPException(status_code=400, detail="Failed to reject clip")
