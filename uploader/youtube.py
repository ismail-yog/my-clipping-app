"""
StreamClipper — YouTube Uploader
Uploads clips to YouTube Shorts via the Data API v3 with OAuth 2.0.
"""

import time
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import config

logger = logging.getLogger("streamclipper.youtube")


@dataclass
class UploadResult:
    success: bool
    video_id: str = ""
    video_url: str = ""
    error: str = ""
    timestamp: float = 0.0


class YouTubeUploader:
    """
    Uploads video clips to YouTube using the Data API v3.

    Handles OAuth 2.0 authentication with token persistence,
    quota management, and retry logic.
    """

    def __init__(self):
        self._service = None
        self._uploads: list[UploadResult] = []
        self._daily_uploads: int = 0
        self._daily_reset: float = 0.0

    def _get_service(self):
        """Authenticate and return a YouTube API service object."""
        if self._service is not None:
            return self._service

        secrets_path = Path(config.YOUTUBE_CLIENT_SECRETS)
        if not secrets_path.exists():
            logger.error("YouTube client_secrets.json not found at %s", secrets_path)
            return None

        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            token_path = Path(config.YOUTUBE_TOKEN_FILE)

            # Load existing token
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(token_path), config.YOUTUBE_SCOPES
                )

            # Refresh or get new token
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing YouTube OAuth token...")
                    creds.refresh(Request())
                else:
                    logger.info("Starting YouTube OAuth flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(secrets_path), config.YOUTUBE_SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # Save token for next time
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                logger.info("YouTube token saved to %s", token_path)

            self._service = build(
                config.YOUTUBE_API_SERVICE_NAME,
                config.YOUTUBE_API_VERSION,
                credentials=creds,
            )
            logger.info("YouTube API service initialized")
            return self._service

        except Exception as e:
            logger.error("YouTube auth failed: %s", e)
            return None

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[list[str]] = None,
        privacy: str = "public",
        category_id: str = "",
    ) -> UploadResult:
        """
        Upload a video to YouTube.

        Args:
            video_path: Path to the video file.
            title: Video title (max 100 chars).
            description: Video description.
            tags: List of tags.
            privacy: "public", "unlisted", or "private".
            category_id: YouTube category ID (default from config).
        """
        # Check quota
        self._check_daily_reset()
        if self._daily_uploads >= 6:
            logger.warning("Daily upload quota reached (6/day on free tier)")
            result = UploadResult(
                success=False,
                error="Daily upload quota exceeded",
                timestamp=time.time(),
            )
            self._uploads.append(result)
            return result

        service = self._get_service()
        if not service:
            result = UploadResult(
                success=False,
                error="YouTube API not authenticated",
                timestamp=time.time(),
            )
            self._uploads.append(result)
            return result

        if not video_path.exists():
            result = UploadResult(
                success=False,
                error=f"Video file not found: {video_path}",
                timestamp=time.time(),
            )
            self._uploads.append(result)
            return result

        try:
            from googleapiclient.http import MediaFileUpload

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": (tags or [])[:30],
                    "categoryId": category_id or config.YOUTUBE_CATEGORY_ID,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 5,  # 5MB chunks
            )

            logger.info("Uploading to YouTube: %s", title)

            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = self._resumable_upload(request)

            if response:
                video_id = response["id"]
                video_url = f"https://youtube.com/shorts/{video_id}"
                self._daily_uploads += 1

                result = UploadResult(
                    success=True,
                    video_id=video_id,
                    video_url=video_url,
                    timestamp=time.time(),
                )
                self._uploads.append(result)

                logger.info("✅ Uploaded: %s → %s", title, video_url)
                return result

            result = UploadResult(
                success=False,
                error="Upload returned no response",
                timestamp=time.time(),
            )
            self._uploads.append(result)
            return result

        except Exception as e:
            logger.error("Upload failed: %s", e)
            result = UploadResult(
                success=False,
                error=str(e),
                timestamp=time.time(),
            )
            self._uploads.append(result)
            return result

    def _resumable_upload(self, request, max_retries: int = 3):
        """Execute a resumable upload with retry logic."""
        import random
        from googleapiclient.errors import HttpError

        response = None
        retry = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.debug("Upload progress: %d%%", int(status.progress() * 100))
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504] and retry < max_retries:
                    retry += 1
                    wait = 2 ** retry + random.random()
                    logger.warning("Upload error %d, retrying in %.1fs...", e.resp.status, wait)
                    time.sleep(wait)
                else:
                    raise

        return response

    def _check_daily_reset(self):
        """Reset daily counter at midnight PT."""
        now = time.time()
        if now - self._daily_reset > 86400:
            self._daily_uploads = 0
            self._daily_reset = now

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """Set a custom thumbnail for an uploaded video."""
        service = self._get_service()
        if not service:
            return False

        if not thumbnail_path.exists():
            logger.warning("Thumbnail file not found: %s", thumbnail_path)
            return False

        try:
            from googleapiclient.http import MediaFileUpload

            media = MediaFileUpload(
                str(thumbnail_path),
                mimetype="image/jpeg",
            )

            service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()

            logger.info("🖼️ Thumbnail set for video %s", video_id)
            return True

        except Exception as e:
            logger.warning("Failed to set thumbnail: %s", e)
            return False

    @property
    def upload_history(self) -> list[UploadResult]:
        return list(self._uploads)

    @property
    def uploads_today(self) -> int:
        self._check_daily_reset()
        return self._daily_uploads
