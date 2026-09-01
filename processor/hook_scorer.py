"""
StreamClipper / LumiClip — 0-100 Virality Hook Scoring Engine
Analyzes transcript windows (30-90s) with structured LLM prompts (NVIDIA Nemotron)
to isolate high-retention clips, generate punchy hook assertions, and rank by virality (>=80).
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

    def __init__(self, min_hook_score: int = 75):
        self.min_hook_score = min_hook_score
        self.nvidia_api_key = getattr(config, "NVIDIA_API_KEY", "") or os.environ.get("NVIDIA_API_KEY", "")
        self.nvidia_model = getattr(config, "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
        self.nvidia_fallback_model = getattr(config, "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.fast_backup_model = "meta/llama-3.2-11b-vision-instruct"

    def score_transcript(
        self,
        transcript_segments: list,
        streamer_name: str = "Streamer",
        window_sec: int = 60,
        step_sec: int = 30
    ) -> List[HookCandidate]:
        """
        Slice transcript into overlapping windows and execute structured virality scoring.
        """
        if not transcript_segments:
            return []

        # Find total transcript duration
        max_end_sec = max(seg.get("end", 0) for seg in transcript_segments)
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
                if seg.get("start", 0) >= current_start and seg.get("end", 0) <= current_end
            ]
            
            window_text = " ".join(seg.get("text", "").strip() for seg in window_segments).strip()
            
            if len(window_text.split()) >= 15:  # Require meaningful speech density
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
        logger.info("HookScorer evaluated transcript: %d candidates found (%d >= %d score)",
                    len(candidates), len(deduped), self.min_hook_score)
        return deduped

    def _score_window_llm(
        self,
        window_text: str,
        start_sec: float,
        end_sec: float,
        streamer_name: str
    ) -> List[HookCandidate]:
        """Call NVIDIA NIM to get structured JSON clip evaluations."""
        prompt = self._build_prompt(window_text, start_sec, end_sec, streamer_name)

        models_to_try = [self.nvidia_model, self.nvidia_fallback_model, self.fast_backup_model]

        for model in models_to_try:
            if not model or not self.nvidia_api_key:
                continue
            try:
                response = self._call_nvidia_nim(prompt, model)
                if response:
                    parsed = self._parse_llm_json(response, window_text, start_sec, end_sec)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.warning("HookScorer model %s failed: %s", model, e)

        # Local heuristic fallback if LLM is unreachable
        return self._heuristic_fallback(window_text, start_sec, end_sec, streamer_name)

    def _call_nvidia_nim(self, prompt: str, model: str) -> Optional[str]:
        """Execute HTTP request to NVIDIA NIM cloud endpoint."""
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
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return None

    def _build_prompt(self, window_text: str, start_sec: float, end_sec: float, streamer_name: str) -> str:
        """Create structured prompt enforcing strict JSON output."""
        return f"""Analyze this {int(end_sec - start_sec)}s audio transcript segment from streamer '{streamer_name}'.
Window start: {start_sec:.1f}s, Window end: {end_sec:.1f}s.

Transcript:
\"\"\"{window_text}\"\"\"

Identify if there is a viral highlight moment in this window. Rate virality on a scale of 0 to 100.
High scores (80-100) require:
- Strong 3-second opening hook / sudden statement
- High emotional reaction, punchline, victory, or failure
- Cohesive standalone context for TikTok / YouTube Shorts

Output a JSON object matching this schema:
{{
  "clips": [
    {{
      "start_sec": {start_sec:.1f},
      "end_sec": {end_sec:.1f},
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
        """Extract and validate JSON clip objects from LLM response."""
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
                score = int(item.get("hook_score", 50))
                title = str(item.get("title", ""))[:80]
                hook_text = str(item.get("hook_text", ""))[:40]
                reasoning = str(item.get("reasoning", ""))

                results.append(
                    HookCandidate(
                        start_ms=int(c_start_sec * 1000),
                        end_ms=int(c_end_sec * 1000),
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
        """Fallback scoring using keyword density and punctuation energy."""
        hype_keywords = ["clutch", "insane", "omg", "no way", "wtf", "gg", "win", "dead", "unbelievable", "bro"]
        text_lower = window_text.lower()
        
        matches = sum(1 for k in hype_keywords if k in text_lower)
        exclamations = window_text.count("!") + window_text.count("?")
        
        base_score = 60 + min(35, matches * 10 + exclamations * 4)

        return [
            HookCandidate(
                start_ms=int(start_sec * 1000),
                end_ms=int(end_sec * 1000),
                hook_score=base_score,
                title=f"UNBELIEVABLE moment by {streamer_name}! 😱",
                hook_text="YOU WON'T BELIEVE THIS 🤯",
                reasoning="Detected high-energy emotional vocabulary in transcript.",
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
