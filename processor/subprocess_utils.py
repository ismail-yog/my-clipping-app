"""
StreamClipper — Subprocess & Hardware Resource Utilities
Production-grade subprocess execution, integer millisecond timestamp handling,
CFR normalization, and strict VRAM memory eviction.
"""

import gc
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger("streamclipper.utils")


class PipelineError(Exception):
    """Base exception for all pipeline failures."""
    pass


class SubprocessExecutionError(PipelineError):
    """Raised when a subprocess (ffmpeg, yt-dlp, streamlink, ffprobe) fails or times out."""

    def __init__(self, cmd: List[str], returncode: Optional[int], stdout: str, stderr: str, message: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        cmd_str = " ".join(str(c) for c in cmd)
        err_msg = message or f"Command '{cmd_str}' failed with exit code {returncode}.\nStderr: {stderr.strip()}"
        super().__init__(err_msg)


class MediaProcessingError(PipelineError):
    """Raised when media decoding, encoding, or slicing encounters a fatal defect."""
    pass


class ResourceLimitError(PipelineError):
    """Raised when hardware boundaries (VRAM/RAM) or process limits are exceeded."""
    pass


def run_command_safely(
    cmd: List[Union[str, Path]],
    timeout: float = 300.0,
    cwd: Optional[Union[str, Path]] = None,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Executes a subprocess safely with explicit timeouts, strict output capture,
    and typed SubprocessExecutionError on non-zero exit codes.
    """
    cmd_str_list = [str(arg) for arg in cmd]
    try:
        res = subprocess.run(
            cmd_str_list,
            cwd=str(cwd) if cwd else None,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if check and res.returncode != 0:
            raise SubprocessExecutionError(
                cmd=cmd_str_list,
                returncode=res.returncode,
                stdout=res.stdout or "",
                stderr=res.stderr or "",
            )
        return res
    except subprocess.TimeoutExpired as e:
        stdout_str = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr_str = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        raise SubprocessExecutionError(
            cmd=cmd_str_list,
            returncode=-1,
            stdout=stdout_str,
            stderr=stderr_str,
            message=f"Process timed out after {timeout} seconds: {' '.join(cmd_str_list)}",
        ) from e
    except Exception as e:
        if isinstance(e, SubprocessExecutionError):
            raise
        raise SubprocessExecutionError(
            cmd=cmd_str_list,
            returncode=-1,
            stdout="",
            stderr=str(e),
            message=f"Failed to execute command {' '.join(cmd_str_list)}: {e}",
        ) from e


def safe_unlink(path: Optional[Union[str, Path]]) -> bool:
    """Safely remove a file from disk without throwing unhandled exceptions."""
    if not path:
        return False
    try:
        p = Path(path)
        if p.is_file() or p.is_symlink():
            p.unlink(missing_ok=True)
            return True
        elif p.is_dir():
            for child in p.glob("*"):
                safe_unlink(child)
            p.rmdir()
            return True
    except Exception as exc:
        logger.warning("Failed to unlink path '%s': %s", path, exc)
    return False


def ms_to_timestamp(ms: int) -> str:
    """Converts integer milliseconds to HH:MM:SS.mmm format for FFmpeg/ASS."""
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    rem_ms = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{rem_ms:03d}"


def ms_to_ass_timestamp(ms: int) -> str:
    """Converts integer milliseconds to H:MM:SS.cc format for ASS subtitles."""
    if ms < 0:
        ms = 0
    total_seconds = ms // 1000
    centiseconds = (ms % 1000) // 10
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def seconds_to_ms(seconds: Union[int, float]) -> int:
    """Converts seconds (float/int) into exact integer milliseconds."""
    return int(round(float(seconds) * 1000))


def free_vram():
    """
    Enforces device memory release and garbage collection to respect 16GB VRAM boundaries.
    """
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass
