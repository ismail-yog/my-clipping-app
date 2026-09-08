"""
StreamClipper — YouTube Uploader
Uploads clips to YouTube as Shorts with multi-account sequential failover and quota cascade.

Rules:
1. Exclusivity: One clip is ONLY uploaded to ONE account. Never duplicated.
2. Sequential Cascade: Prioritizes Account 1. Once Account 1 daily limit or quota is exhausted,
   automatically fails over to Account 2, then Account 3.
"""

import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger("streamclipper.uploader.youtube")


@dataclass
class UploadResult:
    """Dataclass representing the outcome of a YouTube upload attempt."""
    success: bool
    video_id: str = ""
    video_url: str = ""
    error: str = ""
    account_id: str = "account1"


class YouTubeUploader:
    """Multi-Account YouTube Uploader with sequential quota failover."""

    def __init__(self, token_file: Optional[str] = None, client_secrets_file: Optional[str] = None):
        self.scopes = config.YOUTUBE_SCOPES
        self.client_secrets_file = client_secrets_file or config.YOUTUBE_CLIENT_SECRETS
        self.token_file = token_file or config.YOUTUBE_TOKEN_FILE
        self.category_id = getattr(config, "YOUTUBE_CATEGORY_ID", "22")
        self._services_cache: Dict[str, Any] = {}
        logger.info("YouTubeUploader initialized.")

    def _discover_accounts(self) -> List[Dict[str, Any]]:
        """Discover all configured accounts in sequential priority order."""
        ordered_ids = ["account1", "account2", "account3"]

        # Detect additional client_secrets_account*.json or youtube_token_account*.json
        for path in config.BASE_DIR.glob("client_secrets_account*.json"):
            match = re.search(r"client_secrets_account(\d+)\.json", path.name)
            if match:
                aid = f"account{match.group(1)}"
                if aid not in ordered_ids:
                    ordered_ids.append(aid)

        def sort_key(aid: str) -> int:
            digits = "".join(filter(str.isdigit, aid))
            return int(digits) if digits else 999

        ordered_ids.sort(key=sort_key)

        accounts = []
        for aid in ordered_ids:
            if aid == "account1":
                accounts.append({
                    "id": "account1",
                    "name": "Account 1 (Primary)",
                    "secrets_path": Path(config.YOUTUBE_CLIENT_SECRETS),
                    "token_path": Path(config.YOUTUBE_TOKEN_FILE),
                })
            elif aid == "account2":
                accounts.append({
                    "id": "account2",
                    "name": "Account 2",
                    "secrets_path": Path(getattr(config, "YOUTUBE_ACCOUNT_2_CLIENT_SECRETS", "client_secrets_account2.json")),
                    "token_path": Path(getattr(config, "YOUTUBE_ACCOUNT_2_TOKEN_FILE", "youtube_token_account2.json")),
                })
            elif aid == "account3":
                accounts.append({
                    "id": "account3",
                    "name": "Account 3",
                    "secrets_path": Path(getattr(config, "YOUTUBE_ACCOUNT_3_CLIENT_SECRETS", "client_secrets_account3.json")),
                    "token_path": Path(getattr(config, "YOUTUBE_ACCOUNT_3_TOKEN_FILE", "youtube_token_account3.json")),
                })
            else:
                num_str = "".join(filter(str.isdigit, aid))
                suffix = f"_account{num_str}" if num_str else f"_{aid}"
                accounts.append({
                    "id": aid,
                    "name": f"Account {num_str or aid.title()}",
                    "secrets_path": config.BASE_DIR / f"client_secrets{suffix}.json",
                    "token_path": config.BASE_DIR / f"youtube_token{suffix}.json",
                })
        return accounts

    def _get_service_for_account(self, account: Dict[str, Any]):
        """Build and authenticate a YouTube API client for a given account."""
        aid = account["id"]
        token_path: Path = account["token_path"]

        if aid in self._services_cache:
            return self._services_cache[aid]

        if not token_path.exists():
            raise FileNotFoundError(f"Token file missing for {account['name']}: {token_path}")

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        import googleapiclient.discovery

        try:
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)
        except Exception as e:
            logger.error("Failed to load credentials from %s: %s", token_path, e)
            raise ValueError(f"Invalid credentials file for {account['name']}: {e}")

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token for %s...", account["name"])
                creds.refresh(Request())
                token_path.write_text(creds.to_json(), encoding="utf-8")
                logger.info("Token refreshed successfully for %s.", account["name"])
            else:
                raise ValueError(f"Credentials for {account['name']} are invalid and missing refresh_token.")

        service = googleapiclient.discovery.build("youtube", "v3", credentials=creds, cache_discovery=False)
        self._services_cache[aid] = service
        return service

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "public",
        preferred_account_id: Optional[str] = None,
    ) -> UploadResult:
        """
        Upload a clip to YouTube as a Short.
        Guarantees:
        1. Exclusivity: Single upload only. Returns immediately upon first success.
        2. Sequential Quota Failover: Account 1 -> Account 2 -> Account 3 cascade.
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists() or video_path.stat().st_size == 0:
            return UploadResult(success=False, error=f"Video file not found or empty: {video_path}")

        # Ensure #Shorts tag is present
        if "#Shorts" not in description:
            description = f"{description}\n\n#Shorts"

        all_accounts = self._discover_accounts()

        # Filter to accounts with token files
        eligible_accounts = [a for a in all_accounts if a["token_path"].exists()]

        if not eligible_accounts:
            return UploadResult(
                success=False,
                error="No authenticated YouTube accounts found. Connect an account in Settings to enable uploads.",
            )

        from database import Database
        db = Database()
        max_per_account = getattr(config, "UPLOAD_MAX_PER_DAY", 6)

        # Balanced multi-account distribution (6 uploads per account daily = 18 total)
        # Prioritize accounts that have NOT yet reached max_per_account (6),
        # ordered by fewest uploads today so all accounts receive videos evenly.
        def account_sort_key(acc: Dict[str, Any]) -> tuple:
            aid = acc["id"]
            uploads_today = db.count_uploads_today(account_id=aid)
            is_full = (uploads_today >= max_per_account)
            is_preferred = (aid == preferred_account_id) if preferred_account_id else False
            return (is_full, -1 if is_preferred else 0, uploads_today, aid)

        eligible_accounts.sort(key=account_sort_key)

        attempted_accounts = []
        last_error = ""

        for acc in eligible_accounts:
            aid = acc["id"]
            name = acc["name"]
            attempted_accounts.append(name)

            # 1. Check local daily upload limit for this specific account
            uploads_today = db.count_uploads_today(account_id=aid)
            if uploads_today >= max_per_account:
                logger.info(
                    "Account %s reached daily upload limit (%d/%d uploads). Cascading to next available account...",
                    name, uploads_today, max_per_account,
                )
                continue

            # 2. Attempt upload using this account
            logger.info("Dispatching clip upload to %s (%d/%d uploads today)...", name, uploads_today, max_per_account)
            res = self._execute_upload(
                account=acc,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy_status,
            )

            # Exclusivity: if successful, return immediately! Never upload again!
            if res.success:
                logger.info("Successfully uploaded clip to %s! Video ID: %s (URL: %s)", name, res.video_id, res.video_url)
                db.close()
                return res

            # Check if failure was quota or rate-limit related
            err_lower = res.error.lower()
            is_quota_issue = any(
                keyword in err_lower
                for keyword in [
                    "uploadlimitexceeded",
                    "quotaexceeded",
                    "upload limit",
                    "quota",
                    "exceeded the number of videos",
                    "daily limit",
                ]
            )

            last_error = res.error
            if is_quota_issue:
                logger.warning(
                    "%s reached daily YouTube API quota / upload limit: %s. Cascading to next account...",
                    name, res.error,
                )
                continue
            else:
                # Non-quota failure (e.g. video rendering issue, bad metadata)
                logger.error("Upload execution failed on %s: %s", name, res.error)
                db.close()
                return res

        total_today = sum(db.count_uploads_today(account_id=a["id"]) for a in eligible_accounts)
        db.close()
        return UploadResult(
            success=False,
            error=f"Daily upload capacity reached across all {len(eligible_accounts)} accounts ({total_today}/{len(eligible_accounts) * max_per_account} uploads today). Last error: {last_error or 'Daily quota reached'}",
        )

    def _execute_upload(
        self,
        account: Dict[str, Any],
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str,
    ) -> UploadResult:
        """Execute the actual API call against the specified account."""
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
        import json

        aid = account["id"]
        try:
            youtube = self._get_service_for_account(account)
        except Exception as e:
            logger.warning("Could not initialize service for %s: %s", account["name"], e)
            return UploadResult(success=False, error=str(e), account_id=aid)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": [t[:500] for t in tags] if tags else [],
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        try:
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024,
            )

            response = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            ).execute()

            video_id = response.get("id", "")
            if not video_id:
                return UploadResult(
                    success=False,
                    error="Upload succeeded but video ID was missing from API response.",
                    account_id=aid,
                )

            video_url = f"https://youtube.com/shorts/{video_id}"
            return UploadResult(success=True, video_id=video_id, video_url=video_url, account_id=aid)

        except HttpError as e:
            err_details = str(e)
            try:
                raw = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
                err_data = json.loads(raw)
                errors = err_data.get("error", {}).get("errors", [])
                reasons = [item.get("reason") for item in errors if "reason" in item]
                messages = [item.get("message") for item in errors if "message" in item]

                if "uploadLimitExceeded" in reasons:
                    err_details = "YouTube Daily Upload Limit Exceeded (uploadLimitExceeded)."
                elif "quotaExceeded" in reasons:
                    err_details = "YouTube API Quota Exceeded (quotaExceeded - 10,000 units/day)."
                elif messages:
                    err_details = "; ".join(messages)
            except Exception:
                pass
            return UploadResult(success=False, error=err_details, account_id=aid)

        except Exception as e:
            return UploadResult(success=False, error=str(e), account_id=aid)

    def set_thumbnail(self, video_id: str, thumbnail_path: Path, account_id: str = "account1") -> bool:
        """Upload custom thumbnail using the account that published the video."""
        if not thumbnail_path.exists():
            return False

        from googleapiclient.http import MediaFileUpload
        all_accounts = self._discover_accounts()
        account = next((a for a in all_accounts if a["id"] == account_id), None)
        if not account or not account["token_path"].exists():
            account = next((a for a in all_accounts if a["token_path"].exists()), None)
        if not account:
            return False

        try:
            youtube = self._get_service_for_account(account)
            media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
            youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
            logger.info("Custom thumbnail set for video %s on %s", video_id, account["name"])
            return True
        except Exception as e:
            logger.warning("Failed to set thumbnail on %s: %s", account["name"], e)
            return False
