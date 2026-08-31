"""Dream Team — Director
Central orchestrator that initialises, routes, and coordinates all agents.
The Director is the single entry point for the rest of the StreamClipper
pipeline to interact with the Dream Team.
"""
import logging
import threading
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.memory import SharedMemory
from dream_team.base_agent import BaseAgent

logger = logging.getLogger("dreamteam.director")


class Director:
    """Manages the lifecycle and orchestration of all Dream Team agents.

    Usage::

        director = Director()
        director.initialise()  # boots all enabled agents

        # Run the full enhancement pipeline on a clip
        result = director.process_clip(clip_data)

        # Shut down cleanly
        director.shutdown()
    """

    def __init__(self):
        self.memory = SharedMemory()
        self._agents: Dict[str, BaseAgent] = {}
        self._lock = threading.Lock()
        self._initialised = False
        logger.info("Director created")

    # ──────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────

    def initialise(self) -> None:
        """Import and boot every agent that is enabled in config."""
        if self._initialised:
            logger.warning("Director already initialised — skipping")
            return

        logger.info("Initialising Dream Team agents …")

        # ── Atlas — Viral Moment Analyst ─────────────────────────────
        if config.ACTIVE_AGENTS.get("atlas"):
            try:
                from dream_team.agents.atlas import Atlas
                self._agents["atlas"] = Atlas(self.memory)
                logger.info("✅ Atlas loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Atlas: %s", exc)

        # ── Scribe — SEO Wordsmith ───────────────────────────────────
        if config.ACTIVE_AGENTS.get("scribe"):
            try:
                from dream_team.agents.scribe import Scribe
                self._agents["scribe"] = Scribe(self.memory)
                logger.info("✅ Scribe loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Scribe: %s", exc)

        # ── Sentinel — Content Guardian ──────────────────────────────
        if config.ACTIVE_AGENTS.get("sentinel"):
            try:
                from dream_team.agents.sentinel import Sentinel
                self._agents["sentinel"] = Sentinel(self.memory)
                logger.info("✅ Sentinel loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Sentinel: %s", exc)

        # ── Pixel — Visual Artist ────────────────────────────────────
        if config.ACTIVE_AGENTS.get("pixel"):
            try:
                from dream_team.agents.pixel import Pixel
                self._agents["pixel"] = Pixel(self.memory)
                logger.info("✅ Pixel loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Pixel: %s", exc)

        # ── Pulse — Performance Analyst ──────────────────────────────
        if config.ACTIVE_AGENTS.get("pulse"):
            try:
                from dream_team.agents.pulse import Pulse
                self._agents["pulse"] = Pulse(self.memory)
                logger.info("✅ Pulse loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Pulse: %s", exc)

        # ── Debugger — System Doctor ─────────────────────────────────
        if config.ACTIVE_AGENTS.get("debugger"):
            try:
                from dream_team.agents.debugger import Debugger
                self._agents["debugger"] = Debugger(self.memory)
                logger.info("✅ Debugger loaded")
            except Exception as exc:
                logger.error("❌ Failed to load Debugger: %s", exc)

        self._initialised = True
        logger.info(
            "Dream Team ready — %d/%d agents active: %s",
            len(self._agents),
            len(config.ACTIVE_AGENTS),
            list(self._agents.keys()),
        )

    def shutdown(self) -> None:
        """Gracefully shutdown all agents."""
        logger.info("Shutting down Dream Team …")
        with self._lock:
            self._agents.clear()
            self._initialised = False
        logger.info("Dream Team shutdown complete")

    # ──────────────────────────────────────────────────────────────────
    # Agent Access
    # ──────────────────────────────────────────────────────────────────

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Return an agent by name, or None if not loaded."""
        return self._agents.get(name)

    @property
    def active_agents(self) -> List[str]:
        """List names of currently active agents."""
        return list(self._agents.keys())

    @property
    def is_ready(self) -> bool:
        return self._initialised and len(self._agents) > 0

    # ──────────────────────────────────────────────────────────────────
    # Main Pipeline: process_clip
    # ──────────────────────────────────────────────────────────────────

    def process_clip(self, clip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run a clip through the full Dream Team enhancement pipeline.

        Expected *clip_data* keys::

            clip_path:      str   — path to the clip video file
            transcript:     str   — clip transcript / captions
            emotion:        str   — detected primary emotion
            streamer_name:  str   — streamer's display name
            chat_intensity: float — 0.0–1.0 chat activity level (optional)
            title:          str   — existing title (optional)
            description:    str   — existing description (optional)
            tags:           list  — existing tags (optional)

        Returns an enhanced dict with extra keys added by each agent.
        """
        if not self._initialised:
            logger.warning("Director not initialised — call initialise() first")
            return clip_data

        result = dict(clip_data)  # shallow copy
        clip_id = clip_data.get("clip_id", "unknown")
        logger.info("▶ Processing clip %s through Dream Team", clip_id)

        # ── 1. Atlas — Viral Score ───────────────────────────────────
        atlas = self.get_agent("atlas")
        if atlas:
            try:
                analysis = atlas.analyze_clip(
                    clip_path=clip_data.get("clip_path", ""),
                    transcript=clip_data.get("transcript", ""),
                    emotion=clip_data.get("emotion", ""),
                    chat_intensity=clip_data.get("chat_intensity", 0.0),
                )
                result["viral_analysis"] = analysis
                result["viral_score"] = analysis.get("viral_score", 0.0)
                result["viral_recommended"] = analysis.get("recommended", False)
                logger.info(
                    "Atlas: viral_score=%.2f recommended=%s",
                    result["viral_score"], result["viral_recommended"],
                )
            except Exception as exc:
                logger.error("Atlas failed: %s", exc)

        # ── 2. Scribe — SEO Enhancement ──────────────────────────────
        scribe = self.get_agent("scribe")
        if scribe:
            try:
                enhanced = scribe.enhance_seo(result)
                result["title"] = enhanced.get("title", result.get("title", ""))
                result["description"] = enhanced.get("description", result.get("description", ""))
                result["tags"] = enhanced.get("tags", result.get("tags", []))
                result["hook_text"] = enhanced.get("hook_text", "")
                result["seo_enhanced"] = True
                logger.info("Scribe: title='%s'", result["title"][:60])
            except Exception as exc:
                logger.error("Scribe failed: %s", exc)

        # ── 3. Sentinel — Content Review ─────────────────────────────
        sentinel = self.get_agent("sentinel")
        if sentinel:
            try:
                moderation = sentinel.auto_moderate(result)
                result["moderation"] = moderation
                result["moderation_action"] = moderation.get("action", "approve")
                logger.info("Sentinel: action=%s", result["moderation_action"])
            except Exception as exc:
                logger.error("Sentinel failed: %s", exc)

        # ── 4. Pixel — Visual Enhancement ────────────────────────────
        pixel = self.get_agent("pixel")
        if pixel:
            try:
                visuals = pixel.enhance_clip_visuals(result)
                result["thumbnail_text"] = visuals.get("thumbnail_text", "")
                result["color_scheme"] = visuals.get("color_scheme", {})
                result["visual_enhanced"] = True
                logger.info("Pixel: thumbnail_text='%s'", result["thumbnail_text"])
            except Exception as exc:
                logger.error("Pixel failed: %s", exc)

        # ── 5. Pulse — Performance Prediction ────────────────────────
        pulse = self.get_agent("pulse")
        if pulse:
            try:
                suggestions = pulse.suggest_improvements(result)
                result["performance_suggestions"] = suggestions
                logger.info("Pulse: %d suggestions", len(suggestions))
            except Exception as exc:
                logger.error("Pulse failed: %s", exc)

        # Store the final result in shared memory
        try:
            self.memory.store(
                key=f"processed_clip_{clip_id}",
                value={
                    "viral_score": result.get("viral_score", 0.0),
                    "title": result.get("title", ""),
                    "moderation_action": result.get("moderation_action", ""),
                    "seo_enhanced": result.get("seo_enhanced", False),
                },
                category="clips",
                agent="director",
            )
        except Exception:
            pass

        logger.info("✅ Clip %s processing complete", clip_id)
        return result

    # ──────────────────────────────────────────────────────────────────
    # Utility Methods
    # ──────────────────────────────────────────────────────────────────

    def run_health_check(self) -> Dict[str, Any]:
        """Run a system health check via the Debugger agent."""
        debugger = self.get_agent("debugger")
        if debugger:
            try:
                return debugger.check_system_health()
            except Exception as exc:
                logger.error("Health check failed: %s", exc)
                return {"status": "error", "message": str(exc)}
        return {"status": "unavailable", "message": "Debugger agent not loaded"}

    def get_performance_report(self, days: int = 7) -> Dict[str, Any]:
        """Get a performance report from the Pulse agent."""
        pulse = self.get_agent("pulse")
        if pulse:
            try:
                return pulse.generate_report(days=days)
            except Exception as exc:
                logger.error("Performance report failed: %s", exc)
                return {"error": str(exc)}
        return {"error": "Pulse agent not loaded"}

    def diagnose_error(self, error_msg: str, context: str = "") -> Dict[str, Any]:
        """Diagnose an error via the Debugger agent."""
        debugger = self.get_agent("debugger")
        if debugger:
            try:
                return debugger.diagnose_error(error_msg, context)
            except Exception as exc:
                logger.error("Error diagnosis failed: %s", exc)
                return {"error": str(exc)}
        return {"error": "Debugger agent not loaded"}

    def get_cost_summary(self) -> Dict[str, Any]:
        """Return API cost summary across all agents."""
        summary = {
            "total_cost": BaseAgent.get_total_cost(),
            "max_daily": config.MAX_DAILY_API_COST,
            "agents": {},
        }
        for name, agent in self._agents.items():
            summary["agents"][name] = {
                "cost": agent._agent_cost,
                "tools": list(agent._tools.keys()),
            }
        return summary

    def get_memory_stats(self) -> Dict[str, Any]:
        """Return shared memory usage stats."""
        return self.memory.get_stats()

    def __repr__(self) -> str:
        return (
            f"<Director agents={self.active_agents} "
            f"ready={self.is_ready} "
            f"cost=${BaseAgent.get_total_cost():.4f}>"
        )
