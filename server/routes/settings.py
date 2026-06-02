import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import config

logger = logging.getLogger("streamclipper.api.settings")
router = APIRouter()

SETTINGS_FILE = config.BASE_DIR / "settings.json"

class SettingsUpdate(BaseModel):
    max_clips: int = 3
    clip_duration: int = 45
    download_resolution: int = 1080
    parallel_renders: int = 2
    use_fast_whisper: bool = True
    burn_captions: bool = True
    viral_threshold: float = 0.4
    auto_publish: bool = False

@router.get("")
async def get_settings():
    """Get current settings from config and settings.json."""
    # Start with current config values
    settings = {
        "max_clips": config.vod_settings.max_clips,
        "clip_duration": config.vod_settings.clip_duration,
        "download_resolution": config.vod_settings.download_resolution,
        "parallel_renders": config.vod_settings.parallel_renders,
        "use_fast_whisper": config.vod_settings.use_fast_whisper,
        "burn_captions": config.vod_settings.burn_captions,
        "viral_threshold": config.thresholds.moment_threshold,
        "auto_publish": False, # Mocked for now
    }
    
    # Override with what's actually in the file if present
    if SETTINGS_FILE.exists():
        try:
            file_data = json.loads(SETTINGS_FILE.read_text())
            settings.update(file_data)
        except Exception as e:
            logger.error("Failed to read settings file: %s", e)
            
    return settings

@router.post("")
async def update_settings(settings: SettingsUpdate):
    """Update settings.json and reload config."""
    try:
        data = settings.dict()
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        
        # Force reload in config object
        config.vod_settings.load_dynamic()
        config.thresholds.moment_threshold = settings.viral_threshold
        
        logger.info("Settings updated and reloaded: %s", data)
        return {"status": "success", "settings": data}
    except Exception as e:
        logger.error("Failed to update settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
