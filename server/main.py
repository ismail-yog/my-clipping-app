"""
StreamClipper — FastAPI Unified Backend
FastAPI backend that exposes REST API for the frontend dashboard.
"""

import time
import logging
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from database import Database
from task_queue import TaskQueue
from server.deps import get_db, get_pipeline_manager, get_task_queue
from server.routes import auth, settings, ws, status, streamers, clips, uploads, jobs, vod

# Logger matching specification
logger = logging.getLogger("streamclipper.server")


# ── Pydantic Models ─────────────────────────────────────────────────────────

class StreamerCreate(BaseModel):
    name: str
    platform: str
    channel: str
    url: str
    auto_approve: bool = False


class StreamerUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_approve: Optional[bool] = None
    name: Optional[str] = None
    platform: Optional[str] = None
    channel: Optional[str] = None
    url: Optional[str] = None


class VODProcessRequest(BaseModel):
    url: str
    layout_type: str = "gamer"


# ── Lifespan Context Manager ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI server starting")

    # Reset any stuck processing jobs back to pending on startup
    try:
        db = get_db()
        db.reset_processing_jobs()
        logger.info("Reset all stuck processing jobs to pending")
    except Exception as e:
        logger.error("Failed to reset stuck processing jobs: %s", e)

    # Auto-start pipeline manager for live stream monitoring
    pm = get_pipeline_manager()
    streamers = config.get_streamers()
    if pm and streamers:
        logger.info("Auto-starting pipeline manager with %d streamers", len(streamers))
        try:
            pm.start(streamers)
        except Exception as e:
            logger.error("Failed to auto-start pipeline manager: %s", e)

    yield

    # Shutdown
    if pm:
        try:
            pm.stop()
        except Exception as e:
            logger.error("Failed to stop pipeline manager: %s", e)
    logger.info("FastAPI server shutting down")


# ── FastAPI App Setup ────────────────────────────────────────────────────────

app = FastAPI(
    title="StreamClipper API",
    version="2.0",
    lifespan=lifespan
)

# CORS setup matching specifications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware (Request Logging and Error Handling) ─────────────────────────

@app.middleware("http")
async def log_requests_and_errors(request: Request, call_next):
    start_time = time.time()
    logger.info("Request: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            "Response: %s %s - status=%d - duration=%.3fs",
            request.method,
            request.url.path,
            response.status_code,
            process_time
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "Unhandled exception in request %s %s: %s (duration=%.3fs)",
            request.method,
            request.url.path,
            e,
            process_time,
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred.", "error": str(e)}
        )


# ── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats(db: Database = Depends(get_db)):
    """Retrieve overall system statistics."""
    try:
        return db.get_stats()
    except Exception as e:
        logger.error("Failed to get stats: %s", e)
        raise HTTPException(status_code=500, detail="Database stats query failed")


@app.get("/api/streamers")
async def get_streamers(db: Database = Depends(get_db)):
    """Retrieve all configured streamers."""
    try:
        return db.get_streamers(enabled_only=False)
    except Exception as e:
        logger.error("Failed to get streamers: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@app.post("/api/streamers")
async def create_streamer(req: StreamerCreate, db: Database = Depends(get_db)):
    """Add a new streamer."""
    try:
        # Avoid duplicate platforms and channels
        streamers = db.get_streamers(enabled_only=False)
        for s in streamers:
            if s.get("platform") == req.platform and s.get("channel") == req.channel:
                raise HTTPException(status_code=400, detail="Streamer already exists")

        streamer_id = db.add_streamer(
            name=req.name,
            platform=req.platform,
            channel=req.channel,
            url=req.url,
            enabled=True,
            auto_approve=req.auto_approve
        )
        created = db.get_streamer(streamer_id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to retrieve created streamer")
        return created
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add streamer: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/streamers/{id}")
async def update_streamer(id: int, req: StreamerUpdate, db: Database = Depends(get_db)):
    """Update configured streamer options."""
    try:
        if not db.get_streamer(id):
            raise HTTPException(status_code=404, detail="Streamer not found")

        updates = req.model_dump(exclude_unset=True)
        # Convert booleans to integers for standard SQLite mappings
        for k, v in list(updates.items()):
            if isinstance(v, bool):
                updates[k] = int(v)

        success = db.update_streamer(id, **updates)
        return {"success": success, "streamer": db.get_streamer(id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update streamer %d: %s", id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/streamers/{id}")
async def delete_streamer(id: int, db: Database = Depends(get_db)):
    """Delete a streamer configuration."""
    try:
        if not db.get_streamer(id):
            raise HTTPException(status_code=404, detail="Streamer not found")
        success = db.delete_streamer(id)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete streamer %d: %s", id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clips")
async def get_clips(
    status: Optional[str] = None,
    streamer: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Database = Depends(get_db)
):
    """Retrieve video clips with optional filters."""
    try:
        return db.get_clips(status=status, streamer=streamer, limit=limit, offset=offset)
    except Exception as e:
        logger.error("Failed to query clips: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clips/{clip_id}")
async def get_clip(clip_id: str, db: Database = Depends(get_db)):
    """Retrieve a single clip metadata."""
    try:
        clip = db.get_clip(clip_id)
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        return clip
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to query clip %s: %s", clip_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clips/{clip_id}/approve")
async def approve_clip(clip_id: str, pm = Depends(get_pipeline_manager)):
    """Approve a clip and submit it to the queue for uploading."""
    if not pm:
        raise HTTPException(status_code=500, detail="Pipeline manager not initialized")
    try:
        success = pm.approve_clip(clip_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Approval failed. Clip may already be approved/uploaded or does not exist."
            )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error approving clip %s: %s", clip_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/clips/{clip_id}")
async def delete_clip(clip_id: str, db: Database = Depends(get_db)):
    """Delete a clip record and its media files."""
    try:
        if not db.get_clip(clip_id):
            raise HTTPException(status_code=404, detail="Clip not found")
        success = db.delete_clip(clip_id)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete clip %s: %s", clip_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/uploads")
async def get_uploads(limit: int = 50, db: Database = Depends(get_db)):
    """Retrieve history of successful uploads."""
    try:
        return db.get_uploads(limit=limit)
    except Exception as e:
        logger.error("Failed to get uploads: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vod/process")
async def process_vod(req: VODProcessRequest, tq = Depends(get_task_queue)):
    """Submit a video URL for highlights and clipping via the task queue."""
    if not tq:
        raise HTTPException(status_code=500, detail="Task queue not initialized")
    try:
        job_id = tq.submit(
            job_type="vod_process",
            payload={"url": req.url, "layout_type": req.layout_type},
            priority=2
        )
        return {"job_id": str(job_id)}
    except Exception as e:
        logger.error("Failed to submit VOD job: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
async def get_jobs(status: Optional[str] = None, limit: int = 50, db: Database = Depends(get_db)):
    """Get jobs from queue."""
    try:
        return db.get_jobs(status=status, limit=limit)
    except Exception as e:
        logger.error("Failed to query jobs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Service health check endpoint."""
    return {"status": "ok", "timestamp": time.time()}


# ── Include Modular Sub-Routers ─────────────────────────────────────────────

app.include_router(ws.router, tags=["WebSocket"])
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(streamers.router, prefix="/api", tags=["Streamers"])
app.include_router(clips.router, prefix="/api", tags=["Clips"])
app.include_router(uploads.router, prefix="/api", tags=["Uploads"])
app.include_router(jobs.router, prefix="/api", tags=["Jobs"])
app.include_router(vod.router, prefix="/api/vod", tags=["VOD"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    return app
