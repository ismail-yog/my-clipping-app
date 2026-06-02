"""
StreamClipper — Smart Crop / Split View
Uses OpenCV to detect faces and generate a professional 'Split View' (Face Top, Game Bottom)
layout with dynamic face tracking for viral 9:16 clips.
"""

import logging
from pathlib import Path
import cv2

logger = logging.getLogger("streamclipper.smart_crop")


class SmartCrop:
    """Calculates crop parameters and generates complex Split-View filters with dynamic face tracking."""

    def __init__(self):
        # Load the pre-trained Haar cascade for frontal face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def get_crop_filter(
        self,
        video_path: Path,
        start_sec: float,
        target_width: int,
        target_height: int,
        layout_type: str = "gamer",
        duration: float = 30.0,
    ) -> str:
        """
        Analyze the video segments to find the streamer's face.
        If layout_type is 'basic', returns center-crop filter immediately.
        If 'gamer', detects face frame-by-frame and returns a split view with dynamic camera panning.
        """
        center_crop = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:(in_w-{target_width})/2:(in_h-{target_height})/2,"
            f"setsar=1"
        )

        if layout_type == "basic":
            logger.info("Basic layout requested. Using standard center crop.")
            return center_crop

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return center_crop

            # Total frames and info
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            # Scan face positions at 1-second intervals
            detections = []  # List of (t_rel, cx, cy, side)
            
            for t_rel in range(int(duration) + 1):
                t_abs = start_sec + t_rel
                cap.set(cv2.CAP_PROP_POS_MSEC, t_abs * 1000)
                ret, frame = cap.read()
                if not ret:
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))

                if len(faces) > 0:
                    # Get largest face
                    fx, fy, fw, fh = sorted(faces, key=lambda x: x[2], reverse=True)[0]
                    cx = fx + fw // 2
                    cy = fy + fh // 2
                    side = int(fw * 2.3)
                    detections.append((t_rel, cx, cy, side))

            cap.release()

            if not detections:
                logger.info("No faces detected in video segment. Defaulting to center crop.")
                return center_crop

            # Determine a single constant side size (average of all detections)
            avg_side = int(sum(d[3] for d in detections) / len(detections))
            # Ensure it fits within video bounds
            avg_side = min(avg_side, w, h)

            # Fill missing frames with nearest neighbor interpolation/propagation
            positions = []  # List of (t_rel, cx, cy) for every second
            for t_rel in range(int(duration) + 1):
                # Find closest detection
                closest = min(detections, key=lambda d: abs(d[0] - t_rel))
                positions.append((t_rel, closest[1], closest[2]))

            # Smooth positions using a 3-second moving average
            smoothed_positions = []
            for i in range(len(positions)):
                t_rel = positions[i][0]
                window = positions[max(0, i-1):min(len(positions), i+2)]
                avg_cx = sum(p[1] for p in window) / len(window)
                avg_cy = sum(p[2] for p in window) / len(window)
                
                # Calculate wx and wy (top-left coordinates of the crop square)
                wx = int(max(0, min(avg_cx - avg_side // 2, w - avg_side)))
                wy = int(max(0, min(avg_cy - avg_side // 2, h - avg_side)))
                smoothed_positions.append((t_rel, wx, wy))

            # Build static & transition regions to generate clean FFmpeg expressions
            # Threshold: only move camera if face shifts by more than 45 pixels
            threshold = 45
            regions_x = []
            regions_y = []
            
            curr_x = smoothed_positions[0][1]
            curr_y = smoothed_positions[0][2]
            
            last_t_x = 0.0
            last_t_y = 0.0

            for t_rel, wx, wy in smoothed_positions[1:]:
                # Check X movements
                if abs(wx - curr_x) > threshold:
                    # Record previous static region
                    regions_x.append({"start": last_t_x, "end": t_rel - 1.0, "type": "static", "val": curr_x})
                    # Record transition region (smooth pan over 1 second)
                    regions_x.append({"start": t_rel - 1.0, "end": t_rel, "type": "transition", "val_start": curr_x, "val_end": wx})
                    curr_x = wx
                    last_t_x = t_rel

                # Check Y movements
                if abs(wy - curr_y) > threshold:
                    # Record previous static region
                    regions_y.append({"start": last_t_y, "end": t_rel - 1.0, "type": "static", "val": curr_y})
                    # Record transition region (smooth pan over 1 second)
                    regions_y.append({"start": t_rel - 1.0, "end": t_rel, "type": "transition", "val_start": curr_y, "val_end": wy})
                    curr_y = wy
                    last_t_y = t_rel

            # Append final regions
            regions_x.append({"start": last_t_x, "end": duration + 5.0, "type": "static", "val": curr_x})
            regions_y.append({"start": last_t_y, "end": duration + 5.0, "type": "static", "val": curr_y})

            # Compile regions into math expressions for FFmpeg
            expr_x = self._build_ffmpeg_expr(regions_x)
            expr_y = self._build_ffmpeg_expr(regions_y)

            # Split View Filter:
            # 1. Split video into [f] (webcam) and [g] (gameplay)
            # 2. [f] crop dynamically around face using expr_x & expr_y, scale to top half
            # 3. [g] crop static center 9:16, scale to bottom half
            # 4. vstack them together
            split_filter = (
                f"split=2[f][g];"
                f"[f]crop={avg_side}:{avg_side}:'{expr_x}':'{expr_y}',scale={target_width}:{target_height//2}[top];"
                f"[g]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={target_width}:{target_height//2}[bot];"
                f"[top][bot]vstack,setsar=1"
            )

            logger.info("Dynamic face tracking enabled! Generated panning filter graph.")
            return split_filter

        except Exception as e:
            logger.error("Dynamic Smart Crop failed: %s", e)
            return center_crop

    def _build_ffmpeg_expr(self, regions: list[dict]) -> str:
        """Recursively compile region mappings into nested FFmpeg if() statements."""
        if not regions:
            return "0"

        # Start with the last region value
        last = regions[-1]
        expr = str(last["val_end"] if last["type"] == "transition" else last["val"])

        for r in reversed(regions[:-1]):
            if r["type"] == "static":
                expr = f"if(lt(t,{r['end']}),{r['val']},{expr})"
            else:
                # Linear transition formula between r['start'] and r['end']
                trans_expr = f"{r['val_start']}+({r['val_end']-r['val_start']})*(t-{r['start']})/{r['end']-r['start']}"
                expr = f"if(lt(t,{r['end']}),{trans_expr},{expr})"

        return expr
