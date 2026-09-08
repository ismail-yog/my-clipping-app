import unittest
from dataclasses import dataclass
from pipeline import calculate_dynamic_clip_duration_ms
import config

@dataclass
class MockSegment:
    start: float
    end: float
    text: str

def test_dynamic_duration_bounds_and_sentence_snapping():
    # Test 1: Empty transcript returns target duration clamped to 30-45s
    dur_ms = calculate_dynamic_clip_duration_ms([], start_offset_ms=5000, default_duration_ms=60000)
    assert dur_ms == 45000, f"Expected 45000ms max clamp, got {dur_ms}"

    dur_ms_low = calculate_dynamic_clip_duration_ms([], start_offset_ms=5000, default_duration_ms=10000)
    assert dur_ms_low == 30000, f"Expected 30000ms min clamp, got {dur_ms_low}"

    # Test 2: Transcript with a sentence ending at 38s (33s clip duration from 5s offset)
    segments = [
        MockSegment(start=5.0, end=15.0, text="Yo chat look at this right here"),
        MockSegment(start=15.0, end=28.0, text="He really thought he could sneak past us"),
        MockSegment(start=28.0, end=38.5, text="No shot that just happened!"),
        MockSegment(start=38.5, end=48.0, text="Wait there is another guy coming"),
    ]
    # start_offset = 5.0s (5000ms)
    # segment 3 ends at 38.5s (38500ms) -> duration = 38500 - 5000 = 33500ms (33.5s)
    dur_ms_snap = calculate_dynamic_clip_duration_ms(segments, start_offset_ms=5000)
    assert dur_ms_snap == 33500, f"Expected sentence snap to 33500ms, got {dur_ms_snap}"
    assert 30000 <= dur_ms_snap <= 45000

    # Test 3: Sentence ending exactly at 44s (39s duration)
    segments_long = [
        MockSegment(start=5.0, end=44.0, text="That was the biggest play of the entire tournament."),
        MockSegment(start=44.0, end=60.0, text="Let us see the instant replay now."),
    ]
    dur_ms_long = calculate_dynamic_clip_duration_ms(segments_long, start_offset_ms=5000)
    assert dur_ms_long == 39000, f"Expected 39000ms, got {dur_ms_long}"
    assert 30000 <= dur_ms_long <= 45000

    # Test 4: Verify config constants
    assert config.clip_settings.min_duration == 30
    assert config.clip_settings.max_duration == 45
    assert 30 <= config.clip_settings.default_duration <= 45
    assert 30 <= config.vod_settings.clip_duration <= 45
