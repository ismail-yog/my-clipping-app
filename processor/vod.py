"""
StreamClipper — VOD Processor (Optimized)
Downloads a video, finds viral moments via audio energy + transcript,
and extracts clips with captions. Optimized for speed.

Key optimizations over the original:
1. Downloads 720p instead of best quality (2-3x faster download, same output quality for Shorts)
2. Downloads audio-only first for analysis (tiny vs full video)
3. Skips the heavy HuggingFace emotion model — uses audio energy + word density scoring
4. Skips PySceneDetect (opens video 2x per clip — very slow)
5. Merges hook overlay into the main FFmpeg clip pass (1 pass instead of 2)
6. Runs clip extraction in parallel threads
7. Uses faster Whisper settings (VAD filter, beam_size=1)
8. Skips re-downloading video if already have it
"""

import time
import uuid
import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from database import Database
from task_queue import TaskQueue

logger = logging.getLogger("streamclipper.vod")

# Global progress tracker for WebSocket/API polling
VOD_PROGRESS: dict[str, dict] = {}

# Global registry of active processors for cancellation: job_id -> VODProcessor instance
ACTIVE_PROCESSORS: dict[str, 'VODProcessor'] = {}
ACTIVE_PROCESSORS_LOCK = threading.Lock()


def _get_video_duration(path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


class VODProcessor:
    """Fast VOD processor — download, analyze, clip."""

    def __init__(self, db: Database, task_queue: Optional[TaskQueue] = None):
        self.db = db
        self.task_queue = task_queue
        self._whisper_model = None
        self.cancelled = False
        self.active_processes = set()  # Set of running subprocess.Popen instances
        self._lock = threading.Lock()

    def cancel(self):
        """Cancel the active processing task."""
        with self._lock:
            self.cancelled = True
            for proc in list(self.active_processes):
                try:
                    logger.info("Killing active subprocess for cancelled job: PID %d", proc.pid)
                    proc.kill()
                except Exception as e:
                    logger.error("Failed to kill subprocess: %s", e)

    @classmethod
    def cancel_job(cls, job_id: str) -> bool:
        """Cancel job by ID."""
        with ACTIVE_PROCESSORS_LOCK:
            processor = ACTIVE_PROCESSORS.get(job_id)
            if processor:
                processor.cancel()
                return True
        return False

    def run_subprocess(self, cmd: list[str], timeout: Optional[int] = None, capture_output: bool = True, text: bool = True) -> subprocess.CompletedProcess:
        """Run subprocess supporting cancellation."""
        if self.cancelled:
            raise RuntimeError("Job cancelled")

        kwargs = {}
        if capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE
        if text:
            kwargs["text"] = True

        with self._lock:
            if self.cancelled:
                raise RuntimeError("Job cancelled")
            proc = subprocess.Popen(cmd, **kwargs)
            self.active_processes.add(proc)

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            ret = proc.returncode
            if self.cancelled:
                raise RuntimeError("Job cancelled")
            return subprocess.CompletedProcess(cmd, ret, stdout, stderr)
        except subprocess.TimeoutExpired as e:
            try:
                proc.kill()
            except Exception:
                pass
            stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout, stdout, stderr)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise
        finally:
            with self._lock:
                self.active_processes.discard(proc)

    def _load_whisper(self):
        """Lazy-load Whisper (tiny/base for speed)."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                model_name = getattr(config, "WHISPER_MODEL", "base")
                device = getattr(config, "WHISPER_DEVICE", "cpu")
                compute = getattr(config, "WHISPER_COMPUTE_TYPE", "int8")
                logger.info("Loading Whisper '%s' on %s/%s...", model_name, device, compute)
                self._whisper_model = WhisperModel(model_name, device=device, compute_type=compute)
            except ImportError:
                logger.warning("faster-whisper not found, trying openai-whisper")
                import whisper
                self._whisper_model = whisper.load_model("base")
        return self._whisper_model

    def process_url(self, url: str, job_id: str = "", layout_type: str = "gamer") -> bool:
        """Main pipeline — download, analyze, extract clips."""
        if job_id:
            with ACTIVE_PROCESSORS_LOCK:
                ACTIVE_PROCESSORS[job_id] = self

        vid = str(uuid.uuid4())[:8]
        temp_dir = config.TEMP_MEDIA_DIR / f"vod_{vid}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        video_path = temp_dir / "video.mp4"
        audio_path = temp_dir / "audio.wav"

        def progress(pct: int, msg: str):
            if job_id:
                VOD_PROGRESS[job_id] = {"url": url, "progress": pct, "status": msg}
            logger.info("[%d%%] %s", pct, msg)

        try:
            # ── 1. DOWNLOAD (Optimized resolution) ──────────────────────────────
            progress(5, f"Downloading video ({config.vod_settings.download_resolution}p)...")

            dl_cmd = [
                "yt-dlp",
                "-f", f"bestvideo[height<={config.vod_settings.download_resolution}][ext=mp4]+bestaudio[ext=m4a]/best[height<={config.vod_settings.download_resolution}][ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--no-playlist",
                "--no-warnings",
                "--no-check-certificate",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--progress",
                "-o", str(video_path),
                url,
            ]
            r = self.run_subprocess(dl_cmd, timeout=300)
            if r.returncode != 0 or not video_path.exists():
                err_msg = r.stderr[-500:] if r.stderr else "unknown error"
                if "400: Bad Request" in err_msg or "403: Forbidden" in err_msg:
                    logger.error("YouTube blocked the request or URL is invalid: %s", err_msg)
                    progress(0, "YouTube error: Use direct video link instead of channel link")
                else:
                    logger.error("yt-dlp failed: %s", err_msg)
                    progress(0, "Download failed: yt-dlp error")
                return False

            duration = _get_video_duration(video_path)
            logger.info("Downloaded: %.0fs video", duration)

            # ── 2. EXTRACT AUDIO (mono 16kHz — Whisper input format) ────────────
            progress(20, "Extracting audio...")

            audio_cmd = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(audio_path),
            ]
            self.run_subprocess(audio_cmd, timeout=120)
            if not audio_path.exists():
                logger.error("Audio extraction failed")
                return False

            # ── 3. TRANSCRIBE (fast Whisper settings) ───────────────────────────
            progress(35, "Transcribing audio...")

            segments = self._transcribe_fast(audio_path, progress_cb=progress)
            if not segments:
                logger.warning("No transcript segments — using fallback energy-only scoring")
                # Fallback: create evenly-spaced clips
                segments = self._create_fallback_segments(duration)

            # ── 4. SCORE WINDOWS (audio energy + word density — NO heavy model) ─
            progress(55, "Finding viral moments...")

            windows = self._score_windows(segments, audio_path, duration)
            if not windows:
                progress(0, "No moments found")
                return False

            # Take top clips from config
            top = windows[:config.vod_settings.max_clips]
            logger.info("Found %d viral windows, extracting top %d", len(windows), len(top))

            # ── 5. EXTRACT CLIPS (parallel FFmpeg for speed) ────────────────────
            progress(65, f"Rendering {len(top)} clips...")

            clips_made = self._extract_clips_parallel(
                video_path, top, vid, progress, 65, 95, layout_type=layout_type
            )

            # ── 6. DONE ────────────────────────────────────────────────────────
            progress(100, f"Done! {clips_made} clips generated")
            time.sleep(2)  # Let UI see 100%
            return clips_made > 0

        except Exception as e:
            logger.error("VOD processing failed: %s", e, exc_info=True)
            progress(0, f"Error: {e}")
            return False
        finally:
            if job_id:
                with ACTIVE_PROCESSORS_LOCK:
                    ACTIVE_PROCESSORS.pop(job_id, None)
            # Cleanup temp files (keep clips/ intact)
            self._cleanup(temp_dir)
            if job_id:
                # Keep progress for 30s so UI can read it, then remove
                threading.Timer(30, lambda: VOD_PROGRESS.pop(job_id, None)).start()

    # ── Transcription ───────────────────────────────────────────────────────

    def _transcribe_fast(self, audio_path: Path, progress_cb=None) -> list[dict]:
        """Transcribe with fast settings. Returns list of {start, end, text, words}."""
        model = self._load_whisper()
        try:
            segs, info = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language="en",
                vad_filter=True,          # Skip silence — huge speedup
                beam_size=3,              # Beam search (higher accuracy)
                temperature=0.0,          # Disable temperature sweep fallback loops (huge speedup!)
                condition_on_previous_text=True,  # Continuity context for higher accuracy
            )
            result = []
            total_duration = info.duration if info and info.duration else 0.0
            last_progress_time = time.time()
            for seg in segs:
                if self.cancelled:
                    logger.info("Transcription cancelled")
                    break
                words = []
                if seg.words:
                    words = [{"word": w.word.strip(), "start": w.start, "end": w.end, "prob": w.probability}
                             for w in seg.words]
                result.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": words,
                })
                
                # Periodically update progress
                now = time.time()
                if progress_cb and total_duration > 0 and now - last_progress_time > 2.0:
                    pct = int(35 + (seg.end / total_duration) * 20)
                    pct = min(54, max(35, pct))
                    progress_cb(pct, f"Transcribing audio ({pct - 35}% complete)...")
                    last_progress_time = now

            logger.info("Transcribed %d segments", len(result))
            return result
        except Exception as e:
            logger.error("Transcription failed: %s", e)
            return []

    def _create_fallback_segments(self, duration: float) -> list[dict]:
        """Create evenly-spaced segments when transcription fails."""
        segs = []
        for t in range(0, int(duration), 30):
            segs.append({"start": t, "end": min(t + 30, duration), "text": "", "words": []})
        return segs

    # ── Scoring (fast — no heavy ML models) ─────────────────────────────────

    def _score_windows(self, segments: list[dict], audio_path: Path, total_duration: float) -> list[dict]:
        """
        Score 30-second windows by fusing multi-modal signals:
        1. Audio spikes (volume levels via librosa) - 40% weight
        2. Word density (speech speed/excitement) - 30% weight
        3. Word confidence variance (low confidence/fast speech) - 30% weight
        4. Viral / Hype words bonus (e.g. insane, clutch, crazy)
        5. Shouting/Exclamation bonus (caps-lock and !)
        """
        # Extract audio spikes for virality scoring
        audio_spikes = []
        try:
            from detector.audio import AudioDetector
            detector = AudioDetector()
            audio_spikes = detector.analyze(audio_path, reference_time=0.0)
            logger.info("Found %d audio spikes in VOD for virality optimization", len(audio_spikes))
        except Exception as e:
            logger.error("Failed to analyze VOD audio spikes: %s", e)

        # Group segments into 30s windows
        windows = []
        current: list[dict] = []
        window_start = 0.0

        for seg in segments:
            if not current:
                window_start = seg["start"]
            current.append(seg)
            if seg["end"] - window_start >= 30.0:
                windows.append(current)
                current = []
        if current:
            windows.append(current)

        # Score each window
        scored = []
        hype_words = ["insane", "crazy", "wtf", "omg", "lol", "lmao", "no way", "unbelievable", "huge", "shocking", "screaming", "died", "ruined", "secret", "never", "finally", "broke", "scared", "impossible", "win", "clutch", "epic", "perfect", "destroy", "rage", "crying", "hacker", "aimbot", "glitch", "broken"]

        for w in windows:
            if not w:
                continue

            start = w[0]["start"]
            end = w[-1]["end"]
            dur = max(end - start, 1.0)
            text = " ".join(s["text"] for s in w)
            word_count = len(text.split())

            # All word probabilities in this window
            all_probs = [wp["prob"] for s in w for wp in s.get("words", []) if "prob" in wp]

            # Metric 1: Words per second (talking speed = excitement)
            wps = word_count / dur
            wps_score = min(1.0, wps / 4.0)  # 4 words/sec = max

            # Metric 2: Low average confidence = fast/unclear speech = hype
            if all_probs:
                avg_prob = sum(all_probs) / len(all_probs)
                conf_score = max(0, 1.0 - avg_prob)
            else:
                conf_score = 0.3  # Neutral

            # Metric 3: Audio spikes in this window
            window_spikes = [e for e in audio_spikes if start <= e.offset_seconds <= end]
            peak_audio_score = max((e.score for e in window_spikes), default=0.0)

            # Metric 4: Viral / Hype words bonus
            text_lower = text.lower()
            hype_match_count = sum(1 for hw in hype_words if hw in text_lower)
            hype_bonus = min(0.15, hype_match_count * 0.03)

            # Metric 5: Shouting / Exclamation bonus
            shout_bonus = 0.0
            if "!" in text:
                shout_bonus += 0.05
            upper_words = sum(1 for word in text.split() if word.isupper() and len(word) > 2)
            if upper_words > 0:
                shout_bonus += min(0.1, upper_words * 0.02)

            # Avoid very start/end of video (usually intros/outros)
            position = (start + end) / 2 / max(total_duration, 1.0)
            pos_penalty = 1.0
            if position < 0.1 or position > 0.9:
                pos_penalty = 0.6  # Penalize first/last 10%

            # Combined score (weighted average of audio, words/sec, and confidence variance)
            if audio_spikes:
                score = (peak_audio_score * 0.4 + wps_score * 0.3 + conf_score * 0.3)
            else:
                score = (wps_score * 0.5 + conf_score * 0.5)

            # Apply bonuses and penalty
            score = (score + hype_bonus + shout_bonus) * pos_penalty
            score = round(min(1.0, max(0.0, score)), 3)

            # Determine dominant emotion heuristic
            if wps > 3.5 and conf_score > 0.4:
                emotion = "surprise"
            elif wps > 2.5:
                emotion = "joy"
            elif word_count < 10:
                emotion = "neutral"
            else:
                emotion = "joy"

            scored.append({
                "start": start,
                "end": end,
                "score": score,
                "emotion": emotion,
                "text": text,
                "segments": w,
                "words_per_sec": round(wps, 2),
                "word_count": word_count,
            })

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        # Remove overlapping windows (keep highest scored) and filter out low-virality clips
        filtered = []
        used_ranges: list[tuple[float, float]] = []
        min_virality_score = 0.45  # Exclude very low virality clips

        for w in scored:
            overlaps = any(
                w["start"] < ur[1] and w["end"] > ur[0]
                for ur in used_ranges
            )
            if overlaps:
                continue

            # Always allow the absolute highest-scoring moment as fallback, but filter others below threshold
            if w["score"] < min_virality_score and len(filtered) >= 1:
                logger.info("Skipping window at %.1f-%.1f due to low viral score (%.2f < %.2f)", w["start"], w["end"], w["score"], min_virality_score)
                continue

            filtered.append(w)
            used_ranges.append((w["start"], w["end"]))

        return filtered

    # ── Clip Extraction (parallel) ──────────────────────────────────────────

    def _extract_clips_parallel(
        self,
        video_path: Path,
        windows: list[dict],
        vid: str,
        progress_fn,
        pct_start: int,
        pct_end: int,
        layout_type: str = "gamer",
    ) -> int:
        """Extract clips in parallel using ThreadPoolExecutor."""
        total = len(windows)
        completed = 0
        lock = threading.Lock()

        def extract_one(i: int, window: dict) -> bool:
            if self.cancelled:
                return False
            nonlocal completed
            clip_id = f"vod_{vid}_{i}"
            start = window["start"]
            dur = min(window["end"] - window["start"] + 5.0, 60.0)

            try:
                output = config.CLIPS_DIR / f"{clip_id}.mp4"

                # Build subtitle file for captions if enabled
                sub_path = None
                if config.vod_settings.burn_captions:
                    sub_path = self._build_simple_subs(window, clip_id)

                if self.cancelled:
                    return False

                # Single FFmpeg pass: cut + crop to 9:16 + burn subs
                cmd = self._build_fast_clip_cmd(video_path, output, start, dur, sub_path, layout_type=layout_type)
                r = self.run_subprocess(cmd, timeout=120)

                if self.cancelled:
                    return False

                if r.returncode != 0 or not output.exists():
                    logger.error("Clip %s failed: %s", clip_id, r.stderr[-300:] if r.stderr else "")
                    return False

                # Generate a simple title from transcript
                title = self._generate_title(window["text"], window["emotion"])

                # Apply Hook Overlay, Watermark, and Outro Fades
                try:
                    from processor.hook import HookOverlayRenderer
                    hook_renderer = HookOverlayRenderer()
                    hooked_output = hook_renderer.apply(
                        clip_path=output,
                        hook_text=title,
                        watermark_text="@StreamClipper",
                    )
                    if hooked_output:
                        logger.info("Hook overlay, watermark, and outro applied to %s", clip_id)
                except Exception as e:
                    logger.error("Failed to apply hook overlay to %s: %s", clip_id, e)

                # Determine auto-approve
                auto_approve = window["score"] >= 0.8

                # Save to database
                self.db.save_clip(
                    clip_id=clip_id,
                    streamer_name="VOD_Clipper",
                    platform="custom",
                    clip_path=str(output),
                    duration=dur,
                    moment_score=window["score"],
                    emotion=window["emotion"],
                    transcript=window["text"][:500],
                    has_captions=sub_path is not None,
                    auto_approve=auto_approve,
                )

                # Submit to queue if auto-approved
                if auto_approve and self.task_queue:
                    self.task_queue.submit(
                        job_type="upload",
                        clip_id=clip_id,
                        payload={
                            "clip_path": str(output),
                            "title": title,
                            "description": window["text"][:200],
                            "tags": ["shorts", "viral", "clips", window["emotion"]],
                            "thumbnail_path": "",
                        },
                        priority=3,
                    )
                    logger.info("🔥 High viral score (%.2f) — VOD clip %s queued for auto-upload", window["score"], clip_id)

                # Update SEO fields directly (skip Ollama for speed)
                self.db.update_clip_seo(
                    clip_id=clip_id,
                    title=title,
                    description=window["text"][:200],
                    tags=["shorts", "viral", "clips", window["emotion"]],
                    hook_text=title,
                    seo_method="fast-heuristic",
                )

                with lock:
                    nonlocal completed
                    completed += 1
                    pct = pct_start + int((completed / total) * (pct_end - pct_start))
                    progress_fn(pct, f"Rendered clip {completed}/{total}")

                logger.info("Clip %s created (score: %.2f)", clip_id, window["score"])
                return True

            except Exception as e:
                logger.error("Clip %s error: %s", clip_id, e)
                return False

        # Run parallel clips (disk I/O and CPU bound)
        success_count = 0
        with ThreadPoolExecutor(max_workers=config.vod_settings.parallel_renders) as executor:
            futures = {executor.submit(extract_one, i, w): i for i, w in enumerate(windows)}
            for future in as_completed(futures):
                if self.cancelled:
                    logger.info("Parallel clip rendering cancelled")
                    break
                if future.result():
                    success_count += 1

        return success_count

    def _build_fast_clip_cmd(
        self, source: Path, output: Path,
        start: float, duration: float,
        sub_path: Optional[Path],
        layout_type: str = "gamer",
    ) -> list[str]:
        """
        Single FFmpeg command that does everything in one pass:
        - Seeks to timestamp
        - Crops/Split-View via SmartCrop
        - Burns subtitles
        - Normalizes audio, loops background music, auto-ducks, and injects SFX
        - Fast encoding preset
        """
        from processor.smart_crop import SmartCrop
        from processor.audio_engine import AudioEngine

        sc = SmartCrop()
        audio_engine = AudioEngine()

        filter_complex = sc.get_crop_filter(source, start, 1080, 1920, layout_type=layout_type, duration=duration)
        video_filter = "[0:v]" + filter_complex + "[v_out]"

        if sub_path and sub_path.exists():
            # Windows ASS filter needs specific escaping
            sub_escaped = str(sub_path.absolute()).replace("\\", "/").replace(":", "\\:")
            video_filter += f";[v_out]ass='{sub_escaped}'[v_captioned]"
            v_output_label = "[v_captioned]"
        else:
            v_output_label = "[v_out]"

        # Build audio filter graph and get extra input files (BGM, SFX)
        audio_filter, extra_inputs = audio_engine.build_audio_filter(
            duration=duration,
            has_sfx=True,
            sfx_name="vine_boom",
            sfx_offset_sec=duration * 0.7,
        )

        # Combine video and audio filter complexes
        full_filter_complex = video_filter + ";" + audio_filter

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(max(0, start)),
            "-i", str(source),
        ]

        # Append extra inputs (BGM/SFX)
        cmd.extend(extra_inputs)

        cmd.extend([
            "-t", str(duration),
            "-filter_complex", full_filter_complex,
            "-map", v_output_label,
            "-map", "[a_out]",
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-r", "30",
            "-movflags", "+faststart",
            str(output),
        ])
        return cmd

    def _build_simple_subs(self, window: dict, clip_id: str) -> Optional[Path]:
        """Generate ASS subtitle file with word-level highlights and emoji injection (upgraded)."""
        segments = window.get("segments", [])
        if not segments:
            return None

        # Check if any segment has words
        has_words = any(s.get("words") for s in segments)
        if not has_words:
            return None

        sub_path = config.CLIPS_DIR / f"{clip_id}.ass"
        base_time = window["start"]  # Offset to clip-relative time

        # ASS header with thicker black outline (Outline=6, Shadow=2) and bold Arial Black font
        font_name = "Arial Black"
        header = f"""[Script Info]
Title: {clip_id}
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},90,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = [header]

        # Emojis dictionary
        emoji_map = {
            "insane": "🤯", "crazy": "🤯", "wtf": "🤬", "oh my god": "😱", "omg": "😱",
            "dead": "💀", "died": "💀", "kill": "💀", "fire": "🔥", "lit": "🔥",
            "win": "🏆", "clutch": "👑", "epic": "⚡", "love": "❤️", "hype": "🔥",
            "laugh": "😂", "funny": "😂", "lol": "😂", "screaming": "😱", "shot": "💥",
            "aim": "🎯", "headshot": "🎯", "ez": "😎", "easy": "😎", "noob": "🤡",
            "hacker": "🤖", "money": "💰", "cash": "💰", "run": "🏃", "fast": "⚡",
            "stream": "💻", "live": "🔴", "speed": "⚡", "rage": "😡", "angry": "😡",
        }

        def clean_word(w: str) -> str:
            return "".join(c for c in w.lower() if c.isalnum())

        def get_word_with_emoji(word: str) -> str:
            cw = clean_word(word)
            emoji = emoji_map.get(cw)
            return f"{word} {emoji}" if emoji else word

        # Flatten all words from all segments in this window
        all_words = []
        for seg in segments:
            words = seg.get("words", [])
            if words:
                all_words.extend(words)

        # Chunk words into groups of max 3 words
        chunks = []
        current_chunk = []
        for w in all_words:
            if current_chunk and (w["start"] - current_chunk[-1]["end"] > 1.0 or len(current_chunk) >= 3):
                chunks.append(current_chunk)
                current_chunk = []
            current_chunk.append(w)
        if current_chunk:
            chunks.append(current_chunk)

        if chunks:
            # Word-by-word highlight style for chunks
            for chunk in chunks:
                for i, active_word in enumerate(chunk):
                    # Relative time offset
                    start_ts = self._to_ass_time(active_word["start"] - base_time)
                    end_ts = self._to_ass_time(active_word["end"] - base_time)

                    # Build line with active word capitalized and highlighted yellow
                    text_parts = []
                    for j, w in enumerate(chunk):
                        word_text = get_word_with_emoji(w["word"])
                        if j == i:
                            text_parts.append(f"{{\\c&H00FFFF&}}{word_text.upper()}{{\\c&HFFFFFF&}}")
                        else:
                            text_parts.append(word_text)

                    full_text = " ".join(text_parts)
                    lines.append(
                        f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{full_text}"
                    )
        else:
            # Fallback to segment levels if no word timings
            for seg in segments:
                s = self._to_ass_time(seg["start"] - base_time)
                e = self._to_ass_time(seg["end"] - base_time)
                lines.append(
                    f"Dialogue: 0,{s},{e},Default,,0,0,0,,{seg['text']}"
                )

        try:
            sub_path.write_text("\n".join(lines), encoding="utf-8")
            return sub_path
        except Exception as e:
            logger.error("Failed to write ASS subtitles: %s", e)
            return None

    @staticmethod
    def _to_ass_time(seconds: float) -> str:
        """Convert seconds to ASS time (H:MM:SS.CC)."""
        seconds = max(0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _generate_title(self, transcript: str, emotion: str) -> str:
        """Generate a quick title from transcript (no LLM needed)."""
        words = transcript.split()
        if len(words) <= 5:
            return transcript.strip().upper() or "VIRAL MOMENT"

        # Take first meaningful sentence fragment
        fragment = " ".join(words[:8]).strip()
        if len(fragment) > 60:
            fragment = fragment[:57] + "..."

        prefixes = {
            "surprise": "WAIT FOR THIS - ",
            "joy": "BEST MOMENT - ",
            "anger": "THIS IS INSANE - ",
            "neutral": "",
        }
        prefix = prefixes.get(emotion, "")
        return (prefix + fragment).upper()

    def _cleanup(self, temp_dir: Path):
        """Remove temp files."""
        try:
            for f in temp_dir.glob("*"):
                f.unlink()
            temp_dir.rmdir()
        except Exception as e:
            logger.debug("Cleanup error: %s", e)
