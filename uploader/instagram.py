"""
StreamClipper / LumiClip — Instagram Reels & Meta Graph Video Publisher Adapter
Uploads vertical shorts to Instagram Reels using the official Meta Graph API v20.0+.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests

import config

logger = logging.getLogger("streamclipper.uploader.instagram")


class InstagramUploader:
    """Publishes vertical short-form reels to Instagram via Meta Graph API."""

    def __init__(self):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "") or os.getenv("META_ACCESS_TOKEN", "")
        self.ig_user_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
        self.graph_version = "v20.0"
        self.base_url = f"https://graph.facebook.com/{self.graph_version}"

    def upload_reel(
        self,
        video_url: str,
        caption: str,
        tags: list = None,
        cover_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create and publish an Instagram Reel container from a public/signed video URL.
        """
        if not self.access_token or not self.ig_user_id:
            logger.warning("INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not configured.")
            return {
                "status": "unconfigured",
                "message": "Instagram Meta Graph credentials missing in .env"
            }

        tags = tags or []
        tag_str = " ".join(f"#{t.replace(' ', '')}" for t in tags)
        full_caption = f"{caption}\n\n{tag_str}".strip()[:2200]

        try:
            # 1. Create Media Container for REELS
            container_url = f"{self.base_url}/{self.ig_user_id}/media"
            params = {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": full_caption,
                "share_to_feed": True,
                "access_token": self.access_token,
            }
            if cover_url:
                params["cover_url"] = cover_url

            logger.info("Initializing Instagram Reel media container for account %s...", self.ig_user_id)
            init_resp = requests.post(container_url, data=params, timeout=30)
            if init_resp.status_code != 200:
                return {"status": "error", "code": init_resp.status_code, "message": init_resp.text}

            creation_id = init_resp.json().get("id")
            if not creation_id:
                return {"status": "error", "message": "Failed to obtain container creation_id", "raw": init_resp.json()}

            logger.info("Instagram container created: %s. Polling processing status...", creation_id)

            # 2. Poll container status until FINISHED
            status_url = f"{self.base_url}/{creation_id}"
            max_attempts = 15
            for attempt in range(max_attempts):
                time.sleep(4)
                stat_resp = requests.get(
                    status_url,
                    params={"fields": "status_code", "access_token": self.access_token},
                    timeout=15
                )
                if stat_resp.status_code == 200:
                    status_code = stat_resp.json().get("status_code")
                    logger.debug("Instagram container %s status: %s (attempt %d)", creation_id, status_code, attempt + 1)
                    if status_code == "FINISHED":
                        break
                    elif status_code == "ERROR":
                        return {"status": "error", "message": "Instagram media container encoding failed"}

            # 3. Publish the Container
            publish_url = f"{self.base_url}/{self.ig_user_id}/media_publish"
            pub_resp = requests.post(
                publish_url,
                data={"creation_id": creation_id, "access_token": self.access_token},
                timeout=30
            )

            if pub_resp.status_code == 200:
                media_id = pub_resp.json().get("id")
                logger.info("Successfully published Instagram Reel! Media ID: %s", media_id)
                return {
                    "status": "success",
                    "media_id": media_id,
                    "platform": "instagram_reels"
                }
            else:
                return {"status": "error", "code": pub_resp.status_code, "message": pub_resp.text}

        except Exception as e:
            logger.error("Instagram publish failed: %s", e)
            return {"status": "error", "message": str(e)}
