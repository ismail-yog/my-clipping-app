"""
StreamClipper — YOLOv8 Subject Tracking & Dynamic 9:16 Reframing Engine
Extracts vertical 9:16 frames from standard 16:9 inputs with EMA camera smoothing,
strict VRAM eviction, and FFmpeg runtime sendcmd crop coordinate updates.
"""

import gc
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import List, Tuple, Optional, Union
import urllib.parse

import cv2
import numpy as np
import torch

from processor.subprocess_utils import (
    run_command_safely,
    safe_unlink,
    SubprocessExecutionError,
    MediaProcessingError,
)

logger = logging.getLogger("streamclipper.yolo_reframe")


class ReframingError(MediaProcessingError):
    """Raised when reframing analysis or FFmpeg processing fails."""
    pass


def _escape_ffmpeg_path(path: Path) -> str:
    """
    Sanitizes and escapes a file path for FFmpeg filtergraph strings on both Windows and POSIX.
    On Windows: converts backslashes to forward slashes and escapes drive colons (e.g. C\\:/path).
    """
    p_str = str(path.resolve()).replace("\\", "/")
    if len(p_str) > 1 and p_str[1] == ":":
        p_str = p_str[0] + "\\:" + p_str[2:]
    return p_str


class VideoReframer:
    """
    Surgically reframes horizontal 16:9 streams into stabilized 9:16 vertical video
    using YOLOv8 person tracking and dynamic sendcmd crop updating.
    """

    def __init__(self, scratchpad_dir: Optional[Union[str, Path]] = None):
        if scratchpad_dir is None or str(scratchpad_dir).startswith("/tmp"):
            # Sanitize for Windows compatibility while keeping standard temp location
            base_temp = Path(tempfile.gettempdir()) / "streamclipper_scratch"
            self.scratchpad = base_temp
        else:
            self.scratchpad = Path(scratchpad_dir)
        self.scratchpad.mkdir(parents=True, exist_ok=True)

    def _calculate_smooth_centers(
        self, input_video: Path, alpha: float = 0.08
    ) -> Tuple[List[float], float, int, int]:
        """
        Runs YOLOv8 person detection, computes bounding box centers, and applies
        an Exponential Moving Average (EMA) filter to prevent camera jitter.
        Guarantees complete VRAM eviction upon completion.
        """
        if not input_video.exists():
            raise ReframingError(f"Input video does not exist: {input_video}")

        cap = cv2.VideoCapture(str(input_video))
        if not cap.isOpened():
            raise ReframingError(f"Failed to open video file via OpenCV: {input_video}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or np.isnan(fps):
            fps = 60.0  # Fallback to standard 60fps

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            cap.release()
            raise ReframingError(f"Invalid video dimensions: {width}x{height}")

        default_center = width / 2.0
        centers: List[float] = []

        # Probe hardware device: leverage GPU if CUDA is available, otherwise CPU
        device = 0 if torch.cuda.is_available() else "cpu"

        # Defer import of ultralytics to avoid hard import crash if not installed
        try:
            from ultralytics import YOLO
        except ImportError as e:
            cap.release()
            raise ReframingError("ultralytics package is required. Run: pip install ultralytics") from e

        model = None
        try:
            logger.info("Initializing YOLOv8n on device=%s for reframing tracking", device)
            model = YOLO("yolov8n.pt")
            current_smoothed = default_center

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                # Inference strictly on person class (class 0)
                results = model.predict(source=frame, classes=[0], verbose=False, device=device)
                boxes = results[0].boxes

                if len(boxes) > 0:
                    # Select largest detected person by bounding box area
                    areas = [
                        (float(b.xyxy[0][2] - b.xyxy[0][0])) * (float(b.xyxy[0][3] - b.xyxy[0][1]))
                        for b in boxes
                    ]
                    max_idx = int(np.argmax(areas))
                    box = boxes[max_idx].xyxy[0].cpu().numpy()
                    detected_center = float((box[0] + box[2]) / 2.0)
                else:
                    detected_center = current_smoothed

                # Exponential Moving Average filter
                current_smoothed = (alpha * detected_center) + ((1.0 - alpha) * current_smoothed)
                centers.append(current_smoothed)

        finally:
            cap.release()
            # Strict VRAM memory boundary cleanup
            if model is not None:
                del model
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            logger.info("VRAM memory evicted successfully after YOLO tracking")

        if not centers:
            raise ReframingError(f"No frames decoded from input video: {input_video}")

        return centers, fps, width, height

    def reframe_to_vertical(
        self, input_video: Path, output_video: Path, alpha: float = 0.08
    ) -> Path:
        """
        Generates FFmpeg sendcmd script and executes 9:16 surgical reframing.
        Enforces CFR 60fps and audio/video sync.
        """
        input_video = Path(input_video).resolve()
        output_video = Path(output_video).resolve()
        output_video.parent.mkdir(parents=True, exist_ok=True)

        centers, fps, in_w, in_h = self._calculate_smooth_centers(input_video, alpha=alpha)

        # Target crop width for 9:16 given the source height (e.g. 1080 * 9/16 = 607.5 -> 608)
        crop_w = int(in_h * (9.0 / 16.0))
        # Ensure dimensions are divisible by 2 for H.264 macroblock alignment
        if crop_w % 2 != 0:
            crop_w += 1

        cmd_file = self.scratchpad / f"{input_video.stem}_{int(time.time() * 1000)}_crop.cmd"

        try:
            # Build sendcmd script
            with open(cmd_file, "w", encoding="utf-8") as f:
                for idx, center in enumerate(centers):
                    time_start = idx / fps
                    time_end = (idx + 1) / fps
                    # Clamp coordinates within frame boundaries
                    x_pos = int(center - (crop_w / 2.0))
                    x_pos = max(0, min(x_pos, in_w - crop_w))
                    f.write(f"{time_start:.3f}-{time_end:.3f} [enter] crop x {x_pos};\n")

            # Escape command file path for FFmpeg filtergraph
            escaped_cmd = _escape_ffmpeg_path(cmd_file)

            # Complex filter: dynamic crop update -> upscale to 1080x1920 -> force CFR 60fps
            filter_complex = (
                f"[0:v]sendcmd=f='{escaped_cmd}',crop=w={crop_w}:h={in_h}:x=0:y=0,"
                f"scale=1080:1920:flags=lanczos,fps=fps=60[v_out]"
            )

            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", str(input_video),
                "-filter_complex", filter_complex,
                "-map", "[v_out]",
                "-map", "0:a?",
                "-vsync", "cfr",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_video),
            ]

            logger.info("Executing FFmpeg dynamic reframe on %s -> %s", input_video.name, output_video.name)
            run_command_safely(ffmpeg_cmd, timeout=300.0)

            if not output_video.exists() or output_video.stat().st_size == 0:
                raise ReframingError(f"FFmpeg dynamic reframe generated empty file: {output_video}")

            return output_video

        finally:
            safe_unlink(cmd_file)
