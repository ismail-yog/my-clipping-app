"""
StreamClipper — Scorer
Fuses audio, chat, and sentiment signals into a single moment score.
Triggers clip extraction when the score exceeds the threshold.
"""

import time
import logging
import threading
from dataclasses import dataclass
from typing import Optional, Callable
from collections import deque

import config

logger = logging.getLogger("streamclipper.processor.scorer")


@dataclass
class MomentScore:
    """A scored moment that may trigger a clip."""
    timestamp: float
    combined_score: float  # 0-1
    audio_score: float
    chat_score: float
    sentiment_score: float
    audio_events: list  # list[AudioEvent]
    chat_events: list  # list[ChatEvent]
    sentiment_events: list  # list[SentimentEvent]
    reason: str  # e.g., "audio_spike+chat_burst"
    triggered: bool = False  # Keep for dashboard compatibility


class Scorer:
    """
    Combines detection signals into a unified moment score.
    Uses configurable weights and a cooldown to prevent duplicate clips.
    """

    def __init__(
        self,
        on_trigger: Optional[Callable[[MomentScore], None]] = None,
        thresholds: Optional[config.DetectionThresholds] = None,
    ):
        self.on_trigger = on_trigger
        self.thresholds = thresholds or config.thresholds
        self._scores: deque = deque(maxlen=1000)
        self._last_trigger_time: float = 0.0
        self._lock = threading.Lock()

    def score_moment(
        self,
        audio_events: list,
        chat_events: list,
        sentiment_events: list,
        window_seconds: float = 10.0,
    ) -> MomentScore:
        """
        Score the current moment based on recent detection events.
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Filter events to window_seconds
            recent_audio = [e for e in audio_events if e.timestamp >= cutoff]
            recent_chat = [e for e in chat_events if e.timestamp >= cutoff]
            recent_sentiment = [e for e in sentiment_events if e.timestamp >= cutoff]

            # Calculate scores based on max intensity/confidence
            audio_score = max((getattr(e, "intensity", getattr(e, "score", 0.0)) for e in recent_audio), default=0.0)
            chat_score = max((getattr(e, "intensity", getattr(e, "score", 0.0)) for e in recent_chat), default=0.0)
            sentiment_score = max((getattr(e, "confidence", getattr(e, "score", 0.0)) for e in recent_sentiment), default=0.0)

            # Combined score using weights from config
            w = self.thresholds
            combined = (
                audio_score * w.audio_weight
                + chat_score * w.chat_weight
                + sentiment_score * w.sentiment_weight
            )

            # Boost: if multiple signals agree, add a bonus
            active_signals = sum([
                audio_score > 0.3,
                chat_score > 0.3,
                sentiment_score > 0.3,
            ])
            if active_signals >= 2:
                combined = min(1.0, combined * 1.15)
            if active_signals >= 3:
                combined = min(1.0, combined * 1.25)

            # Check threshold and cooldown (time since last trigger > cooldown_seconds)
            time_since_last = now - self._last_trigger_time
            triggered = (combined > w.moment_threshold) and (time_since_last > w.cooldown_seconds)

            # Determine reason string
            reasons = []
            if audio_score > 0.4:
                reasons.append("audio_spike")
            if chat_score > 0.4:
                reasons.append("chat_burst")
            if sentiment_score > 0.4:
                # Find the primary emotion in recent sentiment events
                emotions = [e.emotion for e in recent_sentiment if hasattr(e, "emotion")]
                primary_emotion = emotions[0] if emotions else "joy"
                reasons.append(f"sentiment_{primary_emotion}")
            
            if not reasons:
                max_score = max(audio_score, chat_score, sentiment_score)
                if max_score == audio_score and audio_events:
                    reasons.append("audio")
                elif max_score == chat_score and chat_events:
                    reasons.append("chat")
                elif sentiment_events:
                    reasons.append("sentiment")
                else:
                    reasons.append("normal_activity")
            reason = "+".join(reasons)

            moment = MomentScore(
                timestamp=now,
                combined_score=combined,
                audio_score=audio_score,
                chat_score=chat_score,
                sentiment_score=sentiment_score,
                audio_events=recent_audio,
                chat_events=recent_chat,
                sentiment_events=recent_sentiment,
                reason=reason,
                triggered=triggered
            )

            self._scores.append(moment)

            if triggered:
                self._last_trigger_time = now
                logger.info(
                    "🎯 MOMENT TRIGGERED! Score=%.2f (reason=%s, audio=%.2f, chat=%.2f, sentiment=%.2f)",
                    combined, reason, audio_score, chat_score, sentiment_score,
                )

        # Call on_trigger outside lock to prevent deadlocks
        if triggered and self.on_trigger:
            try:
                self.on_trigger(moment)
            except Exception as e:
                logger.error("Error in on_trigger callback: %s", e, exc_info=True)

        return moment

    @property
    def recent_scores(self) -> list[MomentScore]:
        with self._lock:
            cutoff = time.time() - 300
            return [s for s in self._scores if s.timestamp >= cutoff]

    @property
    def trigger_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._scores if s.triggered)

    def reset_cooldown(self):
        with self._lock:
            self._last_trigger_time = 0.0
