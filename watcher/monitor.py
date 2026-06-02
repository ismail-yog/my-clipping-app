"""
StreamClipper — Stream Monitor
Polls Twitch, Kick, and YouTube APIs to detect when streamers go live.
"""

import time
import logging
import threading
from typing import Callable, Optional
from dataclasses import dataclass

import requests

import config

logger = logging.getLogger("streamclipper.monitor")


@dataclass
class StreamStatus:
    """Current status of a monitored streamer."""

    streamer: config.StreamerConfig
    is_live: bool = False
    title: str = ""
    game: str = ""
    viewer_count: int = 0
    started_at: str = ""
    thumbnail_url: str = ""
    last_checked: float = 0.0


class TwitchAuth:
    """Manages Twitch OAuth app access tokens."""

    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Get a valid app access token, refreshing if expired."""
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            return self._refresh_token()

    def _refresh_token(self) -> str:
        """Request a new app access token from Twitch."""
        logger.info("Refreshing Twitch app access token...")

        try:
            resp = requests.post(
                config.TWITCH_AUTH_URL,
                params={
                    "client_id": config.TWITCH_CLIENT_ID,
                    "client_secret": config.TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            self._token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 3600)

            logger.info(
                "Twitch token refreshed (expires in %ds)", data.get("expires_in", 0)
            )
            return self._token

        except requests.RequestException as e:
            logger.error("Failed to refresh Twitch token: %s", e)
            raise


class StreamMonitor:
    """
    Monitors multiple streamers across platforms and fires callbacks
    when they go live or offline.
    """

    def __init__(
        self,
        streamers: list[config.StreamerConfig],
        on_live: Optional[Callable[[StreamStatus], None]] = None,
        on_offline: Optional[Callable[[StreamStatus], None]] = None,
        poll_interval: int = 60,
    ):
        self.streamers = streamers
        self.on_live = on_live
        self.on_offline = on_offline
        self.poll_interval = poll_interval

        self._statuses: dict[str, StreamStatus] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._twitch_auth = TwitchAuth()

        # Initialize status tracking
        for s in streamers:
            key = f"{s.platform}:{s.channel}"
            self._statuses[key] = StreamStatus(streamer=s)

    @property
    def statuses(self) -> dict[str, StreamStatus]:
        """Return current status of all monitored streamers."""
        return dict(self._statuses)

    def start(self):
        """Start the monitoring loop in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Monitor started — watching %d streamers every %ds",
            len(self.streamers),
            self.poll_interval,
        )

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Monitor stopped")

    def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            for streamer in self.streamers:
                if not self._running:
                    break

                try:
                    self._check_streamer(streamer)
                except Exception as e:
                    logger.error(
                        "Error checking %s/%s: %s",
                        streamer.platform,
                        streamer.channel,
                        e,
                    )

            # Sleep in small increments so we can stop quickly
            for _ in range(self.poll_interval * 2):
                if not self._running:
                    break
                time.sleep(0.5)

    def _check_streamer(self, streamer: config.StreamerConfig):
        """Check a single streamer's live status."""
        key = f"{streamer.platform}:{streamer.channel}"
        status = self._statuses[key]

        if streamer.platform == "twitch":
            is_live, info = self._check_twitch(streamer.channel)
        elif streamer.platform == "kick":
            is_live, info = self._check_kick(streamer.channel)
        elif streamer.platform == "youtube":
            is_live, info = self._check_youtube(streamer.channel)
        else:
            logger.warning("Unknown platform: %s", streamer.platform)
            return

        was_live = status.is_live
        status.is_live = is_live
        status.last_checked = time.time()

        if info:
            status.title = info.get("title", "")
            status.game = info.get("game", "")
            status.viewer_count = info.get("viewer_count", 0)
            status.started_at = info.get("started_at", "")
            status.thumbnail_url = info.get("thumbnail_url", "")

        # Fire callbacks on state change
        if is_live and not was_live:
            logger.info(
                "🟢 %s is LIVE on %s: %s",
                streamer.name,
                streamer.platform,
                status.title,
            )
            if self.on_live:
                self.on_live(status)

        elif not is_live and was_live:
            logger.info(
                "🔴 %s went OFFLINE on %s", streamer.name, streamer.platform
            )
            if self.on_offline:
                self.on_offline(status)

    # ── Twitch ──────────────────────────────────────────────────────────────

    def _check_twitch(self, channel: str) -> tuple[bool, Optional[dict]]:
        """Check if a Twitch channel is live using the Helix API."""
        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return False, None

        token = self._twitch_auth.get_token()
        headers = {
            "Client-Id": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }

        resp = requests.get(
            f"{config.TWITCH_HELIX_URL}/streams",
            params={"user_login": channel},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if data:
            stream = data[0]
            return True, {
                "title": stream.get("title", ""),
                "game": stream.get("game_name", ""),
                "viewer_count": stream.get("viewer_count", 0),
                "started_at": stream.get("started_at", ""),
                "thumbnail_url": stream.get("thumbnail_url", ""),
            }

        return False, None

    # ── Kick ────────────────────────────────────────────────────────────────

    def _check_kick(self, channel: str) -> tuple[bool, Optional[dict]]:
        """
        Check if a Kick channel is live.
        Uses the unofficial public API — may break without notice.
        """
        try:
            resp = requests.get(
                f"https://kick.com/api/v2/channels/{channel}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            livestream = data.get("livestream")
            if livestream and livestream.get("is_live"):
                return True, {
                    "title": livestream.get("session_title", ""),
                    "game": livestream.get("categories", [{}])[0].get("name", "")
                    if livestream.get("categories")
                    else "",
                    "viewer_count": livestream.get("viewer_count", 0),
                    "started_at": livestream.get("created_at", ""),
                }

            return False, None

        except requests.RequestException as e:
            logger.debug("Kick API error for %s: %s", channel, e)
            return False, None

    # ── YouTube ─────────────────────────────────────────────────────────────

    def _check_youtube(self, channel_id: str) -> tuple[bool, Optional[dict]]:
        """
        Check if a YouTube channel is live.
        Uses yt-dlp to avoid needing a separate YouTube API key for monitoring.
        """
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }

            url = f"https://www.youtube.com/channel/{channel_id}/live"

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if info and info.get("is_live"):
                    return True, {
                        "title": info.get("title", ""),
                        "viewer_count": info.get("concurrent_view_count", 0),
                        "started_at": "",
                    }

            return False, None

        except Exception as e:
            logger.debug("YouTube check error for %s: %s", channel_id, e)
            return False, None

    def check_now(self) -> dict[str, StreamStatus]:
        """Force an immediate check of all streamers. Returns statuses."""
        for streamer in self.streamers:
            try:
                self._check_streamer(streamer)
            except Exception as e:
                logger.error("Error checking %s: %s", streamer.name, e)
        return self.statuses
