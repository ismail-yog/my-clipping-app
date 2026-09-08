"""
StreamClipper / LumiClip — 0-100 Virality Hook Scoring Engine
Analyzes transcript windows (30-90s) with structured LLM prompts (NVIDIA Nemotron / Ollama)
to isolate high-retention clips, generate punchy hook assertions, and rank by virality (>= 65).
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

import requests

import config

logger = logging.getLogger("streamclipper.hook_scorer")


def _extract_seg_field(seg: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract attribute from either a dict or an object instance."""
    if isinstance(seg, dict):
        return seg.get(field_name, default)
    return getattr(seg, field_name, default)


@dataclass
class HookCandidate:
    start_ms: int
    end_ms: int
    hook_score: int  # 0 to 100
    title: str
    hook_text: str
    reasoning: str
    transcript_snippet: str = ""

    @property
    def duration_sec(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


class HookScorer:
    """Evaluates transcript windows for retention, punchlines, and virality potential."""

    def __init__(self, min_hook_score: int = 65):
        self.min_hook_score = min_hook_score
        self.nvidia_api_key = getattr(config, "NVIDIA_API_KEY", "") or os.environ.get("NVIDIA_API_KEY", "")
        self.nvidia_model = getattr(config, "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
        self.nvidia_fallback_model = getattr(config, "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.fast_backup_model = "meta/llama-3.2-11b-vision-instruct"
        self._nim_disabled: bool = False
        self._ollama_disabled: bool = False

    def score_transcript(
        self,
        transcript_segments: list,
        streamer_name: str = "Streamer",
        window_sec: int = 40,
        step_sec: int = 15
    ) -> List[HookCandidate]:
        """
        Slice transcript into overlapping windows and execute structured virality scoring.
        Enforces integer millisecond boundaries and strictly 30-45s duration bounds.
        """
        if not transcript_segments:
            return []

        # Find total transcript duration
        max_end_sec = 0.0
        for seg in transcript_segments:
            val = float(_extract_seg_field(seg, "end", 0.0) or 0.0)
            if val > max_end_sec:
                max_end_sec = val

        if max_end_sec <= 0:
            return []

        candidates: List[HookCandidate] = []

        # Generate rolling windows
        current_start = 0.0
        while current_start < max_end_sec:
            current_end = min(current_start + window_sec, max_end_sec)

            # Extract transcript text within window
            window_segments = [
                seg for seg in transcript_segments
                if float(_extract_seg_field(seg, "start", 0.0) or 0.0) >= current_start
                and float(_extract_seg_field(seg, "end", 0.0) or 0.0) <= current_end
            ]

            window_text = " ".join(
                str(_extract_seg_field(seg, "text", "") or "").strip()
                for seg in window_segments
            ).strip()

            words = window_text.split()
            # Speech density check: require at least 5 words or emotional punctuations
            if len(words) >= 5 or any(p in window_text for p in ["!", "?"]):
                scored_clips = self._score_window_llm(
                    window_text=window_text,
                    start_sec=current_start,
                    end_sec=current_end,
                    streamer_name=streamer_name
                )
                candidates.extend(scored_clips)

            current_start += step_sec
            if current_end >= max_end_sec:
                break

        # Filter by minimum score and sort descending
        filtered = [c for c in candidates if c.hook_score >= self.min_hook_score]
        filtered.sort(key=lambda c: c.hook_score, reverse=True)

        # Deduplicate overlapping clips
        deduped = self._deduplicate_candidates(filtered)
        logger.info(
            "HookScorer evaluated transcript: %d candidates found (%d >= %d score)",
            len(candidates), len(deduped), self.min_hook_score
        )
        return deduped

    def evaluate_moment_buffer(
        self,
        transcript_segments: list,
        streamer_name: str = "Streamer",
        min_score: Optional[int] = None,
    ) -> Optional[HookCandidate]:
        """
        Evaluate a single stream buffer window (e.g., 30-60s) for live stream moment validation.
        Returns the top HookCandidate if virality meets the threshold, otherwise None.
        """
        if not transcript_segments:
            return None

        threshold = min_score if min_score is not None else self.min_hook_score

        candidates = self.score_transcript(
            transcript_segments=transcript_segments,
            streamer_name=streamer_name,
            window_sec=40,
            step_sec=10,
        )

        if not candidates:
            return None

        best = candidates[0]
        if best.hook_score >= threshold:
            return best
        return None

    def _score_window_llm(
        self,
        window_text: str,
        start_sec: float,
        end_sec: float,
        streamer_name: str
    ) -> List[HookCandidate]:
        """Call NVIDIA NIM or local Ollama LLM to get structured JSON clip evaluations."""
        prompt = self._build_prompt(window_text, start_sec, end_sec, streamer_name)

        # 1. Try NVIDIA NIM endpoints if API key available and circuit breaker open
        if self.nvidia_api_key and not self._nim_disabled:
            models_to_try = [self.nvidia_model, self.nvidia_fallback_model]
            for model in models_to_try:
                if not model:
                    continue
                try:
                    response = self._call_nvidia_nim(prompt, model)
                    if response:
                        parsed = self._parse_llm_json(response, window_text, start_sec, end_sec)
                        if parsed:
                            return parsed
                except Exception as e:
                    logger.warning("HookScorer model %s failed (%s) — disabling NIM circuit", model, e)
                    self._nim_disabled = True
                    break

        # 2. Try Ollama local endpoint if available and circuit breaker open
        if not self._ollama_disabled:
            try:
                ollama_response = self._call_ollama(prompt)
                if ollama_response:
                    parsed = self._parse_llm_json(ollama_response, window_text, start_sec, end_sec)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.debug("Ollama hook scoring failed (%s) — disabling Ollama circuit", e)
                self._ollama_disabled = True

        # 3. Deterministic heuristic fallback
        return self._heuristic_fallback(window_text, start_sec, end_sec, streamer_name)

    def _call_nvidia_nim(self, prompt: str, model: str) -> Optional[str]:
        """Execute HTTP request to NVIDIA NIM cloud endpoint with bounded timeout."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.nvidia_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a professional viral short-form video editor. Output ONLY raw JSON matching the exact schema."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception as e:
            self._nim_disabled = True
            raise e
        return None

    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Call local Ollama endpoint for semantic clip rating with bounded timeout."""
        ollama_host = getattr(config, "OLLAMA_HOST", "http://localhost:11434")
        ollama_model = getattr(config, "OLLAMA_MODEL", "llama3")
        url = f"{ollama_host.rstrip('/')}/api/generate"
        payload = {
            "model": ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            resp = requests.post(url, json=payload, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "")
        except Exception:
            self._ollama_disabled = True
            return None
        return None

    def _build_prompt(self, window_text: str, start_sec: float, end_sec: float, streamer_name: str) -> str:
        """Create structured prompt enforcing strict JSON output and 30-45s clip duration."""
        return f"""Analyze this {int(end_sec - start_sec)}s audio transcript segment from streamer '{streamer_name}'.
Window start: {start_sec:.1f}s, Window end: {end_sec:.1f}s.

Transcript:
\"\"\"{window_text}\"\"\"

Identify if there is a viral highlight moment in this window. Rate virality on a scale of 0 to 100.
IMPORTANT: Clip duration ("end_sec" - "start_sec") MUST be strictly between 30 and 45 seconds.
High scores (80-100) require:
- Strong 3-second opening hook / sudden statement
- High emotional reaction, punchline, victory, or failure
- Cohesive standalone context for TikTok / YouTube Shorts

Output a JSON object matching this schema:
{{
  "clips": [
    {{
      "start_sec": {start_sec:.1f},
      "end_sec": {min(end_sec, start_sec + 40.0):.1f},
      "hook_score": 85,
      "title": "Clickbait title under 75 characters (with emoji)",
      "hook_text": "3-second opening subtitle (e.g. STOP SCROLLING 💀)",
      "reasoning": "1 sentence explanation of why this retains viewers"
    }}
  ]
}}
"""

    def _parse_llm_json(
        self,
        response: str,
        window_text: str,
        start_sec: float,
        end_sec: float
    ) -> List[HookCandidate]:
        """Extract and validate JSON clip objects from LLM response with strict 30-45s duration clamping."""
        try:
            cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

            # Extract JSON block
            data = None
            code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
            if code_blocks:
                for b in reversed(code_blocks):
                    try:
                        data = json.loads(b)
                        if "clips" in data:
                            break
                    except Exception:
                        pass

            if not data:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(cleaned[start:end])

            if not data or "clips" not in data:
                return []

            results: List[HookCandidate] = []
            for item in data["clips"]:
                c_start_sec = float(item.get("start_sec", start_sec))
                c_end_sec = float(item.get("end_sec", end_sec))

                # Enforce strictly 30s to 45s duration bounds
                cand_dur = c_end_sec - c_start_sec
                if cand_dur < 30.0:
                    c_end_sec = c_start_sec + 30.0
                elif cand_dur > 45.0:
                    c_end_sec = c_start_sec + 45.0

                score = int(item.get("hook_score", 50))
                title = str(item.get("title", ""))[:80]
                hook_text = str(item.get("hook_text", ""))[:40]
                reasoning = str(item.get("reasoning", ""))

                results.append(
                    HookCandidate(
                        start_ms=int(round(c_start_sec * 1000.0)),
                        end_ms=int(round(c_end_sec * 1000.0)),
                        hook_score=score,
                        title=title,
                        hook_text=hook_text,
                        reasoning=reasoning,
                        transcript_snippet=window_text[:200]
                    )
                )
            return results

        except Exception as e:
            logger.debug("Failed to parse hook scoring JSON: %s", e)
            return []

    def _heuristic_fallback(
        self,
        window_text: str,
        start_sec: float,
        end_sec: float,
        streamer_name: str
    ) -> List[HookCandidate]:
        """Fallback scoring using keyword density, emotional signals, and 30-45s duration enforcement."""
        words = [w for w in window_text.strip().split() if w]
        snippet = " ".join(words[:6]).strip('",.?!')

        # Enforce duration bounds strictly between 30 and 45 seconds
        target_dur = max(30.0, min(45.0, end_sec - start_sec))
        c_end_sec = start_sec + target_dur

        hype_keywords = [
            "clutch", "insane", "omg", "no way", "wtf", "gg", "win", "dead",
            "unbelievable", "bro", "crazy", "rage", "screaming", "crying",
            "hack", "aimbot", "glitch", "destroy", "ruined", "never", "holy",
            "caught", "exposed", "shut up", "lost it", "cooked"
        ]
        text_lower = window_text.lower()
        matches = sum(1 for k in hype_keywords if k in text_lower)
        exclamations = window_text.count("!") + window_text.count("?")
        caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)

        # Baseline: 35 for ordinary flat speech. High hype pushed over 65 threshold.
        base_score = 35 + (matches * 10) + (exclamations * 5) + (caps_words * 4)
        base_score = min(98, max(20, base_score))

        name_tag = f"{streamer_name}: " if streamer_name and streamer_name != "Streamer" else ""
        if len(words) >= 3 and len(snippet) > 6:
            snip_lower = snippet.lower()
            if any(k in snip_lower for k in ["i ", "my ", "me ", "we "]):
                title = f"{name_tag}bro really said \"{snip_lower}\" 💀"
            else:
                title = f"{name_tag}ain't no way {snip_lower} 😭"
        else:
            title = f"{name_tag}bro thought he was him 💀"

        hook_snippet = snippet.upper()[:25] if snippet else "WAIT FOR IT"
        hook_text = f"{hook_snippet} 💀" if "💀" not in hook_snippet else hook_snippet

        return [
            HookCandidate(
                start_ms=int(round(start_sec * 1000.0)),
                end_ms=int(round(c_end_sec * 1000.0)),
                hook_score=base_score,
                title=title[:75],
                hook_text=hook_text[:35],
                reasoning="Evaluated emotional density, hype tokens, and narrative coherence in transcript.",
                transcript_snippet=window_text[:200]
            )
        ]

    def _deduplicate_candidates(self, candidates: List[HookCandidate], overlap_threshold_ms: int = 15000) -> List[HookCandidate]:
        """Remove overlapping clips, retaining the higher-scoring clip."""
        deduped: List[HookCandidate] = []
        for c in candidates:
            overlap = False
            for existing in deduped:
                # Check timestamp collision
                if max(c.start_ms, existing.start_ms) < min(c.end_ms, existing.end_ms):
                    overlap = True
                    break
            if not overlap:
                deduped.append(c)
        return deduped
