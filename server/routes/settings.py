import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import config

logger = logging.getLogger("streamclipper.api.settings")
router = APIRouter()

SETTINGS_FILE = config.BASE_DIR / "settings.json"

from typing import Optional, List

class SettingsUpdate(BaseModel):
    max_clips: int = 3
    clip_duration: int = 35
    download_resolution: int = 1080
    parallel_renders: int = 2
    use_fast_whisper: bool = True
    burn_captions: bool = True
    viral_threshold: float = 0.65
    auto_publish: bool = False
    ai_custom_prompt: Optional[str] = ""
    ai_description_template: Optional[str] = ""
    upload_schedule_mode: str = "immediate"  # "immediate", "peak_hours", "stagger"
    upload_peak_hours: List[str] = ["12:00", "16:00", "20:00"]
    upload_stagger_minutes: int = 120

@router.get("")
async def get_settings():
    """Get current settings from config and settings.json with 30-45s duration clamping."""
    # Start with current config values and sensible defaults
    settings = {
        "max_clips": config.vod_settings.max_clips,
        "clip_duration": max(30, min(45, config.vod_settings.clip_duration)),
        "download_resolution": config.vod_settings.download_resolution,
        "parallel_renders": config.vod_settings.parallel_renders,
        "use_fast_whisper": config.vod_settings.use_fast_whisper,
        "burn_captions": config.vod_settings.burn_captions,
        "viral_threshold": max(0.65, config.thresholds.moment_threshold),
        "auto_publish": False,
        "ai_custom_prompt": "Write authentic, viral lowercase titles with emojis (💀, 😭). Reference exact spoken phrases from transcript in quotes. Keep it raw and funny.",
        "ai_description_template": "{summary}\n\nCatch the stream live on Twitch: https://twitch.tv/{streamer}\n\n#Shorts #gaming #viral #streamer #fyp",
        "upload_schedule_mode": "immediate",
        "upload_peak_hours": ["12:00", "16:00", "20:00"],
        "upload_stagger_minutes": 120,
    }
    
    # Override with what's actually in settings.json if present
    if SETTINGS_FILE.exists():
        try:
            file_data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            settings.update(file_data)
            settings["clip_duration"] = max(30, min(45, int(settings.get("clip_duration", 35))))
            settings["viral_threshold"] = max(0.65, float(settings.get("viral_threshold", 0.65)))
        except Exception as e:
            logger.error("Failed to read settings file: %s", e)
            
    return settings

@router.post("")
async def update_settings(settings: SettingsUpdate):
    """Update settings.json and reload config with strict 30-45s duration clamping."""
    try:
        data = settings.dict()
        data["clip_duration"] = max(30, min(45, int(data.get("clip_duration", 35))))
        data["viral_threshold"] = max(0.65, data.get("viral_threshold", 0.65))
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        
        # Force reload in config object
        config.vod_settings.load_dynamic()
        config.clip_settings.default_duration = data["clip_duration"]
        config.clip_settings.min_duration = 30
        config.clip_settings.max_duration = 45
        config.thresholds.moment_threshold = data["viral_threshold"]
        
        logger.info("Settings updated and reloaded: %s", data)
        return {"status": "success", "settings": data}
    except Exception as e:
        logger.error("Failed to update settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
