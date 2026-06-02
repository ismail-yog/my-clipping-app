"""
StreamClipper — Scene Detector
Finds scene changes in a video using PySceneDetect to ensure clips
are cut on visual boundaries rather than awkwardly mid-scene.
"""

import logging
from pathlib import Path
from typing import Optional

from scenedetect import detect, ContentDetector, SceneManager, open_video

logger = logging.getLogger("streamclipper.scene_detector")


class SceneDetector:
    """Detects scene boundaries to adjust clip start/end times."""

    def __init__(self, threshold: float = 27.0):
        self.threshold = threshold

    def find_nearest_scenes(
        self, video_path: Path, start_sec: float, end_sec: float
    ) -> tuple[float, float]:
        """
        Scan the video around the target boundaries to find the nearest scene cuts.
        If a scene cut is within a reasonable threshold (e.g. 2-3 seconds), snap to it.
        """
        try:
            logger.info("Detecting scene cuts around %.1fs - %.1fs...", start_sec, end_sec)
            
            # Since running on the whole video is slow, we should theoretically seek,
            # but scenedetect can be slow if we seek without keyframes. 
            # We'll just run detect() on a chunk around our target times using start/end framing.
            
            # We will grab a 10s window around start and a 10s window around end.
            start_window_start = max(0, start_sec - 5.0)
            start_window_end = start_sec + 5.0
            
            end_window_start = max(0, end_sec - 5.0)
            end_window_end = end_sec + 5.0
            
            # Detect scenes around START
            start_cuts = self._detect_cuts(video_path, start_window_start, start_window_end)
            
            # Detect scenes around END
            end_cuts = self._detect_cuts(video_path, end_window_start, end_window_end)
            
            # Snap start to nearest cut
            adjusted_start = start_sec
            min_start_diff = 5.0
            for cut in start_cuts:
                diff = abs(cut - start_sec)
                if diff < min_start_diff:
                    min_start_diff = diff
                    adjusted_start = cut
                    
            # Snap end to nearest cut
            adjusted_end = end_sec
            min_end_diff = 5.0
            for cut in end_cuts:
                diff = abs(cut - end_sec)
                if diff < min_end_diff:
                    min_end_diff = diff
                    adjusted_end = cut
                    
            if adjusted_start != start_sec:
                logger.info("Snapped start: %.1f -> %.1f", start_sec, adjusted_start)
            if adjusted_end != end_sec:
                logger.info("Snapped end: %.1f -> %.1f", end_sec, adjusted_end)
                
            # Avoid invalid durations
            if adjusted_end - adjusted_start < 5.0:
                return start_sec, end_sec
                
            return adjusted_start, adjusted_end

        except Exception as e:
            logger.error("Scene detection failed: %s", e)
            return start_sec, end_sec

    def _detect_cuts(self, video_path: Path, start: float, end: float) -> list[float]:
        """Detect cuts in a specific time window."""
        try:
            video = open_video(str(video_path))
            # Seek to start
            video.seek(start)
            
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=self.threshold))
            
            # Process until end
            # Calculate frames to process
            fps = video.frame_rate
            duration_frames = int((end - start) * fps)
            
            if duration_frames > 0:
                scene_manager.detect_scenes(video, duration=duration_frames)
                
            cut_list = scene_manager.get_scene_list()
            # return the start times of the scenes
            return [scene[0].get_seconds() for scene in cut_list]
            
        except Exception:
            return []
