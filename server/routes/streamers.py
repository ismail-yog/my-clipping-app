"""Streamers CRUD routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from server.deps import get_db, get_pipeline_manager

router = APIRouter()


class StreamerCreate(BaseModel):
    name: str
    platform: str
    channel: str
    url: str
    enabled: bool = True
    auto_approve: bool = False


class StreamerUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    channel: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    auto_approve: Optional[bool] = None


@router.get("/streamers")
async def list_streamers():
    db = get_db()
    pm = get_pipeline_manager()
    streamers = db.get_streamers()
    
    # Merge live status if pipeline manager is available
    if pm and pm.monitor:
        statuses = pm.monitor.statuses
        for s in streamers:
            key = f"{s['platform']}:{s['channel']}"
            status = statuses.get(key)
            s["is_live"] = status.is_live if status else False
    else:
        for s in streamers:
            s["is_live"] = False
            
    return {"streamers": streamers}


@router.post("/streamers")
async def add_streamer(body: StreamerCreate):
    db = get_db()
    try:
        sid = db.add_streamer(
            name=body.name,
            platform=body.platform,
            channel=body.channel,
            url=body.url,
            enabled=body.enabled,
            auto_approve=body.auto_approve,
        )
        return {"id": sid, "message": "Streamer added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/streamers/{streamer_id}")
async def update_streamer(streamer_id: int, body: StreamerUpdate):
    db = get_db()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    db.update_streamer(streamer_id, **updates)
    return {"message": "Streamer updated"}


@router.delete("/streamers/{streamer_id}")
async def delete_streamer(streamer_id: int):
    db = get_db()
    db.delete_streamer(streamer_id)
    return {"message": "Streamer deleted"}
