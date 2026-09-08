"""Streamers CRUD routes."""

import logging
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import config
from server.deps import get_db, get_pipeline_manager

logger = logging.getLogger("streamclipper.server.routes.streamers")
router = APIRouter()


class StreamerCreate(BaseModel):
    name: str
    platform: str
    channel: str
    url: str = ""
    enabled: bool = True
    auto_approve: bool = False
    framing_mode: Optional[str] = "white_canvas"
    subtitle_style: Optional[str] = "glacier_glow"


class StreamerUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    channel: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    auto_approve: Optional[bool] = None
    framing_mode: Optional[str] = None
    subtitle_style: Optional[str] = None


def normalize_streamer_inputs(name: str, platform: str, channel: str, url: str) -> tuple[str, str, str, str]:
    """Normalize streamer platform, channel username, and stream URL."""
    name = (name or "").strip()
    platform = (platform or "twitch").strip().lower()
    channel = (channel or "").strip()
    url = (url or "").strip()

    # Detect platform or channel from full URL if passed in channel or url
    input_str = channel if "://" in channel else url
    if "twitch.tv/" in input_str.lower():
        platform = "twitch"
        parsed = urlparse(input_str if "://" in input_str else f"https://{input_str}")
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            channel = path_parts[0]
        url = f"https://www.twitch.tv/{channel}"
    elif "kick.com/" in input_str.lower():
        platform = "kick"
        parsed = urlparse(input_str if "://" in input_str else f"https://{input_str}")
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            channel = path_parts[0]
        url = f"https://kick.com/{channel}"
    elif "youtube.com/" in input_str.lower() or "youtu.be/" in input_str.lower():
        platform = "youtube"
        parsed = urlparse(input_str if "://" in input_str else f"https://{input_str}")
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            channel = path_parts[0]
        url = input_str if "://" in input_str else f"https://{input_str}"

    # Clean channel handle
    if platform in ("twitch", "kick"):
        channel = channel.lower().lstrip("@").strip()
        if not url:
            url = f"https://www.twitch.tv/{channel}" if platform == "twitch" else f"https://kick.com/{channel}"
    elif platform == "youtube":
        if not url:
            handle = channel if channel.startswith("@") or channel.startswith("UC") else f"@{channel}"
            url = f"https://www.youtube.com/{handle}"

    if not name:
        name = channel

    return name, platform, channel, url


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
    pm = get_pipeline_manager()
    name, platform, channel, url = normalize_streamer_inputs(
        body.name, body.platform, body.channel, body.url
    )

    try:
        framing_mode = body.framing_mode or "white_canvas"
        subtitle_style = body.subtitle_style or "glacier_glow"
        sid = db.add_streamer(
            name=name,
            platform=platform,
            channel=channel,
            url=url,
            enabled=body.enabled,
            auto_approve=body.auto_approve,
            framing_mode=framing_mode,
            subtitle_style=subtitle_style,
        )

        # Dynamically register with active monitor and check immediately
        if pm and pm.monitor:
            cfg = config.StreamerConfig(
                name=name,
                platform=platform,
                channel=channel,
                url=url,
                enabled=body.enabled,
                auto_approve=body.auto_approve,
                framing_mode=framing_mode,
                subtitle_style=subtitle_style,
            )
            pm.monitor.add_or_update_streamer(cfg, check_immediately=True)

        return {"id": sid, "message": "Streamer added", "channel": channel, "url": url}
    except Exception as e:
        logger.error("Failed to add streamer: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/streamers/{streamer_id}")
async def update_streamer(streamer_id: int, body: StreamerUpdate):
    db = get_db()
    pm = get_pipeline_manager()
    streamer = db.get_streamer(streamer_id)
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # If updating identity fields, normalize
    name = updates.get("name", streamer["name"])
    platform = updates.get("platform", streamer["platform"])
    channel = updates.get("channel", streamer["channel"])
    url = updates.get("url", streamer["url"])

    name, platform, channel, url = normalize_streamer_inputs(name, platform, channel, url)
    updates["name"] = name
    updates["platform"] = platform
    updates["channel"] = channel
    updates["url"] = url

    db.update_streamer(streamer_id, **updates)

    updated = db.get_streamer(streamer_id)
    if pm and pm.monitor and updated:
        cfg = config.StreamerConfig(
            name=updated["name"],
            platform=updated["platform"],
            channel=updated["channel"],
            url=updated["url"],
            enabled=bool(updated["enabled"]),
            auto_approve=bool(updated["auto_approve"]),
            framing_mode=updated.get("framing_mode") or "white_canvas",
            subtitle_style=updated.get("subtitle_style") or "glacier_glow",
        )
        pm.monitor.add_or_update_streamer(cfg, check_immediately=bool(updated["enabled"]))
        key = f"{cfg.platform}:{cfg.channel}"
        if hasattr(pm, "_pipelines") and key in pm._pipelines:
            pm._pipelines[key].streamer = cfg

    return {"message": "Streamer updated"}


@router.delete("/streamers/{streamer_id}")
async def delete_streamer(streamer_id: int):
    db = get_db()
    pm = get_pipeline_manager()
    streamer = db.get_streamer(streamer_id)
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")

    db.delete_streamer(streamer_id)
    if pm and pm.monitor:
        pm.monitor.remove_streamer(streamer.get("name", ""))
    return {"message": "Streamer deleted"}
