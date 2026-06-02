"""
StreamClipper — Sentiment Detector
Transcribes audio with faster-whisper and detects emotional content using sentiment analysis.
"""

import time
import logging
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

import config

logger = logging.getLogger("streamclipper.detector.sentiment")

# Map sentiment labels to emotions
EMOTION_MAP = {
    "joy": "joy",
    "anger": "anger",
    "surprise": "surprise",
    "sadness": "sadness",
    "fear": "fear",
    "neutral": "neutral",
    "love": "joy",
    "disgust": "anger"
}


@dataclass
class TranscriptWord:
    word: str
    start: float  # seconds
    end: float    # seconds
    probability: float


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: List[TranscriptWord]


@dataclass
class SentimentEvent:
    timestamp: float
    emotion: str  # "joy", "anger", "surprise", "sadness", "fear", "neutral"
    confidence: float  # 0-1
    text_snippet: str  # the words that triggered this

    @property
    def score(self) -> float:
        """Compatibility property for scorer that queries event.score."""
        return self.confidence


class SentimentDetector:
    """Monitors streams and detects emotional cues from transcripts."""

    def __init__(self, thresholds: Optional[config.DetectionThresholds] = None):
        self.thresholds = thresholds or config.thresholds
        self._whisper_model = None
        self._sentiment_pipeline = None
        self.recent_events: List[SentimentEvent] = []
        self._lock = threading.Lock()

    def _load_whisper(self):
        """Lazy load Whisper model to save memory and startup time."""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            logger.info("Loading Whisper model: %s on device: %s (%s)...", 
                        config.WHISPER_MODEL, config.WHISPER_DEVICE, config.WHISPER_COMPUTE_TYPE)
            self._whisper_model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE
            )
            logger.info("Whisper model loaded successfully.")
        return self._whisper_model

    def _load_sentiment_pipeline(self):
        """Lazy load sentiment classifier model to save memory and startup time."""
        if self._sentiment_pipeline is None:
            from transformers import pipeline
            logger.info("Loading sentiment-analysis pipeline (j-hartmann/emotion-english-distilroberta-base)...")
            self._sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model="j-hartmann/emotion-english-distilroberta-base",
                device=-1  # Force CPU to match target speed constraints
            )
            logger.info("Sentiment pipeline loaded successfully.")
        return self._sentiment_pipeline

    def transcribe(self, audio_path: Path) -> List[TranscriptSegment]:
        """Transcribe an audio file using faster-whisper with word-level timestamps."""
        try:
            model = self._load_whisper()
            segments_iter, _ = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language="en",
                vad_filter=True
            )
            
            segments = []
            for seg in segments_iter:
                words = []
                if seg.words:
                    words = [
                        TranscriptWord(
                            word=w.word.strip(),
                            start=w.start,
                            end=w.end,
                            probability=w.probability
                        )
                        for w in seg.words
                    ]
                segments.append(
                    TranscriptSegment(
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                        words=words
                    )
                )
            return segments
        except Exception as e:
            logger.error("Whisper transcription failed for %s: %s", audio_path.name, e, exc_info=True)
            return []

    def analyze(self, audio_path: Path, reference_time: float) -> List[SentimentEvent]:
        """Transcribe audio and analyze emotions in the transcript segments."""
        segments = self.transcribe(audio_path)
        if not segments:
            return []

        pipeline_model = self._load_sentiment_pipeline()
        events = []
        target_emotions = set(self.thresholds.sentiment_emotions)
        min_confidence = self.thresholds.sentiment_min_confidence

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue

            try:
                results = pipeline_model(text[:512])
                if results:
                    # Handle both nested list and list format
                    top_pred = results[0][0] if isinstance(results[0], list) else results[0]
                    raw_label = top_pred.get("label", "neutral")
                    confidence = top_pred.get("score", 0.0)
                else:
                    raw_label = "neutral"
                    confidence = 0.0
            except Exception as e:
                logger.error("Sentiment analysis failed for text snippet '%s': %s", text, e)
                raw_label = "neutral"
                confidence = 1.0

            emotion = EMOTION_MAP.get(raw_label.lower(), "neutral")

            if confidence >= min_confidence and emotion in target_emotions:
                event = SentimentEvent(
                    timestamp=reference_time + seg.start,
                    emotion=emotion,
                    confidence=confidence,
                    text_snippet=text
                )
                events.append(event)

        if events:
            with self._lock:
                self.recent_events.extend(events)
                self._prune_old_events()

        return events

    def _prune_old_events(self):
        """Remove SentimentEvent instances older than 60 seconds."""
        cutoff = time.time() - 60.0
        self.recent_events = [e for e in self.recent_events if e.timestamp >= cutoff]

    def get_recent_events(self, last_n_seconds: float = 30.0) -> List[SentimentEvent]:
        """Fetch filtered sentiment events within the specified time window."""
        with self._lock:
            cutoff = time.time() - last_n_seconds
            return [e for e in self.recent_events if e.timestamp >= cutoff]

    def clear_events(self):
        """Reset the cached events cache."""
        with self._lock:
            self.recent_events.clear()
