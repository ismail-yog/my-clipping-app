"""
StreamClipper — YouTube Uploader
Uploads clips to YouTube as Shorts with proper metadata.
"""

import time
import logging
from pathlib import Path
from dataclasses import dataclass

import config

# Logger matching exact specification
logger = logging.getLogger("streamclipper.uploader.youtube")


@dataclass
class UploadResult:
    """Dataclass to represent the result of a YouTube upload."""
    success: bool
    video_id: str = ""
    video_url: str = ""
    error: str = ""


class YouTubeUploader:
    """Uploads video clips to YouTube using OAuth 2.0 and Data API v3."""

    def __init__(self):
        self.scopes = config.YOUTUBE_SCOPES
        self.client_secrets_file = config.YOUTUBE_CLIENT_SECRETS
        self.token_file = config.YOUTUBE_TOKEN_FILE
        self.category_id = getattr(config, "YOUTUBE_CATEGORY_ID", "22")
        self._youtube = None
        logger.info("YouTubeUploader initialized.")

    def _get_authenticated_service(self):
        """Authenticates and returns the Google API client service."""
        if self._youtube is not None:
            return self._youtube

        token_path = Path(self.token_file)
        if not token_path.exists():
            msg = f"YouTube OAuth credentials token file not found at {token_path}."
            logger.error(msg)
            raise FileNotFoundError(msg)

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        import googleapiclient.discovery

        try:
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)
        except Exception as e:
            logger.error("Failed to load credentials from token file %s: %s", token_path, e)
            raise ValueError(f"Invalid token file. Please re-run auth_youtube.py. Error: {e}")

        # Check validity and refresh if needed
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("YouTube OAuth token expired, attempting refresh...")
                try:
                    creds.refresh(Request())
                    # Write updated token back to token file
                    token_path.write_text(creds.to_json())
                    logger.info("YouTube OAuth token refreshed and saved.")
                except Exception as e:
                    logger.error("Failed to refresh credentials token: %s", e)
                    raise ValueError(f"Credentials refresh failed. Please re-run auth_youtube.py. Error: {e}")
            else:
                msg = "Credentials token is invalid and cannot be refreshed. Please re-run auth_youtube.py."
                logger.error(msg)
                raise ValueError(msg)

        try:
            self._youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
            logger.info("YouTube API service built successfully.")
            return self._youtube
        except Exception as e:
            logger.error("Failed to build YouTube API service client: %s", e)
            raise

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "public"
    ) -> UploadResult:
        """
        Upload a clip to YouTube as Shorts.

        Args:
            video_path: Path to the video file.
            title: Clickbait title (max 100 characters).
            description: Video description.
            tags: List of video tags.
            privacy_status: "public", "unlisted", or "private".
        """
        # ── Check Daily Quota ───────────────────────────────────────────────
        try:
            from database import Database
            db = Database()
            uploads_today = db.count_uploads_today()
            db.close()
            
            max_allowed = getattr(config, "UPLOAD_MAX_PER_DAY", 6)
            if uploads_today >= max_allowed:
                msg = f"Daily upload quota reached ({uploads_today}/{max_allowed} uploads in the last 24h)."
                logger.warning(msg)
                return UploadResult(success=False, error=msg)
        except Exception as e:
            logger.error("Error checking daily uploads quota: %s", e)

        # Validate video file exists
        if not video_path.exists():
            msg = f"Video file not found at {video_path}"
            logger.error(msg)
            return UploadResult(success=False, error=msg)

        # Shorts auto tagging for description
        if "#Shorts" not in description:
            description = f"{description}\n\n#Shorts"

        # Initialize authenticated service
        try:
            youtube = self._get_authenticated_service()
        except (FileNotFoundError, ValueError) as e:
            # Suggest running auth_youtube.py for credentials issues
            err_msg = f"{str(e)} Please re-run auth_youtube.py to authenticate."
            logger.error(err_msg)
            return UploadResult(success=False, error=err_msg)
        except Exception as e:
            logger.error("YouTube API initialization failed: %s", e)
            return UploadResult(success=False, error=f"YouTube authentication failed: {e}")

        # Build media request body and upload
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": [t[:500] for t in tags] if tags else [],
                "categoryId": self.category_id
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        try:
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024
            )
            
            logger.info("Executing upload to YouTube: Part snippet,status for %s", video_path.name)
            response = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            ).execute()

            video_id = response.get("id", "")
            if not video_id:
                logger.error("YouTube response did not return a video ID: %s", response)
                return UploadResult(success=False, error="Upload succeeded but video ID was missing from API response.")

            video_url = f"https://youtube.com/shorts/{video_id}"
            logger.info("Successfully uploaded clip to YouTube! Video ID: %s, URL: %s", video_id, video_url)
            return UploadResult(success=True, video_id=video_id, video_url=video_url)

        except HttpError as e:
            logger.error("Google API HttpError during upload: %s", e.content, exc_info=True)
            err_details = str(e)
            if e.resp.status in [401, 403]:
                err_details += " (Authentication / API quota issue. Please check if your token is valid or re-run auth_youtube.py.)"
            return UploadResult(success=False, error=err_details)
        except Exception as e:
            logger.error("Unexpected exception during upload execution: %s", e, exc_info=True)
            return UploadResult(success=False, error=str(e))

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """
        Upload and set a custom thumbnail for a YouTube video.

        Args:
            video_id: The ID of the uploaded YouTube video.
            thumbnail_path: Path to the image file.
        """
        logger.info("Setting thumbnail for video %s to %s", video_id, thumbnail_path)
        if not thumbnail_path.exists():
            logger.error("Thumbnail file not found: %s", thumbnail_path)
            return False

        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        try:
            youtube = self._get_authenticated_service()
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
            logger.info("Successfully set custom thumbnail for video: %s", video_id)
            return True
        except HttpError as e:
            logger.error("Google API HttpError setting custom thumbnail: %s", e.content, exc_info=True)
            return False
        except Exception as e:
            logger.error("Failed to set thumbnail: %s", e, exc_info=True)
            return False
