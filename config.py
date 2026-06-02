"""
StreamClipper — Central Configuration
Loads settings from .env and provides typed access to all config values.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# ── Load .env ───────────────────────────────────────────────────────────────

load_dotenv()

# ── Paths ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.resolve()
CLIPS_DIR = BASE_DIR / "clips"
LOGS_DIR = BASE_DIR / "logs"
THUMBS_DIR = BASE_DIR / "thumbs"
RAW_DIR = BASE_DIR / "raw"
SHORTS_DIR = BASE_DIR / "shorts"
TEMP_MEDIA_DIR = BASE_DIR / "temp"

for d in [CLIPS_DIR, LOGS_DIR, THUMBS_DIR, RAW_DIR, SHORTS_DIR, TEMP_MEDIA_DIR]:
    d.mkdir(exist_ok=True)

# ── Logging Setup ───────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "streamclipper.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger("streamclipper")


# ── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class StreamerConfig:
    """Configuration for a single streamer to monitor."""

    name: str
    platform: str  # "twitch", "kick", "youtube"
    channel: str  # Username or channel ID
    url: str  # Full URL to the stream
    enabled: bool = True
    auto_approve: bool = False  # Auto-approve clips without review


@dataclass
class DetectionThresholds:
    """Thresholds that control when highlights are detected."""

    # Audio spike detection
    audio_rms_spike_db: float = 6.0  # dB above rolling average
    audio_weight: float = 0.3

    # Chat burst detection
    chat_msgs_per_sec: float = 5.0  # Messages per second threshold
    chat_emote_multiplier: float = 1.5  # Bonus for emote-heavy bursts
    chat_weight: float = 0.4

    # Sentiment detection
    sentiment_min_confidence: float = 0.6
    sentiment_emotions: list = field(
        default_factory=lambda: ["joy", "anger", "surprise"]
    )
    sentiment_weight: float = 0.3

    # Overall scoring
    moment_threshold: float = 0.40  # Score 0-1 to trigger a clip
    cooldown_seconds: float = 60.0  # Minimum gap between clips


@dataclass
class ClipSettings:
    """Settings for clip extraction and formatting."""

    min_duration: int = 30  # seconds
    max_duration: int = 90  # seconds
    default_duration: int = 60  # seconds
    output_width: int = 1080  # 9:16 portrait
    output_height: int = 1920
    output_fps: int = 30
    output_format: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 23  # Quality (lower = better, 18-28 typical)

    # Caption styling
    caption_font: str = "Arial"
    caption_font_size: int = 48
    caption_color: str = "&H00FFFFFF"  # ASS white
    caption_outline_color: str = "&H00000000"  # ASS black
    caption_outline_width: int = 3
    caption_position: str = "bottom"  # bottom-third of screen
    caption_bold: bool = True


@dataclass
class CaptureSettings:
    """Settings for the rolling stream buffer."""

    segment_duration: int = 10  # seconds per segment
    buffer_window: int = 120  # seconds of footage to keep
    stream_quality: str = "best"  # Streamlink quality selector
    audio_extract_format: str = "wav"


@dataclass
class HookSettings:
    """Settings for the hook overlay text."""

    duration: float = 3.0  # seconds the hook is visible
    font_size: int = 72
    font_color: str = "white"
    border_width: int = 4
    fade_in: float = 0.3
    fade_out: float = 0.5


@dataclass
class ThumbnailSettings:
    """Settings for thumbnail generation."""

    width: int = 1280
    height: int = 720
    quality: int = 90
    frame_timestamp: float = 1.5  # seconds into clip for frame extraction


@dataclass
class VODSettings:
    """Settings for VOD processing (Clip Generator)."""

    max_clips: int = 3
    clip_duration: int = 45  # target seconds
    download_resolution: int = 1080
    parallel_renders: int = 2
    use_fast_whisper: bool = True
    burn_captions: bool = True

    def load_dynamic(self):
        """Load settings from settings.json if it exists."""
        settings_file = BASE_DIR / "settings.json"
        if settings_file.exists():
            import json
            try:
                data = json.loads(settings_file.read_text())
                if "max_clips" in data: self.max_clips = int(data["max_clips"])
                if "clip_duration" in data: self.clip_duration = int(data["clip_duration"])
                if "download_resolution" in data: self.download_resolution = int(data["download_resolution"])
                if "parallel_renders" in data: self.parallel_renders = int(data["parallel_renders"])
                if "use_fast_whisper" in data: self.use_fast_whisper = bool(data["use_fast_whisper"])
                if "burn_captions" in data: self.burn_captions = bool(data["burn_captions"])
            except Exception as e:
                logger.error("Failed to load dynamic settings: %s", e)


# ── Twitch API ──────────────────────────────────────────────────────────────

TWITCH_CLIENT_ID: str = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET: str = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_AUTH_URL: str = "https://id.twitch.tv/oauth2/token"
TWITCH_HELIX_URL: str = "https://api.twitch.tv/helix"

# ── YouTube API ─────────────────────────────────────────────────────────────

YOUTUBE_CLIENT_SECRETS: str = os.getenv("YOUTUBE_CLIENT_SECRETS", str(BASE_DIR / "client_secrets.json"))
YOUTUBE_TOKEN_FILE: str = os.getenv("YOUTUBE_TOKEN_FILE", str(BASE_DIR / "youtube_token.json"))
YOUTUBE_API_SERVICE_NAME: str = "youtube"
YOUTUBE_API_VERSION: str = "v3"
YOUTUBE_SCOPES: list = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID: str = "22"  # "People & Blogs"

# ── Ollama (Local LLM) ─────────────────────────────────────────────────────

OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_FALLBACK_MODEL: str = os.getenv("OLLAMA_FALLBACK_MODEL", "mistral")

# ── Whisper Settings ────────────────────────────────────────────────────────

WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ── Database ────────────────────────────────────────────────────────────────

DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "streamclipper.db"))

# ── Dashboard ───────────────────────────────────────────────────────────────

DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8420"))

# ── Task Queue ──────────────────────────────────────────────────────────────

QUEUE_POLL_INTERVAL: float = float(os.getenv("QUEUE_POLL_INTERVAL", "5.0"))
UPLOAD_MAX_PER_DAY: int = int(os.getenv("UPLOAD_MAX_PER_DAY", "6"))

# ── Streamer Presets ────────────────────────────────────────────────────────

DEFAULT_STREAMERS: list[StreamerConfig] = [
    StreamerConfig(
        name="IShowSpeed",
        platform="youtube",
        channel="UCWsDFcIhY2DBi3GB5uykGXA",
        url="https://www.youtube.com/@IShowSpeed",
        enabled=True,
    ),
    StreamerConfig(
        name="Kai Cenat",
        platform="twitch",
        channel="kaicenat",
        url="https://www.twitch.tv/kaicenat",
        enabled=True,
    ),
    StreamerConfig(
        name="Adin Ross",
        platform="kick",
        channel="adinross",
        url="https://www.kick.com/adinross",
        enabled=True,
    ),
    StreamerConfig(
        name="Jinnytty",
        platform="twitch",
        channel="jinnytty",
        url="https://www.twitch.tv/jinnytty",
        enabled=True,
    ),
    StreamerConfig(
        name="JakenbakeLIVE",
        platform="twitch",
        channel="jakenbakeLIVE",
        url="https://www.twitch.tv/jakenbakeLIVE",
        enabled=True,
    ),
    StreamerConfig(
        name="n3on",
        platform="kick",
        channel="n3on",
        url="https://www.kick.com/n3on",
        enabled=True,
    ),
    StreamerConfig(
        name="Ice Poseidon",
        platform="kick",
        channel="iceposeidon",
        url="https://www.kick.com/iceposeidon",
        enabled=True,
    ),
    StreamerConfig(
        name="ExtraEmily",
        platform="twitch",
        channel="extraemily",
        url="https://www.twitch.tv/extraemily",
        enabled=True,
    ),
    StreamerConfig(
        name="Robcdee",
        platform="twitch",
        channel="robcdee",
        url="https://www.twitch.tv/robcdee",
        enabled=True,
    ),
    StreamerConfig(
        name="CookSux",
        platform="twitch",
        channel="cooksux",
        url="https://www.twitch.tv/cooksux",
        enabled=True,
    ),
]


# ── Instantiate Defaults ────────────────────────────────────────────────────

thresholds = DetectionThresholds()
clip_settings = ClipSettings()
capture_settings = CaptureSettings()
hook_settings = HookSettings()
thumbnail_settings = ThumbnailSettings()
vod_settings = VODSettings()
vod_settings.load_dynamic()


def get_streamers() -> list[StreamerConfig]:
    """Return all enabled streamers."""
    return [s for s in DEFAULT_STREAMERS if s.enabled]


def validate_config() -> list[str]:
    """Validate configuration and return a list of warnings."""
    warnings = []

    if not TWITCH_CLIENT_ID:
        warnings.append("TWITCH_CLIENT_ID not set — Twitch monitoring disabled")
    if not TWITCH_CLIENT_SECRET:
        warnings.append("TWITCH_CLIENT_SECRET not set — Twitch monitoring disabled")

    # Check Ollama connectivity
    try:
        import requests
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        if resp.status_code != 200:
            warnings.append(f"Ollama not responding at {OLLAMA_HOST} — SEO will use templates")
    except Exception:
        warnings.append(f"Ollama not reachable at {OLLAMA_HOST} — SEO will use templates")

    if not Path(YOUTUBE_CLIENT_SECRETS).exists():
        warnings.append(
            f"YouTube client_secrets.json not found at {YOUTUBE_CLIENT_SECRETS} "
            "— YouTube upload disabled"
        )

    return warnings
