"""
StreamClipper — Audio Spike Detector
Detects volume spikes in audio using librosa RMS analysis.
"""

import time
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import numpy as np
import config

logger = logging.getLogger("streamclipper.audio")


@dataclass
class AudioEvent:
    timestamp: float
    offset_seconds: float
    magnitude_db: float
    rms_value: float
    duration: float
    score: float


class AudioDetector:
    def __init__(self, thresholds: Optional[config.DetectionThresholds] = None):
        self.thresholds = thresholds or config.thresholds
        self._events: list[AudioEvent] = []
        self._librosa = None

    def _load_librosa(self):
        if self._librosa is None:
            import librosa
            self._librosa = librosa
        return self._librosa

    def analyze(self, audio_path: Path, reference_time: Optional[float] = None) -> list[AudioEvent]:
        librosa = self._load_librosa()
        ref_time = reference_time or time.time()
        try:
            y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
            if len(y) == 0:
                return []

            hop_length = int(sr * 0.01)
            frame_length = int(sr * 0.025)
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            if len(rms) == 0:
                return []

            rms_db = librosa.amplitude_to_db(rms, ref=np.max)
            window_size = max(1, min(int(2.0 / (hop_length / sr)), len(rms_db)))
            rolling_avg = np.convolve(rms_db, np.ones(window_size) / window_size, mode="same")

            spike_mask = (rms_db - rolling_avg) > self.thresholds.audio_rms_spike_db
            events = self._extract_events(spike_mask, rms_db, rolling_avg, rms, hop_length, sr, ref_time)
            self._events.extend(events)
            logger.info("Audio: %d spikes in %.1fs", len(events), len(y) / sr)
            return events
        except Exception as e:
            logger.error("Audio analysis failed: %s", e)
            return []

    def _extract_events(self, spike_mask, rms_db, rolling_avg, rms_raw, hop_length, sr, ref_time):
        events = []
        in_spike = False
        spike_start = 0

        for i in range(len(spike_mask)):
            if spike_mask[i] and not in_spike:
                in_spike = True
                spike_start = i
            elif not spike_mask[i] and in_spike:
                in_spike = False
                ev = self._make_event(spike_start, i, rms_db, rolling_avg, rms_raw, hop_length, sr, ref_time)
                if ev.duration >= 0.3:
                    events.append(ev)

        if in_spike:
            ev = self._make_event(spike_start, len(spike_mask) - 1, rms_db, rolling_avg, rms_raw, hop_length, sr, ref_time)
            if ev.duration >= 0.3:
                events.append(ev)

        return events

    def _make_event(self, start_idx, end_idx, rms_db, rolling_avg, rms_raw, hop_length, sr, ref_time):
        offset_start = start_idx * hop_length / sr
        offset_end = end_idx * hop_length / sr
        region = rms_db[start_idx:end_idx + 1]
        avg_region = rolling_avg[start_idx:end_idx + 1]
        magnitude = float(np.max(region - avg_region))
        threshold = self.thresholds.audio_rms_spike_db
        score = min(1.0, max(0.0, magnitude / (threshold * 2)))
        return AudioEvent(
            timestamp=ref_time + offset_start,
            offset_seconds=offset_start,
            magnitude_db=magnitude,
            rms_value=float(np.mean(rms_raw[start_idx:end_idx + 1])),
            duration=offset_end - offset_start,
            score=score,
        )

    @property
    def recent_events(self) -> list[AudioEvent]:
        cutoff = time.time() - 300
        return [e for e in self._events if e.timestamp >= cutoff]

    def clear_events(self):
        self._events.clear()
