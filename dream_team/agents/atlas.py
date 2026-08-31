"""Dream Team — Atlas Agent
The Viral Moment Analyst.

Atlas evaluates stream clips to predict their viral potential using a
combination of LLM-based reasoning and fast keyword heuristics.  Results
are persisted to :class:`SharedMemory` so downstream agents (Scribe,
Pixel, etc.) can act on them.
"""
import json
import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory
from dream_team.tools import TOOL_REGISTRY


class Atlas(BaseAgent):
    """Viral Moment Analyst — scores clips on viral potential.

    Usage::

        memory = SharedMemory()
        atlas = Atlas(memory)
        result = atlas.analyze_clip(
            clip_path="clips/rage_moment.mp4",
            transcript="No way! That's insane!",
            emotion="excited",
            chat_intensity=0.85,
        )
        print(result["viral_score"])  # 0.0–1.0
    """

    # ── Viral-signal keywords grouped by weight ──────────────────────
    _HIGH_SIGNAL_KEYWORDS: List[str] = [
        "insane", "no way", "oh my god", "unbelievable", "clutch",
        "world record", "never seen", "impossible", "legendary",
    ]
    _MEDIUM_SIGNAL_KEYWORDS: List[str] = [
        "epic", "rage", "fail", "crazy", "amazing", "incredible",
        "let's go", "holy", "what the", "bruh", "sheesh",
    ]
    _LOW_SIGNAL_KEYWORDS: List[str] = [
        "wow", "lol", "haha", "nice", "gg", "pog", "w",
        "unlucky", "rip", "oof", "yikes",
    ]

    # Emotions that tend to correlate with virality
    _VIRAL_EMOTIONS: Dict[str, float] = {
        "excited": 0.20,
        "angry": 0.18,
        "surprised": 0.22,
        "happy": 0.12,
        "sad": 0.08,
        "frustrated": 0.15,
        "scared": 0.14,
        "neutral": 0.0,
    }

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="atlas",
            description="Viral Moment Analyst — predicts clip virality",
            agent_config=config.ATLAS_CONFIG,
        )
        self.memory = memory

        # Register the video tools this agent needs
        for tool_name in ("get_video_duration", "extract_frame"):
            if tool_name in TOOL_REGISTRY:
                self.register_tool(tool_name, TOOL_REGISTRY[tool_name])

        self.logger.info(
            "Atlas ready — min_viral_score=%.2f, consider_history=%s",
            self.agent_config.get("min_viral_score", 0.65),
            self.agent_config.get("consider_history", True),
        )

    # ──────────────────────────────────────────────────────────────────
    # Core analysis
    # ──────────────────────────────────────────────────────────────────

    def analyze_clip(
        self,
        clip_path: str,
        transcript: str,
        emotion: str,
        chat_intensity: float = 0.0,
    ) -> Dict[str, Any]:
        """Perform a full viral-potential analysis on a clip.

        Args:
            clip_path: Filesystem path to the video clip.
            transcript: Text transcript / captions of the clip.
            emotion: Dominant detected emotion (e.g. ``"excited"``).
            chat_intensity: Normalised 0-1 measure of live-chat activity.

        Returns:
            A dict with keys ``viral_score``, ``confidence``,
            ``reasoning``, ``recommended``, and ``tags``.
        """
        self.logger.info(
            "analyze_clip() — clip=%s, emotion=%s, chat=%.2f",
            clip_path, emotion, chat_intensity,
        )

        # Gather optional metadata from tools
        duration: Optional[float] = None
        try:
            duration = self.use_tool("get_video_duration", path=clip_path)
        except Exception:
            self.logger.debug("Could not read video duration for %s", clip_path)

        # Build LLM prompt
        prompt = self._build_analysis_prompt(
            transcript=transcript,
            emotion=emotion,
            chat_intensity=chat_intensity,
            duration=duration,
        )

        # Call LLM
        raw_response = self.think(prompt, temperature=0.4, max_tokens=512)
        result = self._parse_llm_response(raw_response, transcript, emotion, chat_intensity)

        # Store in shared memory
        clip_id = f"clip_{uuid.uuid4().hex[:12]}"
        memory_entry = {
            **result,
            "clip_path": clip_path,
            "emotion": emotion,
            "chat_intensity": chat_intensity,
            "duration": duration,
            "analyzed_at": datetime.utcnow().isoformat(),
        }
        try:
            self.memory.store(
                key=clip_id,
                value=memory_entry,
                category="clips",
                agent=self.name,
            )
            self.logger.info(
                "Stored analysis for %s — viral_score=%.2f, recommended=%s",
                clip_id, result["viral_score"], result["recommended"],
            )
        except Exception as exc:
            self.logger.error("Failed to store clip analysis in memory: %s", exc)

        # Also cache in per-agent memory for quick recall
        self.remember(f"last_analysis_{clip_id}", result)

        return result

    # ──────────────────────────────────────────────────────────────────
    # Quick scoring (no LLM)
    # ──────────────────────────────────────────────────────────────────

    def score_virality(
        self,
        transcript: str,
        emotion: str,
        chat_intensity: float,
    ) -> float:
        """Return a fast heuristic viral score (0-1) without LLM inference.

        Useful for bulk pre-filtering before running the heavier
        :meth:`analyze_clip` on the top candidates.

        Scoring factors:
            * Keyword hits — high/medium/low signal words in transcript.
            * Emotion bonus — emotions historically linked to virality.
            * Chat intensity — high live-chat activity is a strong signal.

        Args:
            transcript: Text transcript of the clip.
            emotion: Dominant detected emotion.
            chat_intensity: Normalised 0-1 chat activity measure.

        Returns:
            A float between 0.0 and 1.0.
        """
        self.logger.debug("score_virality() — fast path")

        text_lower = transcript.lower()
        score: float = 0.0

        # Keyword hits
        for kw in self._HIGH_SIGNAL_KEYWORDS:
            if kw in text_lower:
                score += 0.12
        for kw in self._MEDIUM_SIGNAL_KEYWORDS:
            if kw in text_lower:
                score += 0.07
        for kw in self._LOW_SIGNAL_KEYWORDS:
            if kw in text_lower:
                score += 0.03

        # Emotion bonus
        score += self._VIRAL_EMOTIONS.get(emotion.lower(), 0.0)

        # Chat intensity (strong signal — up to 0.25)
        score += min(chat_intensity, 1.0) * 0.25

        # Transcript length bonus — very short or very long clips are less viral
        word_count = len(transcript.split())
        if 10 <= word_count <= 80:
            score += 0.05  # sweet-spot length

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        self.logger.debug("score_virality() result: %.3f", score)
        return round(score, 3)

    # ──────────────────────────────────────────────────────────────────
    # Trending patterns
    # ──────────────────────────────────────────────────────────────────

    def get_trending_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Query shared memory for recent clip patterns and trending signals.

        Returns up to *limit* dicts with keys ``topic``, ``emotion``,
        ``avg_score``, and ``count``.
        """
        self.logger.info("get_trending_patterns(limit=%d)", limit)

        try:
            recent_clips = self.memory.search(category="clips", limit=50, agent=self.name)
        except Exception as exc:
            self.logger.error("Failed to query shared memory: %s", exc)
            return []

        if not recent_clips:
            self.logger.info("No clips in memory — no trending patterns")
            return []

        # Aggregate by emotion
        emotion_stats: Dict[str, List[float]] = {}
        tag_counter: Counter = Counter()

        for entry in recent_clips:
            value = entry.get("value", {})
            em = value.get("emotion", "unknown")
            vs = value.get("viral_score", 0.0)

            emotion_stats.setdefault(em, []).append(vs)

            for tag in value.get("tags", []):
                tag_counter[tag] += 1

        # Build patterns list
        patterns: List[Dict[str, Any]] = []

        for em, scores in emotion_stats.items():
            patterns.append({
                "topic": f"emotion:{em}",
                "emotion": em,
                "avg_score": round(sum(scores) / len(scores), 3),
                "count": len(scores),
            })

        # Add top tags as pseudo-topics
        for tag, count in tag_counter.most_common(limit):
            patterns.append({
                "topic": f"tag:{tag}",
                "emotion": "mixed",
                "avg_score": 0.0,  # tags don't carry a direct score
                "count": count,
            })

        # Sort by count descending, then avg_score descending
        patterns.sort(key=lambda p: (-p["count"], -p["avg_score"]))
        patterns = patterns[:limit]

        self.logger.info("Returning %d trending patterns", len(patterns))
        return patterns

    # ──────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────

    def _build_analysis_prompt(
        self,
        transcript: str,
        emotion: str,
        chat_intensity: float,
        duration: Optional[float],
    ) -> str:
        """Compose the LLM prompt for viral-potential analysis."""
        duration_str = f"{duration:.1f} seconds" if duration else "unknown"

        history_note = ""
        if self.agent_config.get("consider_history"):
            try:
                recent = self.memory.search(category="clips", limit=5, agent=self.name)
                if recent:
                    avg_score = sum(
                        e["value"].get("viral_score", 0) for e in recent
                    ) / len(recent)
                    history_note = (
                        f"\nHistorical context: average viral score of recent "
                        f"clips is {avg_score:.2f} (from {len(recent)} clips)."
                    )
            except Exception:
                pass

        return f"""You are a viral content analyst specialising in gaming/streaming clips.

Analyse the following clip and predict its viral potential.

TRANSCRIPT:
{transcript}

CLIP METADATA:
- Detected emotion: {emotion}
- Live-chat intensity (0-1): {chat_intensity:.2f}
- Duration: {duration_str}{history_note}

Score the clip on these criteria (each 0-1):
1. Emotional intensity — how strong is the emotional reaction?
2. Quotable moments — does it contain memorable phrases?
3. Relatability — would a broad audience relate to this?
4. Controversy / shock value — does it provoke strong reactions?
5. Humor — is it funny or entertaining?

Respond ONLY in valid JSON with this exact structure:
{{
    "viral_score": <float 0-1>,
    "confidence": <float 0-1>,
    "reasoning": "<one-paragraph explanation>",
    "tags": ["<tag1>", "<tag2>", ...]
}}"""

    def _parse_llm_response(
        self,
        raw_response: str,
        transcript: str,
        emotion: str,
        chat_intensity: float,
    ) -> Dict[str, Any]:
        """Parse the LLM JSON response, falling back to heuristics on error."""
        min_score = self.agent_config.get("min_viral_score", 0.65)

        try:
            # Try to extract JSON from the response (LLMs sometimes wrap it)
            json_match = re.search(r"\{[\s\S]*\}", raw_response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON object found in LLM response")

            viral_score = float(data.get("viral_score", 0.0))
            confidence = float(data.get("confidence", 0.5))
            reasoning = str(data.get("reasoning", ""))
            tags = list(data.get("tags", []))

            # Validate ranges
            viral_score = max(0.0, min(1.0, viral_score))
            confidence = max(0.0, min(1.0, confidence))

            result = {
                "viral_score": round(viral_score, 3),
                "confidence": round(confidence, 3),
                "reasoning": reasoning,
                "recommended": viral_score >= min_score,
                "tags": tags[:15],  # cap tags
            }
            self.logger.info(
                "LLM analysis parsed — score=%.3f, confidence=%.3f",
                result["viral_score"], result["confidence"],
            )
            return result

        except Exception as exc:
            self.logger.warning(
                "Failed to parse LLM response, falling back to heuristics: %s", exc
            )
            # Fallback to heuristic scoring
            fallback_score = self.score_virality(transcript, emotion, chat_intensity)
            return {
                "viral_score": fallback_score,
                "confidence": 0.3,  # low confidence for heuristic fallback
                "reasoning": "Heuristic fallback — LLM analysis could not be parsed.",
                "recommended": fallback_score >= min_score,
                "tags": self._extract_heuristic_tags(transcript, emotion),
            }

    def _extract_heuristic_tags(self, transcript: str, emotion: str) -> List[str]:
        """Generate basic tags from keywords when LLM is unavailable."""
        tags: List[str] = [emotion]
        text_lower = transcript.lower()

        all_keywords = (
            self._HIGH_SIGNAL_KEYWORDS
            + self._MEDIUM_SIGNAL_KEYWORDS
            + self._LOW_SIGNAL_KEYWORDS
        )
        for kw in all_keywords:
            if kw in text_lower:
                tags.append(kw.replace(" ", "-"))

        # Deduplicate while preserving order
        seen: set = set()
        unique_tags: List[str] = []
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)

        return unique_tags[:10]
