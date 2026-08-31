"""Dream Team — Pulse Agent (Performance Analyst)
Tracks upload performance, analyses trends, and learns from historical
data to provide actionable recommendations for improving clip virality.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory

logger = logging.getLogger("dreamteam.pulse")


class Pulse(BaseAgent):
    """Performance Analyst agent.

    Monitors upload metrics (views, likes, comments, shares, watch time),
    detects trends over configurable windows, and uses LLM reasoning to
    generate improvement suggestions and optimal upload-time predictions.
    """

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="pulse",
            description="Performance Analyst — tracks uploads and learns from data",
            agent_config=config.PULSE_CONFIG,
        )
        self.memory = memory
        self._performance_cache: Dict[str, Dict[str, Any]] = {}
        self.logger.info(
            "Pulse initialised — track=%s, learn=%s, interval=%dh",
            self.agent_config.get("track_performance", True),
            self.agent_config.get("learn_from_data", True),
            self.agent_config.get("update_interval_hours", 24),
        )

    # ──────────────────────────────────────────────────────────────────
    # Track uploads
    # ──────────────────────────────────────────────────────────────────

    def track_upload(self, clip_id: str, video_url: str, metrics: dict) -> None:
        """Store performance data for an uploaded clip.

        Args:
            clip_id: Unique clip identifier.
            video_url: Public URL of the uploaded video.
            metrics: Dict with keys — views, likes, comments, shares,
                     watch_time_avg (all numeric).
        """
        if not self.agent_config.get("track_performance", True):
            self.logger.debug("Performance tracking disabled — skipping clip %s", clip_id)
            return

        required_keys = {"views", "likes", "comments", "shares", "watch_time_avg"}
        missing = required_keys - set(metrics.keys())
        if missing:
            self.logger.warning(
                "track_upload(%s): missing metric keys %s — storing anyway", clip_id, missing,
            )

        record: Dict[str, Any] = {
            "clip_id": clip_id,
            "video_url": video_url,
            "metrics": metrics,
            "tracked_at": datetime.utcnow().isoformat(),
        }

        # Derive an engagement score (0-1) for quick ranking
        views = max(metrics.get("views", 0), 1)
        engagement = (
            metrics.get("likes", 0)
            + metrics.get("comments", 0) * 2
            + metrics.get("shares", 0) * 3
        ) / views
        record["engagement_score"] = round(min(engagement, 1.0), 4)

        # Persist to shared memory
        mem_key = f"perf_{clip_id}"
        try:
            self.memory.store(mem_key, record, category="performance", agent=self.name)
            self.logger.info("Tracked upload %s — engagement=%.4f", clip_id, record["engagement_score"])
        except Exception as exc:
            self.logger.error("Failed to store performance data for %s: %s", clip_id, exc)
            raise

        # Update local cache
        self._performance_cache[clip_id] = record

    # ──────────────────────────────────────────────────────────────────
    # Trend analysis
    # ──────────────────────────────────────────────────────────────────

    def analyze_trends(self, days: int = 7) -> dict:
        """Analyse recent performance data and return trend insights.

        Args:
            days: Look-back window in days (default 7).

        Returns:
            {
                "top_performing": list[dict],
                "worst_performing": list[dict],
                "avg_views": float,
                "trend": "up" | "down" | "stable",
                "insights": list[str],
            }
        """
        self.logger.info("analyze_trends(days=%d) started", days)

        # Fetch recent performance entries from shared memory
        entries = self._fetch_recent_performance(days)

        if not entries:
            self.logger.warning("No performance data found for the last %d days", days)
            return {
                "top_performing": [],
                "worst_performing": [],
                "avg_views": 0.0,
                "trend": "stable",
                "insights": ["No data available for the requested period."],
            }

        # Sort by engagement score
        sorted_entries = sorted(
            entries, key=lambda e: e.get("engagement_score", 0), reverse=True,
        )

        top_performing = sorted_entries[:5]
        worst_performing = sorted_entries[-5:] if len(sorted_entries) > 5 else sorted_entries[-1:]

        # Calculate average views
        all_views = [e.get("metrics", {}).get("views", 0) for e in entries]
        avg_views = sum(all_views) / len(all_views) if all_views else 0.0

        # Use LLM to determine trend & generate insights
        trend, insights = self._llm_trend_analysis(entries, days)

        result = {
            "top_performing": top_performing,
            "worst_performing": worst_performing,
            "avg_views": round(avg_views, 2),
            "trend": trend,
            "insights": insights,
        }

        # Cache the analysis
        self.remember(f"trend_analysis_{days}d", result)
        self.logger.info(
            "Trend analysis complete — trend=%s, avg_views=%.1f, entries=%d",
            trend, avg_views, len(entries),
        )
        return result

    def _llm_trend_analysis(self, entries: list, days: int) -> tuple:
        """Use the LLM to derive trend direction and insights from raw data.

        Returns:
            (trend: str, insights: list[str])
        """
        # Build a compact summary for the prompt
        summary_lines: List[str] = []
        for e in entries[:20]:  # cap to avoid prompt overflow
            m = e.get("metrics", {})
            summary_lines.append(
                f"clip={e.get('clip_id','?')} views={m.get('views',0)} "
                f"likes={m.get('likes',0)} comments={m.get('comments',0)} "
                f"shares={m.get('shares',0)} watch_avg={m.get('watch_time_avg',0)}"
            )
        data_block = "\n".join(summary_lines)

        prompt = (
            f"You are a data analyst for a short-form video channel.\n"
            f"Below is performance data from the last {days} days:\n\n"
            f"{data_block}\n\n"
            f"Respond in JSON only (no markdown) with exactly these keys:\n"
            f'  "trend": one of "up", "down", or "stable"\n'
            f'  "insights": a list of 3-5 short actionable insight strings\n'
        )

        try:
            raw = self.think(prompt, temperature=0.4, max_tokens=400)
            parsed = json.loads(raw)
            trend = parsed.get("trend", "stable")
            if trend not in ("up", "down", "stable"):
                trend = "stable"
            insights = parsed.get("insights", [])
            if not isinstance(insights, list):
                insights = [str(insights)]
            return trend, insights
        except (json.JSONDecodeError, Exception) as exc:
            self.logger.warning("LLM trend analysis parse failed: %s", exc)
            return "stable", ["Unable to generate AI insights — raw data was reviewed."]

    # ──────────────────────────────────────────────────────────────────
    # Improvement suggestions
    # ──────────────────────────────────────────────────────────────────

    def suggest_improvements(self, clip_data: dict) -> List[str]:
        """Suggest improvements for a clip based on past performance patterns.

        Args:
            clip_data: Dict describing the clip (title, tags, duration, etc.).

        Returns:
            List of actionable suggestion strings.
        """
        self.logger.info("suggest_improvements() for clip: %s", clip_data.get("clip_id", "unknown"))

        # Gather historical context
        history = self._fetch_recent_performance(days=30)
        history_summary = ""
        if history:
            top = sorted(history, key=lambda e: e.get("engagement_score", 0), reverse=True)[:5]
            lines = []
            for h in top:
                m = h.get("metrics", {})
                lines.append(
                    f"  - clip={h.get('clip_id','?')} engagement={h.get('engagement_score',0)} "
                    f"views={m.get('views',0)}"
                )
            history_summary = "Top performing clips (last 30 days):\n" + "\n".join(lines)

        prompt = (
            f"You are a video performance optimisation expert.\n\n"
            f"Current clip data:\n{json.dumps(clip_data, indent=2)}\n\n"
            f"{history_summary}\n\n"
            f"Provide 3-6 specific, actionable suggestions to improve this clip's performance.\n"
            f"Respond as a JSON array of strings only (no markdown).\n"
        )

        try:
            raw = self.think(prompt, temperature=0.6, max_tokens=512)
            suggestions = json.loads(raw)
            if isinstance(suggestions, list):
                self.logger.info("Generated %d improvement suggestions", len(suggestions))
                return [str(s) for s in suggestions]
        except (json.JSONDecodeError, Exception) as exc:
            self.logger.warning("suggest_improvements LLM parse failed: %s", exc)

        # Fallback: rule-based suggestions
        fallback = self._rule_based_suggestions(clip_data)
        self.logger.info("Returning %d rule-based suggestions (LLM fallback)", len(fallback))
        return fallback

    def _rule_based_suggestions(self, clip_data: dict) -> List[str]:
        """Generate basic suggestions when LLM is unavailable."""
        suggestions: List[str] = []
        title = clip_data.get("title", "")
        tags = clip_data.get("tags", [])
        duration = clip_data.get("duration", 0)

        if len(title) < 20:
            suggestions.append("Consider a longer, more descriptive title to improve discoverability.")
        if len(title) > 80:
            suggestions.append("Shorten the title — titles over 80 chars may be truncated on mobile.")
        if len(tags) < 5:
            suggestions.append(f"Add more tags (currently {len(tags)}). Aim for 5-8 relevant tags.")
        if duration and duration > 60:
            suggestions.append("Clips under 60 seconds tend to perform better on short-form platforms.")
        if not clip_data.get("thumbnail"):
            suggestions.append("Add a custom thumbnail — clips with thumbnails get 2x more clicks.")
        suggestions.append("Post during peak hours (14:00-16:00 UTC) for maximum initial reach.")
        return suggestions

    # ──────────────────────────────────────────────────────────────────
    # Best upload time
    # ──────────────────────────────────────────────────────────────────

    def get_best_upload_time(self) -> str:
        """Analyse historical data to suggest the optimal upload window.

        Returns:
            Time-range string, e.g. ``'14:00-16:00 UTC'``.
        """
        self.logger.info("get_best_upload_time() called")

        history = self._fetch_recent_performance(days=30)

        if not history:
            self.logger.info("No historical data — returning default upload window")
            return "14:00-16:00 UTC"

        # Extract hours from tracked_at timestamps
        hour_scores: Dict[int, List[float]] = {}
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["tracked_at"])
                hour = ts.hour
                score = entry.get("engagement_score", 0)
                hour_scores.setdefault(hour, []).append(score)
            except (KeyError, ValueError):
                continue

        if not hour_scores:
            return "14:00-16:00 UTC"

        # Average engagement by hour
        avg_by_hour = {
            h: sum(scores) / len(scores) for h, scores in hour_scores.items()
        }
        best_hour = max(avg_by_hour, key=avg_by_hour.get)
        window_start = best_hour
        window_end = (best_hour + 2) % 24

        result = f"{window_start:02d}:00-{window_end:02d}:00 UTC"
        self.logger.info("Best upload time determined: %s (based on %d entries)", result, len(history))
        self.remember("best_upload_time", result)
        return result

    # ──────────────────────────────────────────────────────────────────
    # Full report
    # ──────────────────────────────────────────────────────────────────

    def generate_report(self, days: int = 7) -> dict:
        """Generate a comprehensive performance report.

        Args:
            days: Reporting window in days (default 7).

        Returns:
            {
                "period": str,
                "total_uploads": int,
                "avg_score": float,
                "top_clips": list,
                "recommendations": list[str],
            }
        """
        self.logger.info("generate_report(days=%d) started", days)

        entries = self._fetch_recent_performance(days)
        now = datetime.utcnow()
        period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        period_end = now.strftime("%Y-%m-%d")

        if not entries:
            return {
                "period": f"{period_start} → {period_end}",
                "total_uploads": 0,
                "avg_score": 0.0,
                "top_clips": [],
                "recommendations": ["No data to report. Start tracking uploads to see insights."],
            }

        # Compute aggregate stats
        scores = [e.get("engagement_score", 0) for e in entries]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        sorted_entries = sorted(entries, key=lambda e: e.get("engagement_score", 0), reverse=True)
        top_clips = sorted_entries[:5]

        # Generate recommendations via LLM
        recommendations = self._generate_recommendations(entries, days)

        report = {
            "period": f"{period_start} → {period_end}",
            "total_uploads": len(entries),
            "avg_score": round(avg_score, 4),
            "top_clips": top_clips,
            "recommendations": recommendations,
        }

        # Persist the report
        report_key = f"report_{period_start}_{period_end}"
        try:
            self.memory.store(report_key, report, category="performance", agent=self.name)
        except Exception as exc:
            self.logger.warning("Failed to persist report: %s", exc)

        self.logger.info(
            "Report generated — period=%s, uploads=%d, avg_score=%.4f",
            report["period"], report["total_uploads"], report["avg_score"],
        )
        return report

    def _generate_recommendations(self, entries: list, days: int) -> List[str]:
        """Use LLM to produce report recommendations."""
        if not self.agent_config.get("learn_from_data", True):
            return ["Enable 'learn_from_data' in PULSE_CONFIG for AI-powered recommendations."]

        stats_lines: List[str] = []
        for e in entries[:15]:
            m = e.get("metrics", {})
            stats_lines.append(
                f"clip={e.get('clip_id','?')} score={e.get('engagement_score',0)} "
                f"views={m.get('views',0)} likes={m.get('likes',0)}"
            )

        prompt = (
            f"You are a content-strategy consultant reviewing {days}-day performance data.\n\n"
            f"Data:\n" + "\n".join(stats_lines) + "\n\n"
            f"Produce 3-5 concise recommendations for improving future uploads.\n"
            f"Respond as a JSON array of strings only (no markdown).\n"
        )

        try:
            raw = self.think(prompt, temperature=0.5, max_tokens=400)
            recs = json.loads(raw)
            if isinstance(recs, list):
                return [str(r) for r in recs]
        except (json.JSONDecodeError, Exception) as exc:
            self.logger.warning("Recommendation generation failed: %s", exc)

        return [
            "Focus on clips that generated above-average engagement.",
            "Experiment with different posting times to find your audience's peak.",
            "Analyse top-performing titles and replicate their style.",
        ]

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _fetch_recent_performance(self, days: int) -> List[Dict[str, Any]]:
        """Retrieve performance entries from shared memory within the window."""
        try:
            all_entries = self.memory.search(category="performance", limit=500)
        except Exception as exc:
            self.logger.error("Failed to query shared memory: %s", exc)
            return []

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        recent: List[Dict[str, Any]] = []
        for entry in all_entries:
            value = entry.get("value", {})
            tracked_at = value.get("tracked_at", entry.get("updated", ""))
            if tracked_at >= cutoff:
                recent.append(value)

        self.logger.debug("Fetched %d performance entries (last %d days)", len(recent), days)
        return recent
