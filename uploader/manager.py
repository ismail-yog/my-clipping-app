"""
StreamClipper / LumiClip — Unified Multi-Platform Publisher Manager
Dispatches finished clips simultaneously or on schedule to YouTube Shorts, TikTok, and Instagram.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from uploader.youtube import YouTubeUploader
from uploader.tiktok import TikTokUploader
from uploader.instagram import InstagramUploader

logger = logging.getLogger("streamclipper.uploader.manager")


@dataclass
class PublishRequest:
    video_path: Path
    title: str
    description: str
    tags: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=lambda: ["youtube", "tiktok", "instagram"])
    thumbnail_path: Optional[Path] = None
    public_video_url: Optional[str] = None


class PublisherManager:
    """Coordinates and executes multi-platform video uploads."""

    def __init__(self):
        self.yt_uploader = YouTubeUploader()
        self.tiktok_uploader = TikTokUploader()
        self.ig_uploader = InstagramUploader()

    def publish_clip(self, request: PublishRequest) -> Dict[str, Any]:
        """
        Publish video to all requested platforms and aggregate results.
        """
        results: Dict[str, Any] = {}

        for platform in request.platforms:
            p_lower = platform.lower()

            # 1. YouTube Shorts
            if p_lower in ("youtube", "shorts", "yt"):
                try:
                    logger.info("Dispatching to YouTube Shorts: %s", request.video_path.name)
                    yt_res = self.yt_uploader.upload(
                        video_path=request.video_path,
                        title=request.title,
                        description=request.description,
                        tags=request.tags,
                        thumbnail_path=request.thumbnail_path
                    )
                    results["youtube"] = yt_res
                except Exception as e:
                    logger.error("YouTube dispatch error: %s", e)
                    results["youtube"] = {"status": "error", "message": str(e)}

            # 2. TikTok
            elif p_lower in ("tiktok", "tt"):
                try:
                    logger.info("Dispatching to TikTok: %s", request.video_path.name)
                    tt_res = self.tiktok_uploader.upload_video(
                        video_path=request.video_path,
                        title=request.title,
                        tags=request.tags
                    )
                    results["tiktok"] = tt_res
                except Exception as e:
                    logger.error("TikTok dispatch error: %s", e)
                    results["tiktok"] = {"status": "error", "message": str(e)}

            # 3. Instagram Reels
            elif p_lower in ("instagram", "ig", "reels"):
                try:
                    if request.public_video_url:
                        logger.info("Dispatching to Instagram Reels: %s", request.video_path.name)
                        ig_res = self.ig_uploader.upload_reel(
                            video_url=request.public_video_url,
                            caption=f"{request.title}\n\n{request.description}",
                            tags=request.tags
                        )
                        results["instagram"] = ig_res
                    else:
                        results["instagram"] = {
                            "status": "skipped",
                            "message": "Public video URL required for Instagram Meta Graph API upload"
                        }
                except Exception as e:
                    logger.error("Instagram dispatch error: %s", e)
                    results["instagram"] = {"status": "error", "message": str(e)}

        return results
