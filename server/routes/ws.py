"""WebSocket route for real-time dashboard updates."""

import json
import time
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.deps import get_db, get_pipeline_manager, get_task_queue
from processor.vod import VOD_PROGRESS

logger = logging.getLogger("streamclipper.ws")
router = APIRouter()

# Connected clients
_clients: list[WebSocket] = []


async def broadcast(data: dict):
    """Send data to all connected WebSocket clients."""
    if not _clients:
        return
    msg = json.dumps(data)
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.remove(ws)


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Real-time dashboard updates via WebSocket."""
    await websocket.accept()
    _clients.append(websocket)
    logger.info("WebSocket client connected (%d total)", len(_clients))

    try:
        while True:
            db = get_db()
            pm = get_pipeline_manager()
            tq = get_task_queue()

            stats = db.get_stats()
            data = {
                "type": "status_update",
                "timestamp": time.time(),
                "active": len(pm.active_pipelines) if pm else 0,
                "total_clips": stats.get("total_clips", 0),
                "pending_review": stats.get("pending_review", 0),
                "uploads_today": stats.get("uploads_today", 0),
                "queue_pending": tq.get_queue_stats().get("pending", 0) if tq else 0,
                "vod_progress": VOD_PROGRESS.copy(),
            }

            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
    finally:
        if websocket in _clients:
            _clients.remove(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(_clients))
