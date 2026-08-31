"""Dream Team — Configuration"""
import os
from pathlib import Path

DREAM_TEAM_DIR = Path(__file__).parent.resolve()
AGENTS_DIR = DREAM_TEAM_DIR / "agents"
LOGS_DIR = DREAM_TEAM_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

DREAM_TEAM_ENABLED = True
LOG_LEVEL = "INFO"

ACTIVE_AGENTS = {
    "atlas": True, "scribe": True, "sentinel": True,
    "pixel": True, "pulse": True, "echo": False,
    "debugger": True, "concierge": False,
}

USE_OLLAMA = True
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = "llama3"
OLLAMA_FALLBACK_MODEL = "mistral"

USE_OPENAI = False
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"

USE_ANTHROPIC = False
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-3-haiku-20240307"

ATLAS_CONFIG = {"min_viral_score": 0.65, "consider_history": True, "streamer_profiles": True}
SCRIBE_CONFIG = {"max_title_length": 80, "title_style": "clickbait", "include_emoji": True, "min_tags": 5, "max_tags": 8}
SENTINEL_CONFIG = {"check_captions": True, "check_profanity": True, "check_facts": True, "strict_mode": False}
PIXEL_CONFIG = {"auto_generate": True, "style": "bold", "add_emoji": True}
PULSE_CONFIG = {"track_performance": True, "learn_from_data": True, "update_interval_hours": 24}
DEBUGGER_CONFIG = {"auto_fix": True, "alert_on_errors": True, "log_retention_days": 30}

MAX_DAILY_API_COST = 5.00
COST_TRACKING_ENABLED = True
AGENT_TIMEOUT_SECONDS = 30
MAX_CONCURRENT_AGENTS = 3
