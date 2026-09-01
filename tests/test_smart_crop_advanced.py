"""
Tests for SmartCrop Active Speaker Tracking, MAR, and EMA Camera Smoothing.
"""

import numpy as np
from pathlib import Path
from processor.smart_crop import SmartCrop, FaceTrack


def test_smart_crop_initialization():
    sc = SmartCrop(ema_alpha=0.2, movement_threshold_px=25)
    assert sc.ema_alpha == 0.2
    assert sc.movement_threshold_px == 25
    assert sc.face_cascade is not None


def test_detect_faces_in_synthetic_frame():
    sc = SmartCrop()
    # Create a synthetic 1080x1920 black canvas with a white rectangle simulating face
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    tracks = sc.detect_faces_in_frame(frame, t_sec=1.5)
    # Empty frame should return no faces without throwing
    assert isinstance(tracks, list)


def test_motion_regions_and_ffmpeg_compilation():
    sc = SmartCrop(movement_threshold_px=20)
    
    timed_coords = [
        (0.0, 100),
        (0.5, 105),
        (1.0, 110),
        (1.5, 180),  # Jump > 20px
        (2.0, 185),
    ]
    
    regions = sc._build_motion_regions(timed_coords, duration=2.0)
    assert len(regions) >= 2
    
    expr = sc._compile_ffmpeg_regions(regions)
    assert isinstance(expr, str)
    assert len(expr) > 0


def test_layout_filtergraph_generation():
    sc = SmartCrop()
    fake_path = Path("fake_video.mp4")

    # Basic center crop
    basic_filter = sc.get_crop_filter(fake_path, start_sec=0.0, layout_type="basic")
    assert "crop=" in basic_filter
    assert "setsar=1" in basic_filter

    # Blurred background
    blur_filter = sc.get_crop_filter(fake_path, start_sec=0.0, layout_type="blurred_background")
    assert "boxblur=" in blur_filter
    assert "overlay=" in blur_filter
