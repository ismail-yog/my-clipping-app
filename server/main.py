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

    # Ensure TaskQueue worker is active
    try:
        tq = get_task_queue()
        if tq and not tq.is_running:
            tq.start()
            logger.info("Task queue worker started")
    except Exception as e:
        logger.error("Failed to start task queue: %s", e)

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
    if pm and streamers and not pm.is_active:
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


# ── System Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Service health check endpoint."""
    return {"status": "ok", "timestamp": time.time()}

@app.get("/")
async def root():
    """Service root endpoint."""
    return {"message": "StreamClipper API is running", "timestamp": time.time()}


from server.routes import auth, settings, ws, status, streamers, clips, uploads, jobs, vod, dreamteam

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
app.include_router(dreamteam.router, prefix="/api/dreamteam", tags=["Dream Team"])


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    return app
