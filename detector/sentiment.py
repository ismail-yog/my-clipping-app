"""
StreamClipper — Sentiment Detector
Transcribes audio with faster-whisper and classifies emotion
using a HuggingFace DistilRoBERTa model.
"""

import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import config

logger = logging.getLogger("streamclipper.sentiment")


@dataclass
class TranscriptWord:
    word: str
    start: float
    end: float
    probability: float


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list[TranscriptWord]


@dataclass
class SentimentEvent:
    timestamp: float
    offset_seconds: float
    text: str
    emotion: str
    confidence: float
    score: float


class SentimentDetector:
    """
    Two-stage detector:
    1. Transcribe audio with faster-whisper (word-level timestamps)
    2. Classify transcript segments with HuggingFace emotion model
    """

    def __init__(self, thresholds: Optional[config.DetectionThresholds] = None):
        self.thresholds = thresholds or config.thresholds
        self._whisper_model = None
        self._emotion_pipeline = None
        self._events: list[SentimentEvent] = []
        self._transcripts: list[TranscriptSegment] = []

    def _load_whisper(self):
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            logger.info("Loading Whisper model: %s", config.WHISPER_MODEL)
            self._whisper_model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
            logger.info("Whisper model loaded")
        return self._whisper_model

    def _load_emotion(self):
        if self._emotion_pipeline is None:
            from transformers import pipeline
            logger.info("Loading emotion classifier...")
            self._emotion_pipeline = pipeline(
                "text-classification",
                model="j-hartmann/emotion-english-distilroberta-base",
                top_k=None,
                device=-1,  # CPU; change to 0 for GPU
            )
            logger.info("Emotion classifier loaded")
        return self._emotion_pipeline

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Transcribe audio file and return segments with word timestamps."""
        model = self._load_whisper()
        try:
            segments_iter, info = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language="en",
                vad_filter=True,
            )
            logger.debug("Transcribing: %s (lang=%s, prob=%.2f)",
                         audio_path, info.language, info.language_probability)

            segments = []
            for seg in segments_iter:
                words = []
                if seg.words:
                    words = [
                        TranscriptWord(
                            word=w.word.strip(),
                            start=w.start,
                            end=w.end,
                            probability=w.probability,
                        )
                        for w in seg.words
                    ]

                segments.append(TranscriptSegment(
                    text=seg.text.strip(),
                    start=seg.start,
                    end=seg.end,
                    words=words,
                ))

            self._transcripts.extend(segments)
            logger.info("Transcribed %d segments from %s", len(segments), audio_path.name)
            return segments

        except Exception as e:
            logger.error("Transcription failed: %s", e)
            return []

    def classify_emotions(
        self,
        segments: list[TranscriptSegment],
        reference_time: Optional[float] = None,
    ) -> list[SentimentEvent]:
        """Classify emotion for each transcript segment."""
        classifier = self._load_emotion()
        ref_time = reference_time or time.time()
        events = []

        target_emotions = set(self.thresholds.sentiment_emotions)
        min_conf = self.thresholds.sentiment_min_confidence

        for seg in segments:
            if not seg.text or len(seg.text) < 5:
                continue

            try:
                results = classifier(seg.text[:512])
                if not results or not results[0]:
                    continue

                # results[0] is a list of {label, score} sorted by score
                top = results[0][0]
                emotion = top["label"]
                confidence = top["score"]

                # Only flag emotions in our target list above threshold
                if emotion in target_emotions and confidence >= min_conf:
                    score = min(1.0, confidence / 0.9)
                    event = SentimentEvent(
                        timestamp=ref_time + seg.start,
                        offset_seconds=seg.start,
                        text=seg.text,
                        emotion=emotion,
                        confidence=confidence,
                        score=score,
                    )
                    events.append(event)

            except Exception as e:
                logger.debug("Emotion classification error: %s", e)

        self._events.extend(events)
        logger.info("Sentiment: %d events from %d segments", len(events), len(segments))
        return events

    def predict(self, text: str) -> list[dict]:
        """Predict emotion for a single block of text."""
        classifier = self._load_emotion()
        try:
            return classifier(text[:512])
        except Exception:
            return []

    def analyze(self, audio_path: Path, reference_time: Optional[float] = None) -> list[SentimentEvent]:
        """Full pipeline: transcribe then classify."""
        segments = self.transcribe(audio_path)
        if not segments:
            return []
        return self.classify_emotions(segments, reference_time)

    @property
    def recent_events(self) -> list[SentimentEvent]:
        cutoff = time.time() - 300
        return [e for e in self._events if e.timestamp >= cutoff]

    @property
    def recent_transcripts(self) -> list[TranscriptSegment]:
        return self._transcripts[-50:]

    def clear_events(self):
        self._events.clear()
        self._transcripts.clear()
