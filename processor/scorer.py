"""
StreamClipper — Scorer
Fuses audio, chat, and sentiment signals into a single moment score.
Triggers clip extraction when the score exceeds the threshold.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import deque

import config
from detector.audio import AudioEvent
from detector.chat import ChatEvent
from detector.sentiment import SentimentEvent

logger = logging.getLogger("streamclipper.scorer")


@dataclass
class MomentScore:
    """A scored moment that may trigger a clip."""
    timestamp: float
    audio_score: float
    chat_score: float
    sentiment_score: float
    combined_score: float
    triggered: bool
    audio_events: list = field(default_factory=list)
    chat_events: list = field(default_factory=list)
    sentiment_events: list = field(default_factory=list)


class Scorer:
    """
    Combines detection signals into a unified moment score.
    Uses configurable weights and a cooldown to prevent duplicate clips.
    """

    def __init__(
        self,
        thresholds: Optional[config.DetectionThresholds] = None,
        on_trigger: Optional[Callable[[MomentScore], None]] = None,
    ):
        self.thresholds = thresholds or config.thresholds
        self.on_trigger = on_trigger
        self._scores: deque = deque(maxlen=1000)
        self._last_trigger_time: float = 0.0

    def score_moment(
        self,
        audio_events: list[AudioEvent],
        chat_events: list[ChatEvent],
        sentiment_events: list[SentimentEvent],
        window_seconds: float = 10.0,
    ) -> MomentScore:
        """
        Score the current moment based on recent detection events.

        Looks at events within the last `window_seconds` and computes
        a weighted combination of the peak scores from each detector.
        """
        now = time.time()
        cutoff = now - window_seconds

        # Get peak scores from each detector within the window
        recent_audio = [e for e in audio_events if e.timestamp >= cutoff]
        recent_chat = [e for e in chat_events if e.timestamp >= cutoff]
        recent_sentiment = [e for e in sentiment_events if e.timestamp >= cutoff]

        audio_score = max((e.score for e in recent_audio), default=0.0)
        chat_score = max((e.score for e in recent_chat), default=0.0)
        sentiment_score = max((e.score for e in recent_sentiment), default=0.0)

        # Weighted combination
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

        # Check if we should trigger
        in_cooldown = (now - self._last_trigger_time) < self.thresholds.cooldown_seconds
        triggered = combined >= self.thresholds.moment_threshold and not in_cooldown

        moment = MomentScore(
            timestamp=now,
            audio_score=audio_score,
            chat_score=chat_score,
            sentiment_score=sentiment_score,
            combined_score=combined,
            triggered=triggered,
            audio_events=recent_audio,
            chat_events=recent_chat,
            sentiment_events=recent_sentiment,
        )

        self._scores.append(moment)

        if triggered:
            self._last_trigger_time = now
            logger.info(
                "🎯 MOMENT TRIGGERED! Score=%.2f (audio=%.2f, chat=%.2f, sentiment=%.2f)",
                combined, audio_score, chat_score, sentiment_score,
            )
            if self.on_trigger:
                self.on_trigger(moment)

        return moment

    @property
    def recent_scores(self) -> list[MomentScore]:
        cutoff = time.time() - 300
        return [s for s in self._scores if s.timestamp >= cutoff]

    @property
    def trigger_count(self) -> int:
        return sum(1 for s in self._scores if s.triggered)

    def reset_cooldown(self):
        self._last_trigger_time = 0.0
