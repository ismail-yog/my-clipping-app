"""
StreamClipper — Stream Capture
Records live streams in 1080p using a rolling buffer.
"""

import os
import time
import glob
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("streamclipper.capture")


class StreamCapture:
    """
    Captures live stream footage in short segments to a rolling buffer.
    Pipes streamlink output into FFmpeg to write segment files, cleans up older files.
    """

    def __init__(self, streamer: config.StreamerConfig):
        self.streamer = streamer
        self.settings = config.capture_settings
        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._buffer_dir: Optional[Path] = None
        self._lock = threading.Lock()

    @property
    def is_capturing(self) -> bool:
        """Indicate if the capture loop is actively running."""
        with self._lock:
            return self._running

    def start(self):
        """Begin recording the live stream into the rolling buffer."""
        with self._lock:
            if self._running:
                logger.warning("[%s] Capture is already running.", self.streamer.name)
                return
            self._running = True

        # Create unique buffer directory for this capture session
        self._buffer_dir = config.RAW_DIR / f"{self.streamer.name}_{int(time.time())}"
        self._buffer_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "[%s] Starting capture on %s (quality=%s, segment=%ds, window=%ds)",
            self.streamer.name,
            self.streamer.url,
            self.settings.stream_quality,
            self.settings.segment_duration,
            self.settings.buffer_window,
        )

        # Spawn background capture worker thread
        self._capture_thread = threading.Thread(
            target=self._capture_worker,
            name="_capture_loop",
            daemon=True
        )
        self._capture_thread.start()

        # Spawn background cleanup loop thread
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self._cleanup_thread.start()

    def stop(self):
        """Stop recording and log buffer statistics."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        # Wait for threads to finish
        if self._capture_thread:
            self._capture_thread.join(timeout=5)
            self._capture_thread = None
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None

        # Calculate buffer stats (total segments, total size)
        total_segments = 0
        total_size = 0
        if self._buffer_dir and self._buffer_dir.exists():
            for filepath in self._buffer_dir.glob("seg_*.ts"):
                total_segments += 1
                try:
                    total_size += filepath.stat().st_size
                except Exception:
                    pass

        size_mb = total_size / (1024 * 1024)
        logger.info(
            "[%s] Capture stopped. Buffer stats: %d segments, %.2f MB",
            self.streamer.name,
            total_segments,
            size_mb,
        )

    def _capture_worker(self):
        """Worker loop that retrieves stream URLs and segments footage."""
        while True:
            with self._lock:
                if not self._running:
                    break

            # 1. Get stream URL via streamlink (retries 3 times with 5s delay)
            stream_url = None
            for attempt in range(3):
                with self._lock:
                    if not self._running:
                        break
                stream_url = self._get_stream_url()
                if stream_url:
                    break
                logger.warning(
                    "[%s] Failed to get stream URL. Retrying in 5s... (Attempt %d/3)",
                    self.streamer.name,
                    attempt + 1,
                )
                time.sleep(5)

            if not stream_url:
                logger.error(
                    "[%s] Failed to resolve stream URL after 3 attempts. Retrying in 10s...",
                    self.streamer.name,
                )
                time.sleep(10)
                continue

            # 2. Run FFmpeg to read stream and write segment files
            segment_pattern = str(self._buffer_dir / "seg_%05d.ts")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", stream_url,
                "-c", "copy",
                "-f", "segment",
                "-segment_time", str(self.settings.segment_duration),
                "-reset_timestamps", "1",
                segment_pattern
            ]

            logger.info("[%s] Segmenting stream into buffer...", self.streamer.name)
            try:
                proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                while True:
                    with self._lock:
                        if not self._running:
                            break
                    # If ffmpeg terminated or crashed, break to restart
                    if proc.poll() is not None:
                        break
                    time.sleep(1)

                # Cleanup processes on loop break or stop
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                else:
                    ret = proc.returncode
                    if ret != 0:
                        stderr = ""
                        if proc.stderr:
                            stderr = proc.stderr.read().decode("utf-8", errors="replace")[-300:]
                        logger.error(
                            "[%s] FFmpeg crashed with exit code %d. Error: %s",
                            self.streamer.name,
                            ret,
                            stderr,
                        )
                        logger.info("[%s] Restarting capture from current time...", self.streamer.name)
            except Exception as e:
                logger.error("[%s] Exception in capture execution: %s", self.streamer.name, e)
                time.sleep(2)

    def get_buffer_files(self, last_n_seconds: int = 30) -> list[Path]:
        """Return a sorted list of segments covering the last N seconds."""
        if not self._buffer_dir or not self._buffer_dir.exists():
            return []

        files = list(self._buffer_dir.glob("seg_*.ts"))
        # Sort chronologically by modification time
        files.sort(key=lambda f: f.stat().st_mtime)

        cutoff = time.time() - last_n_seconds
        return [f for f in files if f.stat().st_mtime >= cutoff]

    def get_concat_file(self, start_time: float, duration: float) -> Optional[Path]:
        """
        Concatenate buffer segments covering the time window [start_time, start_time + duration].
        Returns the path to the concatenated file, or None on failure.
        """
        # Fetch segments up to the time duration requested plus extra window to be safe
        segments = self.get_buffer_files(last_n_seconds=int(time.time() - start_time + 10))
        if not segments:
            logger.warning("[%s] No segments available in buffer for concatenation.", self.streamer.name)
            return None

        # Filter segments that match the exact start time and duration bounds (with 10s padding)
        selected = []
        for seg in segments:
            try:
                mtime = seg.stat().st_mtime
                if mtime >= start_time - 10 and mtime <= start_time + duration + 10:
                    selected.append(seg)
            except OSError:
                continue

        if not selected:
            # Fallback to the most recent segments covering the duration
            n_segments = max(1, int(duration // self.settings.segment_duration) + 2)
            selected = segments[-n_segments:]
            logger.info(
                "[%s] No segments matched time bounds, using last %d segments as fallback",
                self.streamer.name,
                len(selected),
            )

        # Create text file for ffmpeg concat demuxer
        concat_list_path = self._buffer_dir / "concat_list.txt"
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for seg in selected:
                    escaped_path = str(seg.resolve()).replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            output_file = config.TEMP_MEDIA_DIR / f"concat_{self.streamer.name}_{int(time.time())}.mp4"
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_file),
            ]

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and output_file.exists():
                logger.info("[%s] Concatenated %d segments to %s", self.streamer.name, len(selected), output_file.name)
                return output_file
            else:
                logger.error("[%s] FFmpeg concat failed: %s", self.streamer.name, result.stderr)
        except Exception as e:
            logger.error("[%s] Concatenate error: %s", self.streamer.name, e)

        return None

    def extract_audio(self, video_path: Path) -> Optional[Path]:
        """Extract audio to a 16kHz mono WAV file (required for Whisper)."""
        audio_path = video_path.with_suffix(".wav")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path),
        ]
        try:
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and audio_path.exists():
                return audio_path
            else:
                logger.error("[%s] Audio extraction failed: %s", self.streamer.name, result.stderr)
        except Exception as e:
            logger.error("[%s] Exception during audio extraction: %s", self.streamer.name, e)
        return None

    def _get_stream_url(self) -> Optional[str]:
        """Query streamlink to resolve the live stream HLS manifest URL."""
        cmd = ["streamlink", "--get-url", self.streamer.url, self.settings.stream_quality]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                if url.startswith("http"):
                    return url
            logger.debug("[%s] Streamlink get-url stderr: %s", self.streamer.name, result.stderr)
        except Exception as e:
            logger.error("[%s] Exception querying streamlink: %s", self.streamer.name, e)
        return None

    def _cleanup_loop(self):
        """Background thread loop that regularly executes segment cleanup."""
        while True:
            with self._lock:
                if not self._running:
                    break

            try:
                self._cleanup_old_segments()
            except Exception as e:
                logger.debug("[%s] Cleanup loop error: %s", self.streamer.name, e)

            # Sleep in small 1-second chunks to exit promptly on stop
            for _ in range(30):
                with self._lock:
                    if not self._running:
                        break
                time.sleep(1)

    def _cleanup_old_segments(self):
        """Delete segment files older than the configured buffer window."""
        if not self._buffer_dir or not self._buffer_dir.exists():
            return

        cutoff = time.time() - self.settings.buffer_window
        removed_count = 0

        for filepath in self._buffer_dir.glob("seg_*.ts"):
            try:
                if filepath.stat().st_mtime < cutoff:
                    filepath.unlink(missing_ok=True)
                    removed_count += 1
            except Exception:
                pass

        if removed_count > 0:
            logger.debug("[%s] Deleted %d segments outside buffer window.", self.streamer.name, removed_count)
