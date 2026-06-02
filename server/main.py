"""
StreamClipper — FastAPI Application
REST API + WebSocket backend at localhost:8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routes import streamers, clips, uploads, jobs, status, ws, vod, auth, settings

logger = logging.getLogger("streamclipper.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI server starting")
    
    # Reset any stuck processing jobs back to pending on startup
    from server.deps import get_db, get_pipeline_manager
    try:
        db = get_db()
        db.reset_processing_jobs()
        logger.info("Reset all stuck processing jobs to pending")
    except Exception as e:
        logger.error("Failed to reset stuck processing jobs: %s", e)
    
    # Auto-start pipeline manager for live stream monitoring
    import config
    pm = get_pipeline_manager()
    streamers = config.get_streamers()
    if pm and streamers:
        logger.info("Auto-starting pipeline manager with %d streamers", len(streamers))
        pm.start(streamers)
        
    yield
    
    # Shutdown
    if pm:
        pm.stop()
    logger.info("FastAPI server shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="StreamClip AI",
        description="Autonomous stream highlight clipper & uploader — REST API",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS — allow all for debugging
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(status.router, prefix="/api", tags=["Status"])
    app.include_router(streamers.router, prefix="/api", tags=["Streamers"])
    app.include_router(clips.router, prefix="/api", tags=["Clips"])
    app.include_router(uploads.router, prefix="/api", tags=["Uploads"])
    app.include_router(jobs.router, prefix="/api", tags=["Jobs"])
    app.include_router(vod.router, prefix="/api/vod", tags=["VOD"])
    app.include_router(auth.router, prefix="/api", tags=["Auth"])
    app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(ws.router, tags=["WebSocket"])

    @app.get("/", tags=["Health"])
    async def root():
        return {"service": "StreamClip AI", "version": "2.0.0", "status": "running"}

    return app
