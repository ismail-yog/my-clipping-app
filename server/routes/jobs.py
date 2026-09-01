"""
Job Queue API Routes — Job lifecycle management, status inspection, cancellation, and retry.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from server.deps import get_db, get_task_queue

logger = logging.getLogger("streamclipper.api.jobs")
router = APIRouter()


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 50):
    """List jobs with optional status filter."""
    db = get_db()
    return {"jobs": db.get_jobs(status=status, limit=limit)}


@router.get("/jobs/stats")
async def get_jobs_stats():
    """Get queue summary statistics and worker heartbeat."""
    tq = get_task_queue()
    if not tq:
        db = get_db()
        return {
            "pending": db.count_jobs("pending"),
            "processing": db.count_jobs("processing"),
            "completed": db.count_jobs("completed"),
            "failed": db.count_jobs("failed"),
            "scheduled": db.count_jobs("scheduled"),
            "is_running": False,
        }
    return tq.get_queue_stats()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: int):
    """Cancel a pending, scheduled, or active job."""
    tq = get_task_queue()
    db = get_db()
    if tq:
        ok = tq.cancel(job_id)
    else:
        ok = db.cancel_job(job_id)

    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or could not be cancelled")
    return {"success": True, "job_id": job_id, "status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job_endpoint(job_id: int):
    """Retry a failed job."""
    tq = get_task_queue()
    db = get_db()
    if tq:
        ok = tq.retry(job_id)
    else:
        ok = db.retry_job(job_id)

    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or could not be retried")
    return {"success": True, "job_id": job_id, "status": "pending"}


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: int):
    """Permanently delete a job."""
    db = get_db()
    ok = db.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job_id": job_id, "deleted": True}
