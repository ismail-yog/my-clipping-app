"""
StreamClipper — Stream Monitor
Polls Twitch, YouTube, and Kick APIs to check live status and trigger clipping workflows.
"""

import os
import time
import logging
import threading
from typing import Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime
import requests

import config

logger = logging.getLogger("streamclipper.monitor")


@dataclass
class StreamStatus:
    """Current live status of a monitored streamer."""
    streamer: config.StreamerConfig
    is_live: bool = False
    title: str = ""
    game: str = ""
    viewer_count: int = 0
    started_at: Optional[float] = None
    thumbnail_url: str = ""
    stream_url: str = ""
    last_checked: float = 0.0


@dataclass
class MonitorStats:
    """Statistics tracked by the StreamMonitor."""
    total_checks: int = 0
    live_streams: int = 0
    api_errors: int = 0
    last_check_time: float = 0.0
    uptime_start: float = field(default_factory=time.time)


def parse_iso_timestamp(iso_str: Optional[str]) -> Optional[float]:
    """Parse ISO 8601 string to a unix timestamp float."""
    if not iso_str:
        return None
    try:
        # standard ISO timestamp parsing (replace Z with +00:00)
        clean_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        return dt.timestamp()
    except Exception as e:
        logger.debug("Failed to parse ISO timestamp %s: %s", iso_str, e)
        return None


class TwitchAPI:
    """Twitch API client using Helix and Client Credentials Flow."""

    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()
        self._user_id_cache: dict[str, str] = {}

    def _get_token(self) -> str:
        """Get or refresh the app access token, refreshing 5 minutes before expiry."""
        with self._lock:
            # Refresh if token doesn't exist or expires in less than 5 minutes
            if self._token and time.time() < self._expires_at - 300:
                return self._token

            logger.info("Refreshing Twitch app access token...")
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

    def lookup_user_id(self, login: str) -> Optional[str]:
        """Resolve a Twitch user ID by their login name using Helix /users."""
        if login in self._user_id_cache:
            return self._user_id_cache[login]

        token = self._get_token()
        headers = {
            "Client-ID": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        resp = requests.get(
            f"{config.TWITCH_HELIX_URL}/users",
            params={"login": login},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            user_id = data[0]["id"]
            self._user_id_cache[login] = user_id
            return user_id
        return None

    def check_stream(self, channel: str) -> tuple[bool, Optional[dict]]:
        """Check if streamer is live using Helix /streams."""
        user_id = self.lookup_user_id(channel)
        if not user_id:
            return False, None

        token = self._get_token()
        headers = {
            "Client-ID": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        resp = requests.get(
            f"{config.TWITCH_HELIX_URL}/streams",
            params={"user_id": user_id},
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
                "started_at": parse_iso_timestamp(stream.get("started_at")),
                "thumbnail_url": stream.get("thumbnail_url", ""),
                "stream_url": f"https://www.twitch.tv/{channel}",
            }
        return False, None


class YouTubeAPI:
    """YouTube API client using official Data API v3 search endpoint."""

    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY", "")

    def check_stream(self, channel_id: str) -> tuple[bool, Optional[dict]]:
        """Check if channel is live using YouTube Data API v3."""
        if not self.api_key:
            logger.warning("YOUTUBE_API_KEY env var not set. YouTube check skipped.")
            return False, None

        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "eventType": "live",
            "type": "video",
            "key": self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            item = items[0]
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId", "")
            started_at_str = snippet.get("publishedAt")
            return True, {
                "title": snippet.get("title", ""),
                "game": "Live Stream",
                "viewer_count": 0,  # Returns 0 as search endpoint does not return live stats
                "started_at": parse_iso_timestamp(started_at_str),
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "stream_url": f"https://www.youtube.com/watch?v={video_id}",
            }
        return False, None


class KickAPI:
    """Kick API client using stable public v2 channels endpoint."""

    def check_stream(self, channel: str) -> tuple[bool, Optional[dict]]:
        """Check if channel is live using Kick v2 endpoint."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(
            f"https://kick.com/api/v2/channels/{channel}",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        livestream = data.get("livestream")
        if livestream and livestream.get("is_live"):
            return True, {
                "title": livestream.get("session_title", ""),
                "game": livestream.get("categories", [{}])[0].get("name", "") if livestream.get("categories") else "",
                "viewer_count": livestream.get("viewer_count", 0),
                "started_at": parse_iso_timestamp(livestream.get("created_at")),
                "thumbnail_url": livestream.get("thumbnail", {}).get("url", ""),
                "stream_url": f"https://kick.com/{channel}",
            }
        return False, None


class StreamMonitor:
    """Autonomous stream monitor that coordinates platform APIs and callback state transitions."""

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
        self._lock = threading.Lock()

        self._stats = MonitorStats()

        # Clients
        self._twitch_api = TwitchAPI()
        self._youtube_api = YouTubeAPI()
        self._kick_api = KickAPI()

        # Initialize status tracking dictionary
        with self._lock:
            for s in streamers:
                key = f"{s.platform}:{s.channel}"
                self._statuses[key] = StreamStatus(streamer=s, stream_url=s.url)

    @property
    def is_running(self) -> bool:
        """Indicate if the monitoring thread is actively running."""
        with self._lock:
            return self._running

    @property
    def statuses(self) -> dict[str, StreamStatus]:
        """Return a copy of the tracked stream statuses."""
        with self._lock:
            return dict(self._statuses)

    @property
    def stats(self) -> MonitorStats:
        """Return current monitor statistics."""
        with self._lock:
            # Refresh live streams count dynamically
            self._stats.live_streams = sum(1 for s in self._statuses.values() if s.is_live)
            return self._stats

    def get_all_statuses(self) -> list[StreamStatus]:
        """Get the statuses of all monitored streamers."""
        with self._lock:
            return list(self._statuses.values())

    def get_live_statuses(self) -> list[StreamStatus]:
        """Get the statuses of only the currently live streamers."""
        with self._lock:
            return [s for s in self._statuses.values() if s.is_live]

    def start(self):
        """Start the background polling loop."""
        with self._lock:
            if self._running:
                return
            self._running = True

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(
            "StreamMonitor started — watching %d streamers every %ds",
            len(self.streamers),
            self.poll_interval,
        )

    def stop(self):
        """Gracefully stop the background polling loop."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("StreamMonitor stopped")

    def check_now(self) -> dict[str, StreamStatus]:
        """Force an immediate status check on all streamers."""
        for streamer in self.streamers:
            if streamer.enabled:
                try:
                    self._check_streamer(streamer)
                except Exception as e:
                    logger.error("Error during manual check for %s: %s", streamer.name, e)
                    with self._lock:
                        self._stats.api_errors += 1
        return self.statuses

    def _poll_loop(self):
        """Run loop executing inside background thread."""
        while True:
            with self._lock:
                if not self._running:
                    break

            for streamer in self.streamers:
                with self._lock:
                    if not self._running:
                        break
                if streamer.enabled:
                    try:
                        self._check_streamer(streamer)
                    except Exception as e:
                        logger.error("Unexpected error in poll loop for %s: %s", streamer.name, e)
                        with self._lock:
                            self._stats.api_errors += 1

            # Sleep in 1s chunks to stay responsive to stop requests
            for _ in range(self.poll_interval):
                with self._lock:
                    if not self._running:
                        break
                time.sleep(1)

    def _check_streamer(self, streamer: config.StreamerConfig):
        """Check status of a single streamer and trigger callbacks on transitions."""
        key = f"{streamer.platform}:{streamer.channel}"

        with self._lock:
            status = self._statuses[key]
            was_live = status.is_live

        is_live = False
        info = None

        try:
            if streamer.platform == "twitch":
                is_live, info = self._twitch_api.check_stream(streamer.channel)
            elif streamer.platform == "youtube":
                is_live, info = self._youtube_api.check_stream(streamer.channel)
            elif streamer.platform == "kick":
                is_live, info = self._kick_api.check_stream(streamer.channel)
            else:
                logger.warning("Unknown streamer platform %s for %s", streamer.platform, streamer.name)
                return
        except Exception as e:
            logger.error("API error checking %s (%s): %s", streamer.name, streamer.platform, e)
            with self._lock:
                self._stats.api_errors += 1
            return

        with self._lock:
            self._stats.total_checks += 1
            self._stats.last_check_time = time.time()

            status.is_live = is_live
            status.last_checked = time.time()

            if is_live and info:
                status.title = info.get("title", "")
                status.game = info.get("game", "")
                status.viewer_count = info.get("viewer_count", 0)
                status.started_at = info.get("started_at")
                status.thumbnail_url = info.get("thumbnail_url", "")
                status.stream_url = info.get("stream_url", streamer.url)
            else:
                # Reset details on offline
                status.title = ""
                status.game = ""
                status.viewer_count = 0
                status.started_at = None
                status.thumbnail_url = ""
                status.stream_url = streamer.url

        # Check and execute state transition callbacks outside of lock
        if is_live and not was_live:
            logger.info("🟢 %s is LIVE on %s: %s", streamer.name, streamer.platform, status.title)
            if self.on_live:
                try:
                    self.on_live(status)
                except Exception as e:
                    logger.error("Error in on_live callback for %s: %s", streamer.name, e)
        elif not is_live and was_live:
            logger.info("🔴 %s went OFFLINE on %s", streamer.name, streamer.platform)
            if self.on_offline:
                try:
                    self.on_offline(status)
                except Exception as e:
                    logger.error("Error in on_offline callback for %s: %s", streamer.name, e)


if __name__ == "__main__":
    # Monitor logger output to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s"
    )

    test_streamers = [
        config.StreamerConfig(
            name="Kai Cenat",
            platform="twitch",
            channel="kaicenat",
            url="https://www.twitch.tv/kaicenat"
        ),
        config.StreamerConfig(
            name="Jinnytty",
            platform="twitch",
            channel="jinnytty",
            url="https://www.twitch.tv/jinnytty"
        )
    ]

    def test_on_live(status: StreamStatus):
        print(f"[{status.streamer.name}] Callback: Stream went LIVE! Title: {status.title}")

    def test_on_offline(status: StreamStatus):
        print(f"[{status.streamer.name}] Callback: Stream went OFFLINE!")

    print("--- Starting Monitor Test (2 Minutes) ---")
    mon = StreamMonitor(
        streamers=test_streamers,
        on_live=test_on_live,
        on_offline=test_on_offline,
        poll_interval=10
    )
    mon.start()

    start_time = time.time()
    try:
        while time.time() - start_time < 120:
            time.sleep(10)
            stats = mon.stats
            print(f"[TEST STATS] Checks: {stats.total_checks} | Live: {stats.live_streams} | Errors: {stats.api_errors}")
    except KeyboardInterrupt:
        pass
    finally:
        mon.stop()
        print("--- Test Completed ---")
