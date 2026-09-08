"""
StreamClipper — Autonomous Social Upload Workers
Production-grade multi-platform upload engine integrating YouTube Shorts
via Google API Client with HTTP/HTTPS residential proxy tunneling, and TikTok
via isolated Playwright browser profiles with dedicated proxy routing.
"""

import asyncio
import json
import logging
import os
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, Union

import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger("streamclipper.upload_worker")


class UploadWorkerError(Exception):
    """Raised when social upload operations fail."""
    pass


class SocialUploadWorker:
    """
    Autonomous upload worker for YouTube Shorts and TikTok with proxy isolation.
    """

    def __init__(self, proxy_url: Optional[str] = None):
        """
        proxy_url format:
            "http://user:password@residential-node.proxy.com:8000"
            or "http://residential-node.proxy.com:8000"
        """
        self.proxy_url = proxy_url.strip() if proxy_url else None
        self._parsed_proxy = urllib.parse.urlparse(self.proxy_url) if self.proxy_url else None

    def _get_http_transport(self, credentials: Optional[Credentials] = None) -> httplib2.Http:
        """
        Configures an authenticated or unauthenticated httplib2.Http instance
        with proxy tunneling if configured.
        """
        if self._parsed_proxy and self._parsed_proxy.hostname:
            proxy_type = (
                httplib2.socks.PROXY_TYPE_SOCKS5
                if self._parsed_proxy.scheme.startswith("socks")
                else httplib2.socks.PROXY_TYPE_HTTP
            )
            proxy_port = self._parsed_proxy.port or (443 if self._parsed_proxy.scheme == "https" else 80)
            
            proxy_info = httplib2.ProxyInfo(
                proxy_type=proxy_type,
                proxy_host=self._parsed_proxy.hostname,
                proxy_port=proxy_port,
                proxy_user=self._parsed_proxy.username or None,
                proxy_pass=self._parsed_proxy.password or None,
            )
            base_http = httplib2.Http(proxy_info=proxy_info, timeout=120)
        else:
            base_http = httplib2.Http(timeout=120)

        if credentials is not None:
            return credentials.authorize(base_http)
        return base_http

    def upload_youtube_short(
        self,
        video_path: Union[str, Path],
        title: str,
        description: str,
        token_info: Dict[str, Any],
        category_id: str = "20",
        privacy_status: str = "public",
    ) -> str:
        """
        Uploads vertical video directly to YouTube Shorts via Data API v3 over proxy.
        Returns the published YouTube Video ID.
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists() or video_path.stat().st_size == 0:
            raise UploadWorkerError(f"Video file missing or empty: {video_path}")

        try:
            credentials = Credentials(
                token=token_info.get("access_token"),
                refresh_token=token_info.get("refresh_token"),
                token_uri=token_info.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_info.get("client_id"),
                client_secret=token_info.get("client_secret"),
            )

            http = self._get_http_transport(credentials)
            youtube = build("youtube", "v3", http=http, cache_discovery=False)

            # Ensure #Shorts tag in description and title length <= 100
            clean_title = title.strip()[:100]
            clean_desc = f"{description.strip()}\n\n#Shorts".strip()

            body = {
                "snippet": {
                    "title": clean_title,
                    "description": clean_desc,
                    "categoryId": category_id,  # Gaming default
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 5,  # 5MB chunks
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            logger.info("Starting resumable YouTube Short upload: '%s'", clean_title)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.debug("YouTube upload progress: %d%%", progress)

            video_id = response.get("id")
            if not video_id:
                raise UploadWorkerError(f"Upload completed but no video ID returned: {response}")

            logger.info("YouTube Short successfully uploaded. ID: %s", video_id)
            return video_id

        except HttpError as http_err:
            logger.error("YouTube API HTTP error: %s", http_err)
            raise UploadWorkerError(f"YouTube API error: {http_err}") from http_err
        except Exception as exc:
            logger.error("Failed to upload YouTube Short: %s", exc, exc_info=True)
            raise UploadWorkerError(f"YouTube upload failed: {exc}") from exc

    async def upload_tiktok_clip(
        self,
        video_path: Union[str, Path],
        caption: str,
        cookies_json_path: Union[str, Path],
        timeout_ms: int = 120000,
    ) -> bool:
        """
        Automates headless browser session upload for TikTok with residential proxy isolation.
        Injects session cookies and waits for upload verification.
        """
        video_path = Path(video_path).resolve()
        cookies_json_path = Path(cookies_json_path).resolve()

        if not video_path.exists():
            raise UploadWorkerError(f"TikTok video file not found: {video_path}")
        if not cookies_json_path.exists():
            raise UploadWorkerError(f"TikTok session cookies file not found: {cookies_json_path}")

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise UploadWorkerError("playwright is required for TikTok automation. Run: pip install playwright") from e

        with open(cookies_json_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        async with async_playwright() as p:
            proxy_dict = None
            if self.proxy_url:
                proxy_dict = {"server": self.proxy_url}

            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy_dict,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                )

                # Inject authenticated session cookies
                await context.add_cookies(cookies)
                page = await context.new_page()

                logger.info("Navigating to TikTok Creator upload page...")
                await page.goto(
                    "https://www.tiktok.com/creator-center/upload?from=upload",
                    wait_until="networkidle",
                    timeout=timeout_ms,
                )

                # Select and attach video file via file input
                file_input = page.locator('input[type="file"]')
                await file_input.wait_for(state="attached", timeout=timeout_ms)
                await file_input.set_input_files(str(video_path))
                logger.info("Attached video file to TikTok input")

                # Fill caption container
                caption_box = page.locator('div[contenteditable="true"]')
                await caption_box.wait_for(state="visible", timeout=timeout_ms)
                await caption_box.fill(caption)

                # Click post button
                post_button = page.locator('button:has-text("Post")')
                await post_button.wait_for(state="visible", timeout=timeout_ms)
                await post_button.click()
                logger.info("Clicked TikTok post button, waiting for confirmation...")

                # Await upload confirmation banner/modal
                await page.wait_for_selector(
                    'text="Your video has been uploaded", text="Uploaded", text="Manage your posts"',
                    timeout=timeout_ms,
                )
                logger.info("TikTok clip upload confirmed")
                return True

            except Exception as e:
                logger.error("TikTok automated upload failed: %s", e, exc_info=True)
                raise UploadWorkerError(f"TikTok automated upload failed: {e}") from e
            finally:
                await browser.close()
