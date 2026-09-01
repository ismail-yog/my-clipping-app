"""
StreamClipper / LumiClip — Smart Crop & Active Speaker Tracking Engine
Converts horizontal 16:9 content into viral vertical 9:16 formats using
MediaPipe/OpenCV face tracking, Mouth Aspect Ratio (MAR) speaker detection,
and Exponential Moving Average (EMA) camera stabilization.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np

logger = logging.getLogger("streamclipper.smart_crop")


@dataclass
class FaceTrack:
    track_id: int
    t_sec: float
    cx: int
    cy: int
    w: int
    h: int
    mouth_openness: float = 0.0
    is_speaking: bool = False


@dataclass
class CropWindow:
    t_sec: float
    crop_x: int
    crop_y: int
    crop_w: int
    crop_h: int


class SmartCrop:
    """Calculates active-speaker crop parameters and generates complex FFmpeg filtergraphs."""

    def __init__(self, ema_alpha: float = 0.15, movement_threshold_px: int = 30):
        self.ema_alpha = ema_alpha
        self.movement_threshold_px = movement_threshold_px
        
        # Load OpenCV Haar cascade as ultra-reliable zero-dependency fallback detector
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def detect_faces_in_frame(
        self,
        frame_bgr: np.ndarray,
        t_sec: float
    ) -> List[FaceTrack]:
        """
        Detect face bounding boxes and estimate mouth openness in a single frame.
        """
        h_img, w_img = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
        
        tracks: List[FaceTrack] = []
        for idx, (fx, fy, fw, fh) in enumerate(faces):
            cx = int(fx + fw / 2)
            cy = int(fy + fh / 2)

            # Estimate mouth movement in lower third of the face box
            mouth_roi_y = int(fy + fh * 0.65)
            mouth_roi_h = int(fh * 0.35)
            mouth_roi_x = int(fx + fw * 0.2)
            mouth_roi_w = int(fw * 0.6)
            
            mouth_openness = 0.0
            if (
                0 <= mouth_roi_y < h_img
                and 0 <= mouth_roi_x < w_img
                and mouth_roi_y + mouth_roi_h <= h_img
                and mouth_roi_x + mouth_roi_w <= w_img
            ):
                mouth_patch = gray[mouth_roi_y:mouth_roi_y + mouth_roi_h, mouth_roi_x:mouth_roi_x + mouth_roi_w]
                # High-contrast variance in mouth patch correlates with mouth movement / speaking
                mouth_openness = float(np.std(mouth_patch))

            tracks.append(
                FaceTrack(
                    track_id=idx,
                    t_sec=t_sec,
                    cx=cx,
                    cy=cy,
                    w=fw,
                    h=fh,
                    mouth_openness=mouth_openness,
                    is_speaking=(mouth_openness > 18.0)
                )
            )

        return tracks

    def get_crop_filter(
        self,
        video_path: Path,
        start_sec: float,
        target_width: int = 1080,
        target_height: int = 1920,
        layout_type: str = "single_speaker",
        duration: float = 30.0,
    ) -> str:
        """
        Analyze video segment and compile a production-ready FFmpeg filtergraph.
        
        Supported layout_type:
          - 'single_speaker': 9:16 crop dynamically centered on active speaker with EMA smoothing.
          - 'split_screen' or 'podcast': Top/Bottom 2-speaker vertical stack.
          - 'gamer': Facecam top window, gameplay center crop bottom window.
          - 'blurred_background': 16:9 centered box over blurred 9:16 canvas.
          - 'basic': Standard center crop.
        """
        center_crop = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:(in_w-{target_width})/2:(in_h-{target_height})/2,"
            f"setsar=1"
        )

        if layout_type == "basic":
            return center_crop

        if layout_type == "blurred_background":
            return (
                f"split=2[fg][bg];"
                f"[bg]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height},boxblur=25:5[blurred];"
                f"[fg]scale={target_width}:-1:force_original_aspect_ratio=decrease[scaled];"
                f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return center_crop

            vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if vid_w <= 0 or vid_h <= 0:
                cap.release()
                return center_crop

            # Scan video frames at 0.5s intervals
            scan_interval_sec = 0.5
            total_steps = int(duration / scan_interval_sec) + 1
            
            frame_detections: List[List[FaceTrack]] = []
            for step in range(total_steps):
                t_rel = step * scan_interval_sec
                t_abs = start_sec + t_rel
                cap.set(cv2.CAP_PROP_POS_MSEC, t_abs * 1000)
                ret, frame = cap.read()
                if not ret:
                    continue
                tracks = self.detect_faces_in_frame(frame, t_rel)
                frame_detections.append(tracks)

            cap.release()

            # Flatten all detections to check presence
            all_tracks = [t for frame_list in frame_detections for t in frame_list]
            if not all_tracks:
                logger.info("No faces detected in video segment. Defaulting to center crop.")
                return center_crop

            if layout_type in ("split_screen", "podcast"):
                return self._build_podcast_split_filter(frame_detections, vid_w, vid_h, target_width, target_height, duration)
            elif layout_type == "gamer":
                return self._build_gamer_split_filter(frame_detections, vid_w, vid_h, target_width, target_height, duration)
            else:
                return self._build_single_speaker_filter(frame_detections, vid_w, vid_h, target_width, target_height, duration)

        except Exception as e:
            logger.error("SmartCrop generation failed: %s. Reverting to center crop.", e)
            return center_crop

    def _build_single_speaker_filter(
        self,
        frame_detections: List[List[FaceTrack]],
        vid_w: int,
        vid_h: int,
        target_w: int,
        target_h: int,
        duration: float
    ) -> str:
        """Dynamic 9:16 crop locked on active speaker with EMA trajectory smoothing."""
        target_crop_w = int(vid_h * (9 / 16))
        target_crop_h = vid_h

        # Compute active speaker center per timestamp
        raw_centers: List[Tuple[float, int]] = []
        for tracks in frame_detections:
            if not tracks:
                continue
            t_sec = tracks[0].t_sec
            # Pick speaking face or largest face
            speaking_faces = [t for t in tracks if t.is_speaking]
            if speaking_faces:
                primary = max(speaking_faces, key=lambda t: t.mouth_openness)
            else:
                primary = max(tracks, key=lambda t: t.w * t.h)
            raw_centers.append((t_sec, primary.cx))

        if not raw_centers:
            return f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={target_w}:{target_h},setsar=1"

        # Apply EMA smoothing to the center X coordinates
        smoothed_x: List[Tuple[float, int]] = []
        curr_ema_x = float(raw_centers[0][1])
        for t_sec, cx in raw_centers:
            curr_ema_x = self.ema_alpha * float(cx) + (1.0 - self.ema_alpha) * curr_ema_x
            crop_x = int(max(0, min(curr_ema_x - target_crop_w / 2, vid_w - target_crop_w)))
            smoothed_x.append((t_sec, crop_x))

        # Build stable regions for smooth camera panning
        regions = self._build_motion_regions(smoothed_x, duration)
        expr_x = self._compile_ffmpeg_regions(regions)

        filter_graph = (
            f"crop={target_crop_w}:{target_crop_h}:'{expr_x}':0,"
            f"scale={target_w}:{target_h},"
            f"setsar=1"
        )
        return filter_graph

    def _build_gamer_split_filter(
        self,
        frame_detections: List[List[FaceTrack]],
        vid_w: int,
        vid_h: int,
        target_w: int,
        target_h: int,
        duration: float
    ) -> str:
        """Facecam on top half, gameplay centered on bottom half."""
        all_faces = [t for frame_list in frame_detections for t in frame_list]
        avg_face_w = int(sum(t.w for t in all_faces) / len(all_faces))
        facecam_side = min(int(avg_face_w * 2.4), vid_w, vid_h)

        face_positions: List[Tuple[float, int, int]] = []
        for tracks in frame_detections:
            if not tracks:
                continue
            t_sec = tracks[0].t_sec
            best_face = max(tracks, key=lambda t: t.w * t.h)
            wx = int(max(0, min(best_face.cx - facecam_side // 2, vid_w - facecam_side)))
            wy = int(max(0, min(best_face.cy - facecam_side // 2, vid_h - facecam_side)))
            face_positions.append((t_sec, wx, wy))

        if not face_positions:
            wx_val = (vid_w - facecam_side) // 2
            wy_val = (vid_h - facecam_side) // 2
            expr_x, expr_y = str(wx_val), str(wy_val)
        else:
            regions_x = self._build_motion_regions([(p[0], p[1]) for p in face_positions], duration)
            regions_y = self._build_motion_regions([(p[0], p[2]) for p in face_positions], duration)
            expr_x = self._compile_ffmpeg_regions(regions_x)
            expr_y = self._compile_ffmpeg_regions(regions_y)

        half_h = target_h // 2
        return (
            f"split=2[facecam][gameplay];"
            f"[facecam]crop={facecam_side}:{facecam_side}:'{expr_x}':'{expr_y}',scale={target_w}:{half_h}[top];"
            f"[gameplay]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={target_w}:{half_h}[bot];"
            f"[top][bot]vstack,setsar=1"
        )

    def _build_podcast_split_filter(
        self,
        frame_detections: List[List[FaceTrack]],
        vid_w: int,
        vid_h: int,
        target_w: int,
        target_h: int,
        duration: float
    ) -> str:
        """Split podcast/interview layout (Speaker 1 Top / Speaker 2 Bottom)."""
        half_h = target_h // 2
        crop_box_w = int(vid_w * 0.48)
        crop_box_h = int(vid_h * 0.85)

        # Left speaker crop [spk1], Right speaker crop [spk2]
        return (
            f"split=2[spk1][spk2];"
            f"[spk1]crop={crop_box_w}:{crop_box_h}:0:(in_h-{crop_box_h})/2,scale={target_w}:{half_h}[top];"
            f"[spk2]crop={crop_box_w}:{crop_box_h}:{vid_w - crop_box_w}:(in_h-{crop_box_h})/2,scale={target_w}:{half_h}[bot];"
            f"[top][bot]vstack,setsar=1"
        )

    def _build_motion_regions(self, timed_coords: List[Tuple[float, int]], duration: float) -> List[Dict[str, Any]]:
        """Create static windows with linear transition interpolation."""
        if not timed_coords:
            return [{"start": 0.0, "end": duration + 5.0, "type": "static", "val": 0}]

        regions: List[Dict[str, Any]] = []
        curr_val = timed_coords[0][1]
        last_t = 0.0

        for t_sec, val in timed_coords[1:]:
            if abs(val - curr_val) > self.movement_threshold_px:
                # Add static region
                regions.append({"start": last_t, "end": max(0.0, t_sec - 0.5), "type": "static", "val": curr_val})
                # Add smooth 0.5s transition
                regions.append({
                    "start": max(0.0, t_sec - 0.5),
                    "end": t_sec,
                    "type": "transition",
                    "val_start": curr_val,
                    "val_end": val
                })
                curr_val = val
                last_t = t_sec

        regions.append({"start": last_t, "end": duration + 10.0, "type": "static", "val": curr_val})
        return regions

    def _compile_ffmpeg_regions(self, regions: List[Dict[str, Any]]) -> str:
        """Compile region list into recursive FFmpeg if() conditional expression."""
        if not regions:
            return "0"

        last = regions[-1]
        expr = str(last["val_end"] if last["type"] == "transition" else last["val"])

        for r in reversed(regions[:-1]):
            if r["type"] == "static":
                expr = f"if(lt(t,{r['end']:.2f}),{r['val']},{expr})"
            else:
                dur = max(0.01, r["end"] - r["start"])
                trans = f"{r['val_start']}+({r['val_end']-r['val_start']})*(t-{r['start']:.2f})/{dur:.2f}"
                expr = f"if(lt(t,{r['end']:.2f}),{trans},{expr})"

        return expr
