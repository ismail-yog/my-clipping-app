"""
StreamClipper — Chat Burst Detector
Monitors Twitch IRC and Kick WebSocket for message/emote bursts.
"""

import time
import socket
import logging
import threading
from dataclasses import dataclass
from typing import Optional
from collections import deque

import config

logger = logging.getLogger("streamclipper.chat")

# Popular emotes that signal highlights
HIGHLIGHT_EMOTES = {
    "LUL", "KEKW", "LULW", "OMEGALUL", "PogChamp", "Pog", "PogU",
    "POGGERS", "Kreygasm", "PepeHands", "monkaS", "monkaW", "HYPERS",
    "catJAM", "EZ", "Clap", "ICANT", "LMAO", "💀", "😂", "W",
    "WWWWW", "NAHHHH", "NAH", "BRO", "CLIP", "CLIPIT",
}


@dataclass
class ChatEvent:
    timestamp: float
    messages_per_sec: float
    emote_ratio: float
    peak_msg_count: int
    window_seconds: float
    score: float


class TwitchChatMonitor:
    """Connects to Twitch IRC and tracks message rate."""

    def __init__(self, channel: str, thresholds: Optional[config.DetectionThresholds] = None):
        self.channel = channel.lower()
        self.thresholds = thresholds or config.thresholds
        self._messages: deque = deque(maxlen=5000)
        self._events: list[ChatEvent] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._analysis_thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()
        self._analysis_thread = threading.Thread(target=self._analyze_loop, daemon=True)
        self._analysis_thread.start()
        logger.info("Chat monitor started for #%s", self.channel)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        logger.info("Chat monitor stopped for #%s", self.channel)

    def _connect(self):
        """Connect to Twitch IRC as anonymous user."""
        while self._running:
            try:
                self._sock = socket.socket()
                self._sock.settimeout(10)
                self._sock.connect(("irc.chat.twitch.tv", 6667))
                self._sock.send(b"PASS SCHMOOPIIE\r\n")
                self._sock.send(b"NICK justinfan12345\r\n")  # Anonymous
                self._sock.send(f"JOIN #{self.channel}\r\n".encode())
                logger.info("Connected to Twitch IRC #%s", self.channel)
                self._read_loop()
            except Exception as e:
                logger.warning("IRC error for #%s: %s", self.channel, e)
                if self._running:
                    time.sleep(5)

    def _read_loop(self):
        buffer = ""
        while self._running:
            try:
                data = self._sock.recv(4096).decode("utf-8", errors="replace")
                if not data:
                    break
                buffer += data
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    self._handle_line(line)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug("IRC read error: %s", e)
                break

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            try:
                self._sock.send(b"PONG :tmi.twitch.tv\r\n")
            except Exception:
                pass
            return

        if "PRIVMSG" in line:
            # Extract message text
            parts = line.split("PRIVMSG", 1)
            if len(parts) > 1:
                msg_parts = parts[1].split(":", 1)
                msg_text = msg_parts[1] if len(msg_parts) > 1 else ""
                has_emote = any(e in msg_text.upper() for e in HIGHLIGHT_EMOTES)
                self._messages.append({
                    "time": time.time(),
                    "text": msg_text,
                    "has_emote": has_emote,
                })

    def _analyze_loop(self):
        """Periodically analyze message rate for bursts."""
        while self._running:
            try:
                event = self._check_burst()
                if event:
                    self._events.append(event)
                    logger.info(
                        "Chat burst in #%s: %.1f msg/s (score=%.2f)",
                        self.channel, event.messages_per_sec, event.score,
                    )
            except Exception as e:
                logger.debug("Chat analysis error: %s", e)
            time.sleep(2)

    def _check_burst(self) -> Optional[ChatEvent]:
        """Check if current message rate constitutes a burst."""
        now = time.time()
        window = 5.0  # 5-second sliding window

        recent = [m for m in self._messages if now - m["time"] <= window]
        if not recent:
            return None

        msg_rate = len(recent) / window
        emote_msgs = sum(1 for m in recent if m["has_emote"])
        emote_ratio = emote_msgs / len(recent) if recent else 0

        # Apply emote multiplier
        effective_rate = msg_rate * (1 + emote_ratio * (self.thresholds.chat_emote_multiplier - 1))

        if effective_rate < self.thresholds.chat_msgs_per_sec:
            return None

        # Normalize score: threshold = 0.5, 2x threshold = 1.0
        threshold = self.thresholds.chat_msgs_per_sec
        score = min(1.0, effective_rate / (threshold * 2))

        return ChatEvent(
            timestamp=now,
            messages_per_sec=msg_rate,
            emote_ratio=emote_ratio,
            peak_msg_count=len(recent),
            window_seconds=window,
            score=score,
        )

    @property
    def recent_events(self) -> list[ChatEvent]:
        cutoff = time.time() - 300
        return [e for e in self._events if e.timestamp >= cutoff]

    def clear_events(self):
        self._events.clear()


class KickChatMonitor:
    """Monitors Kick chat via WebSocket (Pusher protocol)."""

    def __init__(self, channel: str, thresholds: Optional[config.DetectionThresholds] = None):
        self.channel = channel.lower()
        self.thresholds = thresholds or config.thresholds
        self._messages: deque = deque(maxlen=5000)
        self._events: list[ChatEvent] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._connect, daemon=True)
        self._thread.start()
        logger.info("Kick chat monitor started for %s", self.channel)

    def stop(self):
        self._running = False

    def _connect(self):
        """Connect to Kick's Pusher WebSocket."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._ws_loop())
        except Exception as e:
            logger.error("Kick WS error: %s", e)

    async def _ws_loop(self):
        import json
        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed — Kick chat disabled")
            return

        # First, get the chatroom ID
        chatroom_id = await self._get_chatroom_id()
        if not chatroom_id:
            return

        ws_url = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.6.0&flash=false"
        while self._running:
            try:
                async with websockets.connect(ws_url) as ws:
                    # Subscribe to chatroom
                    sub_msg = json.dumps({
                        "event": "pusher:subscribe",
                        "data": {"channel": f"chatrooms.{chatroom_id}.v2"}
                    })
                    await ws.send(sub_msg)
                    logger.info("Subscribed to Kick chatroom %s", chatroom_id)

                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(raw)
                            if data.get("event") == "App\\Events\\ChatMessageEvent":
                                msg_data = json.loads(data.get("data", "{}"))
                                content = msg_data.get("content", "")
                                has_emote = any(e in content.upper() for e in HIGHLIGHT_EMOTES)
                                self._messages.append({
                                    "time": time.time(),
                                    "text": content,
                                    "has_emote": has_emote,
                                })
                        except asyncio.TimeoutError:
                            continue
            except Exception as e:
                logger.warning("Kick WS reconnecting: %s", e)
                if self._running:
                    await asyncio.sleep(5)

    async def _get_chatroom_id(self) -> Optional[int]:
        import aiohttp
        try:
            import requests as req
            resp = req.get(
                f"https://kick.com/api/v2/channels/{self.channel}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                return data.get("chatroom", {}).get("id")
        except Exception as e:
            logger.error("Failed to get Kick chatroom ID: %s", e)
        return None

    @property
    def recent_events(self) -> list[ChatEvent]:
        cutoff = time.time() - 300
        return [e for e in self._events if e.timestamp >= cutoff]

    def clear_events(self):
        self._events.clear()


def create_chat_monitor(streamer: config.StreamerConfig, thresholds=None):
    """Factory: create the right chat monitor for a streamer's platform."""
    if streamer.platform == "twitch":
        return TwitchChatMonitor(streamer.channel, thresholds)
    elif streamer.platform == "kick":
        return KickChatMonitor(streamer.channel, thresholds)
    else:
        logger.warning("No chat monitor for platform: %s", streamer.platform)
        return None
