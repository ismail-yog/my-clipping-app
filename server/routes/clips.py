"""Clips routes with approve/reject workflow + file serving."""

import time
import logging
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
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


class BatchClipsRequest(BaseModel):
    clip_ids: list[str]


@router.get("/clips/upload_queue")
async def get_upload_queue():
    """Retrieve all clips in the upload queue (approved or uploading), strictly excluding uploaded."""
    db = get_db()
    clips = db.get_clips(status="approved", limit=100)
    uploading = db.get_clips(status="uploading", limit=50)
    all_queued = uploading + [c for c in clips if c["clip_id"] not in {u["clip_id"] for u in uploading}]
    # Strictly exclude any already uploaded clips
    all_queued = [c for c in all_queued if c.get("status") != "uploaded"]
    return {"upload_queue": all_queued, "count": len(all_queued)}


@router.post("/clips/queue_batch")
async def queue_clips_batch(body: BatchClipsRequest):
    """Batch add clips to upload queue (ignoring already uploaded clips)."""
    db = get_db()
    tq = get_task_queue()
    pm = get_pipeline_manager()
    queued = []

    for cid in body.clip_ids:
        try:
            clip = db.get_clip(cid)
            if not clip:
                continue
            # Strictly forbidden: already uploaded clips can never be uploaded again
            if clip.get("status") == "uploaded":
                logger.warning("Clip %s is already uploaded — rejected from upload queue", cid)
                continue

            if pm:
                if pm.approve_clip(cid):
                    queued.append(cid)
            else:
                if db.update_clip_status(cid, "approved"):
                    if tq:
                        tq.submit(
                            job_type="upload",
                            clip_id=cid,
                            payload={
                                "clip_path": clip["clip_path"],
                                "title": clip["title"],
                                "description": clip["description"],
                                "tags": clip["tags"],
                                "thumbnail_path": clip.get("thumbnail_path", ""),
                            },
                            priority=3,
                        )
                    queued.append(cid)
        except Exception as e:
            logger.error("Failed to queue clip %s: %s", cid, e)

    return {"message": f"Queued {len(queued)} clips for upload", "queued": queued}


@router.post("/clips/unqueue_batch")
async def unqueue_clips_batch(body: BatchClipsRequest):
    """Batch remove clips from upload queue."""
    db = get_db()
    with db._conn() as conn:
        for cid in body.clip_ids:
            conn.execute(
                "DELETE FROM jobs WHERE job_type = 'upload' AND clip_id = ? AND status IN ('pending', 'scheduled')",
                (cid,),
            )
            conn.execute(
                "UPDATE clips SET status = 'pending_review', updated_at = ? WHERE clip_id = ?",
                (time.time(), cid),
            )
    return {"message": f"Removed {len(body.clip_ids)} clips from upload queue"}


@router.post("/clips/clear_upload_queue")
async def clear_upload_queue():
    """Clear all pending upload jobs and revert clips to pending_review."""
    db = get_db()
    with db._conn() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'upload' AND status IN ('pending', 'scheduled')")
        conn.execute(
            "UPDATE clips SET status = 'pending_review', updated_at = ? WHERE status = 'approved'",
            (time.time(),),
        )
    return {"message": "Upload queue cleared"}


@router.post("/clips/upload_all_now")
async def upload_all_now():
    """Expedite all queued/scheduled upload jobs to run immediately across connected accounts."""
    db = get_db()
    with db._conn() as conn:
        cursor = conn.execute(
            """UPDATE jobs SET scheduled_for = NULL, status = 'pending'
               WHERE job_type = 'upload' AND status = 'scheduled'"""
        )
        expedited_count = cursor.rowcount
    return {
        "message": f"Expedited {expedited_count} scheduled upload jobs for immediate dispatch.",
        "expedited_count": expedited_count,
    }


@router.get("/clips/{clip_id}")
async def get_clip(clip_id: str):
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {"clip": clip}


@router.get("/clips/{clip_id}/video")
async def serve_clip_video(clip_id: str, request: Request):
    """Serve the actual clip video file for playback in the frontend with HTTP Byte-Range support."""
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

    file_size = clip_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            byte_range = range_header.replace("bytes=", "").split("-")
            start = int(byte_range[0]) if byte_range[0] else 0
            end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
            start = max(0, start)
            end = min(file_size - 1, end)
            chunk_size = (end - start) + 1

            def iterfile():
                with open(clip_path, mode="rb") as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_bytes = min(128 * 1024, remaining)
                        data = f.read(read_bytes)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": "video/mp4",
            }
            return StreamingResponse(iterfile(), status_code=206, headers=headers)
        except Exception as e:
            logger.error("Range streaming error for clip %s: %s", clip_id, e)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    }
    return FileResponse(
        str(clip_path),
        media_type="video/mp4",
        filename=f"{clip_id}.mp4",
        headers=headers,
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
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    # Strict rule: already uploaded clips can NEVER be uploaded again
    if clip.get("status") == "uploaded":
        raise HTTPException(
            status_code=400,
            detail="Clip has already been uploaded and cannot be re-uploaded",
        )

    pm = get_pipeline_manager()
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
            from database import ClipStatus
            # Idempotency
            if clip["status"] in [ClipStatus.APPROVED, ClipStatus.UPLOADING]:
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


@router.post("/clips/{clip_id}/unqueue")
async def unqueue_clip(clip_id: str):
    """Remove a clip from the upload queue and revert status to pending_review."""
    db = get_db()
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    with db._conn() as conn:
        conn.execute(
            "DELETE FROM jobs WHERE job_type = 'upload' AND clip_id = ? AND status IN ('pending', 'scheduled')",
            (clip_id,),
        )
        conn.execute(
            "UPDATE clips SET status = 'pending_review', updated_at = ? WHERE clip_id = ?",
            (time.time(), clip_id),
        )

    logger.info("Removed clip %s from upload queue", clip_id)
    return {"message": "Clip removed from upload queue", "clip_id": clip_id, "status": "pending_review"}


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
