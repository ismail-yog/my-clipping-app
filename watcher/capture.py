"""
StreamClipper — Stream Capture
Captures live streams into a rolling buffer of video segments using
streamlink (or yt-dlp) piped into FFmpeg.
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
    Captures a live stream into a rolling buffer of short video segments.

    Uses streamlink to grab the HLS stream and FFmpeg to write segment files.
    Older segments are automatically cleaned up to stay within the buffer window.
    """

    def __init__(
        self,
        streamer: config.StreamerConfig,
        output_dir: Optional[Path] = None,
        settings: Optional[config.CaptureSettings] = None,
    ):
        self.streamer = streamer
        self.settings = settings or config.capture_settings
        self.output_dir = output_dir or (
            config.CLIPS_DIR / "buffer" / streamer.channel
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._streamlink_proc: Optional[subprocess.Popen] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False
        self._started_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def is_capturing(self) -> bool:
        return self._running

    @property
    def segment_pattern(self) -> str:
        """Glob pattern for segment files."""
        return str(self.output_dir / "seg_*.ts")

    @property
    def audio_dir(self) -> Path:
        """Directory for extracted audio chunks."""
        d = self.output_dir / "audio"
        d.mkdir(exist_ok=True)
        return d

    def start(self):
        """Begin capturing the stream."""
        with self._lock:
            if self._running:
                logger.warning("Capture already running for %s", self.streamer.name)
                return

            self._running = True
            self._started_at = time.time()

        logger.info(
            "Starting capture for %s (%s) — quality=%s, segment=%ds",
            self.streamer.name,
            self.streamer.url,
            self.settings.stream_quality,
            self.settings.segment_duration,
        )

        # Start capture in background thread
        capture_thread = threading.Thread(target=self._run_capture, daemon=True)
        capture_thread.start()

        # Start cleanup in background thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop(self):
        """Stop capturing the stream."""
        with self._lock:
            self._running = False

        # Terminate processes
        for proc_name, proc in [
            ("streamlink", self._streamlink_proc),
            ("ffmpeg", self._ffmpeg_proc),
        ]:
            if proc and proc.poll() is None:
                logger.debug("Terminating %s process", proc_name)
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        logger.info("Capture stopped for %s", self.streamer.name)

    def get_buffer_files(self, last_n_seconds: Optional[int] = None) -> list[Path]:
        """
        Get sorted list of buffer segment files.
        If last_n_seconds is specified, only return segments from that window.
        """
        files = sorted(Path(f) for f in glob.glob(self.segment_pattern))

        if last_n_seconds and files:
            cutoff = time.time() - last_n_seconds
            files = [f for f in files if f.stat().st_mtime >= cutoff]

        return files

    def get_concat_file(self, start_time: float, duration: int) -> Optional[Path]:
        """
        Create a concatenated video file from buffer segments covering
        the time window [start_time, start_time + duration].

        Returns the path to the concatenated file, or None on failure.
        """
        segments = self.get_buffer_files()
        if not segments:
            logger.warning("No buffer segments available")
            return None

        # Filter segments by modification time
        selected = []
        for seg in segments:
            try:
                mtime = seg.stat().st_mtime
                if mtime >= start_time and mtime <= start_time + duration + 30:
                    selected.append(seg)
            except OSError:
                continue

        if not selected:
            # Fall back to most recent segments
            n_segments = max(1, duration // self.settings.segment_duration + 2)
            selected = segments[-n_segments:]
            logger.info(
                "No segments matched time window, using last %d segments",
                len(selected),
            )

        # Create concat list file
        concat_list = self.output_dir / "concat_list.txt"
        with open(concat_list, "w") as f:
            for seg in selected:
                f.write(f"file '{seg.resolve()}'\n")

        # Concatenate with FFmpeg
        output_file = self.output_dir / f"concat_{int(time.time())}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_file),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and output_file.exists():
                logger.info("Concatenated %d segments → %s", len(selected), output_file)
                return output_file
            else:
                logger.error("FFmpeg concat failed: %s", result.stderr[-500:])
                return None
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg concat timed out")
            return None

    def extract_audio(self, video_path: Path) -> Optional[Path]:
        """Extract audio from a video file to WAV format."""
        audio_path = self.audio_dir / f"{video_path.stem}.wav"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and audio_path.exists():
                return audio_path
            else:
                logger.error("Audio extraction failed: %s", result.stderr[-300:])
                return None
        except subprocess.TimeoutExpired:
            logger.error("Audio extraction timed out")
            return None

    def _run_capture(self):
        """
        Main capture pipeline: streamlink → pipe → FFmpeg → segments.
        Runs in a background thread.
        """
        while self._running:
            try:
                self._start_pipeline()
            except Exception as e:
                logger.error("Capture pipeline error for %s: %s", self.streamer.name, e)

            if self._running:
                logger.info("Restarting capture in 5s for %s...", self.streamer.name)
                time.sleep(5)

    def _start_pipeline(self):
        """Start the streamlink → FFmpeg pipeline."""
        segment_path = str(self.output_dir / "seg_%06d.ts")

        # Streamlink command: pipe stream to stdout
        streamlink_cmd = [
            "streamlink",
            self.streamer.url,
            self.settings.stream_quality,
            "--stdout",
            "--twitch-disable-ads",
            "--retry-streams", "5",
            "--retry-max", "3",
        ]

        # FFmpeg command: read from stdin, write segments
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", "pipe:0",
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.settings.segment_duration),
            "-reset_timestamps", "1",
            "-strftime", "0",
            segment_path,
        ]

        logger.debug("Starting streamlink: %s", " ".join(streamlink_cmd))
        logger.debug("Starting FFmpeg: %s", " ".join(ffmpeg_cmd))

        # Start streamlink
        self._streamlink_proc = subprocess.Popen(
            streamlink_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Start FFmpeg, reading from streamlink's stdout
        self._ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=self._streamlink_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Allow streamlink to receive SIGPIPE if FFmpeg exits
        if self._streamlink_proc.stdout:
            self._streamlink_proc.stdout.close()

        # Wait for FFmpeg to finish (blocks until stream ends or error)
        self._ffmpeg_proc.wait()

        if self._ffmpeg_proc.returncode != 0 and self._running:
            stderr = ""
            if self._ffmpeg_proc.stderr:
                stderr = self._ffmpeg_proc.stderr.read().decode("utf-8", errors="replace")[-500:]
            logger.warning("FFmpeg exited with code %d: %s", self._ffmpeg_proc.returncode, stderr)

    def _cleanup_loop(self):
        """Periodically remove old segment files outside the buffer window."""
        while self._running:
            try:
                self._cleanup_old_segments()
            except Exception as e:
                logger.debug("Cleanup error: %s", e)

            time.sleep(self.settings.segment_duration)

    def _cleanup_old_segments(self):
        """Remove segments older than the buffer window."""
        cutoff = time.time() - self.settings.buffer_window
        removed = 0

        for filepath in glob.glob(self.segment_pattern):
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    removed += 1
            except OSError:
                pass

        if removed > 0:
            logger.debug("Cleaned up %d old segments for %s", removed, self.streamer.name)
