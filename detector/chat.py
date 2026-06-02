"""
StreamClipper — Chat Burst Detector
Monitors Twitch WebSocket, YouTube API, and Kick Pusher for message spikes/bursts.
"""

import os
import time
import logging
import threading
import requests
from typing import Optional, List
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime

import config

logger = logging.getLogger("streamclipper.detector.chat")

# Popular chat emotes and expressions signaling hype moments
HIGHLIGHT_EMOTES = {
    "LUL", "KEKW", "LULW", "OMEGALUL", "PogChamp", "Pog", "PogU",
    "POGGERS", "Kreygasm", "PepeHands", "monkaS", "monkaW", "HYPERS",
    "catJAM", "EZ", "Clap", "ICANT", "LMAO", "💀", "😂", "W",
    "WWWWW", "NAHHHH", "NAH", "BRO", "CLIP", "CLIPIT", "LUL", "LOL"
}


@dataclass
class ChatEvent:
    """Represents a chat burst/hype event in a stream's chat room."""
    timestamp: float
    message_count: int  # Total messages in last 10s sliding window
    emote_count: int  # Total emote-heavy messages in last 10s
    event_type: str  # "burst", "normal", "spam"
    intensity: float  # Scale of 0-1

    @property
    def score(self) -> float:
        """Compatibility property for scorer that queries event.score."""
        return self.intensity


def parse_iso_timestamp(iso_str: Optional[str]) -> Optional[float]:
    """Parse ISO 8601 string to a unix timestamp float."""
    if not iso_str:
        return None
    try:
        clean_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str).timestamp()
    except Exception:
        return None


class BaseChatMonitor(ABC):
    """Abstract base class representing a platform-specific chat listener."""

    def __init__(self, streamer: config.StreamerConfig):
        self.streamer = streamer
        self.recent_events: List[ChatEvent] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._message_window: List[tuple[float, bool]] = []  # List of (timestamp, is_emote_heavy)

    @abstractmethod
    def start(self):
        """Start the background monitor listener."""
        pass

    @abstractmethod
    def stop(self):
        """Stop the background monitor listener."""
        pass

    def _on_message(self, timestamp: float, is_emote_heavy: bool):
        """Record a single message timestamp and compute rate/spikes."""
        with self._lock:
            self._message_window.append((timestamp, is_emote_heavy))
            # Keep sliding window of last 10 seconds
            cutoff = time.time() - 10.0
            self._message_window = [m for m in self._message_window if m[0] >= cutoff]

            # Calculate burst event
            event = self._calculate_burst()
            if event:
                self.recent_events.append(event)
                # Keep events for last 300 seconds (5 minutes)
                event_cutoff = time.time() - 300.0
                self.recent_events = [e for e in self.recent_events if e.timestamp >= event_cutoff]

    def _calculate_burst(self) -> Optional[ChatEvent]:
        """Verify message rate against thresholds to identify chat explosions."""
        recent = self._message_window
        if not recent:
            return None

        # Compute message rate per second (over 10s sliding window)
        msgs_per_sec = len(recent) / 10.0
        
        threshold = getattr(self.thresholds, "chat_msgs_per_sec", 5.0) if hasattr(self, "thresholds") else 5.0
        if msgs_per_sec < threshold:
            return None

        # Count emote occurrences in window
        emote_count = sum(1 for m in recent if m[1])
        emote_ratio = emote_count / len(recent) if len(recent) > 0 else 0

        # Calculate base intensity (threshold to max normalized at 20 msgs/s)
        intensity = msgs_per_sec / 20.0
        
        # Emote bonus (1.5x multiplier)
        if emote_ratio > 0.3:
            multiplier = getattr(self.thresholds, "chat_emote_multiplier", 1.5) if hasattr(self, "thresholds") else 1.5
            intensity *= multiplier

        intensity = min(1.0, intensity)

        # Classify the burst type
        event_type = "burst"
        if msgs_per_sec > 15.0:
            event_type = "spam"
        elif msgs_per_sec <= 5.0:
            event_type = "normal"

        event = ChatEvent(
            timestamp=time.time(),
            message_count=len(recent),
            emote_count=emote_count,
            event_type=event_type,
            intensity=intensity
        )
        logger.info(
            "Chat burst in #%s: %.1f msg/s (intensity=%.2f, emotes=%d/%d)",
            self.streamer.channel,
            msgs_per_sec,
            intensity,
            emote_count,
            len(recent),
        )
        return event

    def get_recent_events(self, last_n_seconds: float = 30.0) -> List[ChatEvent]:
        """Fetch filtered chat events within the specified time window."""
        with self._lock:
            cutoff = time.time() - last_n_seconds
            return [e for e in self.recent_events if e.timestamp >= cutoff]

    def clear_events(self):
        """Reset the cached events cache."""
        with self._lock:
            self.recent_events.clear()


class TwitchChatMonitor(BaseChatMonitor):
    """Twitch IRC WebSocket listener for real-time chat monitoring."""

    def __init__(self, streamer: config.StreamerConfig, thresholds: Optional[config.DetectionThresholds] = None):
        super().__init__(streamer)
        self.channel = streamer.channel.lower()
        self.thresholds = thresholds or config.thresholds

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[%s] Twitch chat monitor started", self.streamer.name)

    def stop(self):
        with self._lock:
            self._running = False
        logger.info("[%s] Twitch chat monitor stopped", self.streamer.name)

    def _run_loop(self):
        """Background thread executing connection and message parsing loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_loop())
        except Exception as e:
            logger.error("[%s] Twitch WebSocket loop error: %s", self.streamer.name, e)

    async def _ws_loop(self):
        import asyncio
        import websockets

        ws_url = "wss://irc-ws.chat.twitch.tv:443"
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    await ws.send("PASS oauth:anonymous")
                    await ws.send("NICK justinfan12345")
                    await ws.send(f"JOIN #{self.channel}")
                    logger.info("[%s] Connected to Twitch IRC WebSocket #%s", self.streamer.name, self.channel)

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            self._handle_raw(raw)
                        except asyncio.TimeoutError:
                            # Send standard IRC ping to maintain session
                            await ws.send("PING :tmi.twitch.tv")
                            continue
            except Exception as e:
                logger.warning("[%s] Twitch chat reconnecting in 5s: %s", self.streamer.name, e)
                if self._running:
                    await asyncio.sleep(5)

    def _handle_raw(self, raw: str):
        """Parse raw IRC lines from the WebSocket stream."""
        if raw.startswith("PING"):
            return

        if "PRIVMSG" in raw:
            parts = raw.split("PRIVMSG", 1)
            if len(parts) > 1:
                msg_parts = parts[1].split(":", 1)
                msg_text = msg_parts[1] if len(msg_parts) > 1 else ""
                
                # Check for popular hype emotes
                has_emote = any(e in msg_text.upper() for e in HIGHLIGHT_EMOTES)
                
                # Check for punctuation/all-caps/spammed emotes (>50% non-alphanumeric)
                non_alnum = sum(1 for c in msg_text if not c.isalnum() and not c.isspace())
                ratio_non_alnum = non_alnum / len(msg_text) if len(msg_text) > 0 else 0
                is_emote_heavy = has_emote or (ratio_non_alnum > 0.5)

                self._on_message(time.time(), is_emote_heavy)


class YouTubeChatMonitor(BaseChatMonitor):
    """YouTube liveChat/messages polling tracker."""

    def __init__(self, streamer: config.StreamerConfig, thresholds: Optional[config.DetectionThresholds] = None):
        super().__init__(streamer)
        self.thresholds = thresholds or config.thresholds
        self.api_key = os.getenv("YOUTUBE_API_KEY", "")
        self.live_chat_id = getattr(config, "YOUTUBE_LIVE_CHAT_ID", None)

    def start(self):
        if not self.api_key or not self.live_chat_id:
            logger.warning("[%s] YouTube chat monitor skipped (missing key or liveChatId)", self.streamer.name)
            return
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("[%s] YouTube chat monitor started", self.streamer.name)

    def stop(self):
        with self._lock:
            self._running = False
        logger.info("[%s] YouTube chat monitor stopped", self.streamer.name)

    def _poll_loop(self):
        """Continuous HTTP pooling of live chat messages."""
        next_page_token = None
        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"

        while self._running:
            try:
                params = {
                    "liveChatId": self.live_chat_id,
                    "part": "snippet,authorDetails",
                    "key": self.api_key,
                    "maxResults": 200,
                }
                if next_page_token:
                    params["pageToken"] = next_page_token

                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                next_page_token = data.get("nextPageToken")

                items = data.get("items", [])
                for item in items:
                    snippet = item.get("snippet", {})
                    msg_text = snippet.get("displayMessage", "")
                    published_at = snippet.get("publishedAt")
                    timestamp = parse_iso_timestamp(published_at) or time.time()

                    has_emote = any(e in msg_text.upper() for e in HIGHLIGHT_EMOTES)
                    non_alnum = sum(1 for c in msg_text if not c.isalnum() and not c.isspace())
                    ratio_non_alnum = non_alnum / len(msg_text) if len(msg_text) > 0 else 0
                    is_emote_heavy = has_emote or (ratio_non_alnum > 0.5)

                    self._on_message(timestamp, is_emote_heavy)
            except Exception as e:
                logger.error("[%s] YouTube chat polling error: %s", self.streamer.name, e)

            # Polling limit (5 seconds)
            time.sleep(5)


class KickChatMonitor(BaseChatMonitor):
    """Kick Pusher WebSocket listener."""

    def __init__(self, streamer: config.StreamerConfig, thresholds: Optional[config.DetectionThresholds] = None):
        super().__init__(streamer)
        self.thresholds = thresholds or config.thresholds

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[%s] Kick chat monitor started", self.streamer.name)

    def stop(self):
        with self._lock:
            self._running = False
        logger.info("[%s] Kick chat monitor stopped", self.streamer.name)

    def _run_loop(self):
        """Async event loop setup inside background thread."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_loop())
        except Exception as e:
            logger.error("[%s] Kick WebSocket loop error: %s", self.streamer.name, e)

    async def _ws_loop(self):
        import asyncio
        import json
        import websockets

        chatroom_id = await self._get_chatroom_id()
        if not chatroom_id:
            logger.error("[%s] Failed to resolve chatroom ID for Kick chat monitor.", self.streamer.name)
            return

        ws_url = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=7.6.0&flash=false"
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    # Send Pusher channel subscription request
                    sub_msg = json.dumps({
                        "event": "pusher:subscribe",
                        "data": {"channel": f"chatrooms.{chatroom_id}.v2"}
                    })
                    await ws.send(sub_msg)
                    logger.info("[%s] Connected to Kick chatroom channel chatrooms.%s.v2", self.streamer.name, chatroom_id)

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(raw)
                            if data.get("event") == "App\\Events\\ChatMessageEvent":
                                msg_data = json.loads(data.get("data", "{}"))
                                content = msg_data.get("content", "")
                                
                                has_emote = any(e in content.upper() for e in HIGHLIGHT_EMOTES)
                                non_alnum = sum(1 for c in content if not c.isalnum() and not c.isspace())
                                ratio_non_alnum = non_alnum / len(content) if len(content) > 0 else 0
                                is_emote_heavy = has_emote or (ratio_non_alnum > 0.5)

                                self._on_message(time.time(), is_emote_heavy)
                        except asyncio.TimeoutError:
                            # Send standard ping frame to keep session alive
                            await ws.ping()
                            continue
            except Exception as e:
                logger.warning("[%s] Kick chat reconnecting in 5s: %s", self.streamer.name, e)
                if self._running:
                    await asyncio.sleep(5)

    async def _get_chatroom_id(self) -> Optional[int]:
        """Fetch the internal chatroom ID required for channel subscriptions."""
        try:
            resp = requests.get(
                f"https://kick.com/api/v2/channels/{self.streamer.channel}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                return data.get("chatroom", {}).get("id")
        except Exception as e:
            logger.error("[%s] Failed to fetch Kick chatroom ID: %s", self.streamer.name, e)
        return None


def create_chat_monitor(streamer: config.StreamerConfig, thresholds: Optional[config.DetectionThresholds] = None) -> Optional[BaseChatMonitor]:
    """Factory function: initializes the appropriate chat monitor for the platform."""
    if streamer.platform == "twitch":
        return TwitchChatMonitor(streamer, thresholds)
    elif streamer.platform == "youtube":
        return YouTubeChatMonitor(streamer, thresholds)
    elif streamer.platform == "kick":
        return KickChatMonitor(streamer, thresholds)
    else:
        logger.warning("Unsupported chat platform: %s for %s", streamer.platform, streamer.name)
        return None
