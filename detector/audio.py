"""
StreamClipper — Audio Spike Detector
Detects volume spikes, sustained excitement, and silence breaks in audio using RMS energy analysis.
"""

import time
import logging
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
import numpy as np

import config

logger = logging.getLogger("streamclipper.detector.audio")


@dataclass
class AudioEvent:
    """Represents a detected audio spike or excitement event."""
    timestamp: float  # Unix time
    event_type: str  # "spike", "sustained_high", "silence_break"
    intensity: float  # Scale of 0-1
    db_level: float

    @property
    def score(self) -> float:
        """Compatibility property for scorer that queries event.score."""
        return self.intensity


class AudioDetector:
    """Analyzes stream audio chunks to detect excitement thresholds and sudden volume changes."""

    def __init__(self, thresholds: Optional[config.DetectionThresholds] = None):
        self.thresholds = thresholds or config.thresholds
        self.recent_events: List[AudioEvent] = []
        self._lock = threading.Lock()
        self._rolling_avg_db: float = -30.0  # Default baseline in dBFS
        self._librosa = None

    def _load_librosa(self):
        """Lazy load librosa to optimize startup speed."""
        if self._librosa is None:
            import librosa
            self._librosa = librosa
        return self._librosa

    def analyze(self, audio_path: Path, reference_time: Optional[float] = None) -> List[AudioEvent]:
        """
        Analyze a 10-second WAV file, detect volume events, and update the baseline.
        Returns a list of parsed AudioEvent dataclass instances.
        """
        librosa = self._load_librosa()
        ref_time = reference_time or time.time()
        
        try:
            # 1. Load audio file (mono, 16kHz)
            y, sr = librosa.load(str(audio_path), sr=16000, mono=True)
            if len(y) == 0:
                return []

            # 2. Calculate RMS energy per frame (hop_length=512, frame_length=2048)
            hop_length = 512
            frame_length = 2048
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            if len(rms) == 0:
                return []

            # 3. Convert RMS amplitudes to decibels (dB)
            rms = np.clip(rms, 1e-5, None)  # Avoid division by zero
            rms_db = 20 * np.log10(rms)

            # 4. Update the rolling average baseline with current chunk mean
            current_mean_db = float(np.mean(rms_db))
            self._update_rolling_avg(current_mean_db)

            # 5. Segment spikes and compile excitement events
            events = self._extract_events(rms_db, hop_length, sr, ref_time)

            # 6. Save events to rolling cache and prune old ones
            with self._lock:
                self.recent_events.extend(events)
                self._prune_old_events()

            logger.info("Audio: %d spikes in %.1fs (rolling baseline: %.1f dB)", len(events), len(y) / sr, self._rolling_avg_db)
            return events

        except Exception as e:
            logger.error("Audio spike analysis failed for %s: %s", audio_path.name, e)
            return []

    def _update_rolling_avg(self, current_db: float):
        """Update overall baseline using an exponential moving average (EMA)."""
        self._rolling_avg_db = 0.95 * self._rolling_avg_db + 0.05 * current_db

    def _extract_events(self, rms_db: np.ndarray, hop_length: int, sr: int, ref_time: float) -> List[AudioEvent]:
        """Helper to scan rms db frames and find indices matching excitement thresholds."""
        spike_mask = rms_db > (self._rolling_avg_db + self.thresholds.audio_rms_spike_db)
        
        events = []
        in_spike = False
        start_idx = 0

        for i in range(len(spike_mask)):
            if spike_mask[i] and not in_spike:
                in_spike = True
                start_idx = i
            elif not spike_mask[i] and in_spike:
                in_spike = False
                end_idx = i - 1
                ev = self._create_event(start_idx, end_idx, rms_db, hop_length, sr, ref_time)
                if ev:
                    events.append(ev)

        if in_spike:
            end_idx = len(spike_mask) - 1
            ev = self._create_event(start_idx, end_idx, rms_db, hop_length, sr, ref_time)
            if ev:
                events.append(ev)

        return events

    def _create_event(self, start_idx: int, end_idx: int, rms_db: np.ndarray, hop_length: int, sr: int, ref_time: float) -> Optional[AudioEvent]:
        """Compute type, intensity, and metadata for a continuous region of high volume."""
        duration = (end_idx - start_idx + 1) * hop_length / sr
        if duration < 0.1:  # Filter out extremely brief clicks/pops
            return None

        mean_db = float(np.mean(rms_db[start_idx:end_idx + 1]))
        db_diff = mean_db - self._rolling_avg_db
        
        # Scaling intensity between 0.0 and 1.0 (relative to baseline + spike threshold)
        intensity = min(1.0, max(0.0, db_diff / 24.0))

        event_timestamp = ref_time + (start_idx * hop_length / sr)
        
        # Classify the trigger type
        event_type = "spike"
        if duration >= 2.0:
            event_type = "sustained_high"

        # Check for 'silence break' (quiet period of < -12dB below baseline for 2s preceding the event)
        lookback_frames = int(2.0 * sr / hop_length)
        if start_idx > 0:
            silence_start = max(0, start_idx - lookback_frames)
            prev_region = rms_db[silence_start:start_idx]
            if len(prev_region) >= int(1.0 * sr / hop_length) and np.mean(prev_region) < self._rolling_avg_db - 12:
                event_type = "silence_break"

        return AudioEvent(
            timestamp=event_timestamp,
            event_type=event_type,
            intensity=intensity,
            db_level=mean_db
        )

    def _prune_old_events(self):
        """Remove events older than 60 seconds from the cache."""
        cutoff = time.time() - 60.0
        self.recent_events = [e for e in self.recent_events if e.timestamp >= cutoff]

    def get_recent_events(self, last_n_seconds: float = 30.0) -> List[AudioEvent]:
        """Fetch filtered audio events within the specified time window."""
        with self._lock:
            cutoff = time.time() - last_n_seconds
            return [e for e in self.recent_events if e.timestamp >= cutoff]

    def clear_events(self):
        """Reset the cached events cache."""
        with self._lock:
            self.recent_events.clear()
