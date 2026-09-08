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
    archetype: str = "None"
    start_word: str = ""
    end_word: str = ""
    editorial_reasoning: str = ""

    @property
    def duration_sec(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


class HookScorer:
    """Evaluates transcript windows for retention, punchlines, and virality potential."""

    def __init__(self, min_hook_score: int = 80):
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
        window_sec: int = 45,
        step_sec: int = 15
    ) -> List[HookCandidate]:
        """
        Slice transcript into overlapping windows and execute Lead Editorial Director virality scoring.
        Aligns boundaries to word timestamps and strictly enforces 8/10+ (80%+) retention gate.
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

            # Extract transcript text and segments within window
            window_segments = [
                seg for seg in transcript_segments
                if float(_extract_seg_field(seg, "start", 0.0) or 0.0) >= (current_start - 0.5)
                and float(_extract_seg_field(seg, "end", 0.0) or 0.0) <= (current_end + 0.5)
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
                    streamer_name=streamer_name,
                    window_segments=window_segments,
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
            window_sec=45,
            step_sec=10,
        )

        if not candidates:
            return None

        best = candidates[0]
        if best.hook_score >= threshold:
            return best
        return None

    def _align_word_timestamps(
        self,
        window_segments: list,
        start_word: str,
        end_word: str,
        fallback_start_sec: float,
        fallback_end_sec: float,
    ) -> tuple[int, int]:
        """
        Match start_word and end_word to Whisper word timestamps for millisecond precision cut alignment.
        Clamps duration strictly between 20s and 45s.
        """
        clean_sw = re.sub(r"[^\w]", "", start_word).lower()
        clean_ew = re.sub(r"[^\w]", "", end_word).lower()

        flattened_words: list[dict] = []
        for seg in window_segments:
            words_attr = _extract_seg_field(seg, "words", []) or []
            for w in words_attr:
                w_text = _extract_seg_field(w, "word", "") or ""
                w_start = float(_extract_seg_field(w, "start", 0.0) or 0.0)
                w_end = float(_extract_seg_field(w, "end", 0.0) or 0.0)
                clean_w = re.sub(r"[^\w]", "", w_text).lower()
                if clean_w:
                    flattened_words.append({
                        "clean": clean_w,
                        "raw": w_text,
                        "start_ms": int(round(w_start * 1000.0)),
                        "end_ms": int(round(w_end * 1000.0)),
                    })

        matched_start_ms = None
        matched_end_ms = None

        if clean_sw and flattened_words:
            for w in flattened_words:
                if w["clean"] == clean_sw or clean_sw in w["clean"]:
                    matched_start_ms = w["start_ms"]
                    break

        if clean_ew and flattened_words:
            for w in reversed(flattened_words):
                if w["clean"] == clean_ew or clean_ew in w["clean"]:
                    matched_end_ms = w["end_ms"]
                    break

        # Fallback to float bounds if word alignment misses
        final_start_ms = matched_start_ms if matched_start_ms is not None else int(round(fallback_start_sec * 1000.0))
        final_end_ms = matched_end_ms if matched_end_ms is not None else int(round(fallback_end_sec * 1000.0))

        # Enforce 20s minimum and 45s maximum duration constraints
        if final_end_ms <= final_start_ms:
            final_end_ms = final_start_ms + 35000

        dur_ms = final_end_ms - final_start_ms
        if dur_ms < 20000:
            final_end_ms = final_start_ms + 20000
        elif dur_ms > 45000:
            final_end_ms = final_start_ms + 45000

        return final_start_ms, final_end_ms

    def _score_window_llm(
        self,
        window_text: str,
        start_sec: float,
        end_sec: float,
        streamer_name: str,
        window_segments: Optional[list] = None,
    ) -> List[HookCandidate]:
        """Call NVIDIA NIM or local Ollama LLM to get structured JSON clip evaluations."""
        prompt = self._build_prompt(window_text, start_sec, end_sec, streamer_name)
        segments_ref = window_segments or []

        # 1. Try NVIDIA NIM endpoints if API key available and circuit breaker open
        if self.nvidia_api_key and not self._nim_disabled:
            models_to_try = [self.nvidia_model, self.nvidia_fallback_model]
            for model in models_to_try:
                if not model:
                    continue
                try:
                    response = self._call_nvidia_nim(prompt, model)
                    if response:
                        parsed = self._parse_llm_json(response, window_text, start_sec, end_sec, segments_ref)
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
                    parsed = self._parse_llm_json(ollama_response, window_text, start_sec, end_sec, segments_ref)
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
                {
                    "role": "system",
                    "content": "You are the Lead Editorial Director for a viral short-form media brand. Output ONLY raw JSON matching the exact schema."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
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
            "options": {"temperature": 0.2},
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
        """Create structured Lead Editorial Director prompt with 4 archetypes, hard negative constraints, and few-shots."""
        return f"""You are the Lead Editorial Director for a viral short-form media brand.
Your objective is to evaluate 60-90 second live stream transcripts and identify ONLY high-retention, standalone candidate clips (20-45 seconds).

### TARGET CLIP ARCHETYPES:
1. The Rage / Meltdown: Sudden spike in vocal pitch/volume following an unexpected in-game death or betrayal.
2. The Plot Twist / Fail: Streamer acts overconfident ("Watch this clutch"), followed immediately by instant failure.
3. Unfiltered Storytime: A cohesive narrative with an intriguing premise that hooks the listener within the first 3 seconds and concludes with a punchline.
4. Out-of-Context Absurdity: Bizarre statements or interactions between chat and streamer that sound surreal out of context.

### CLIP CRITERIA:
1. THE HOOK (0-3s): The selected window MUST open with an immediate point of intrigue, high energy, or a shocking statement.
2. ESCALATION: The tension or humor must continuously build without dead air.
3. THE PUNCHLINE/PAYOFF: The clip must end immediately after the climax or punchline (e.g., laughter, desk slam, or mic drop).

### HARD NEGATIVE CONSTRAINTS (INSTANT DISQUALIFICATION):
- Cold Intros: REJECT if context requires knowing what happened 5 minutes earlier.
- Streamer Admin Tasks: REJECT if reading out sub names, adjusting OBS/mic settings, or loading screens.
- Dangling Sentences: REJECT if dialogue ends mid-thought or mid-sentence.
- Monotone Delivery: REJECT if speech cadence shows zero emotional inflection or energy.
- If no segment meets a retention score of 8/10 or higher, return "is_viral": false.

### FEW-SHOT CALIBRATION EXAMPLES:
[POSITIVE EXAMPLE]
Transcript: "Bro trust me on this flank I'm literally top 500 in this lobby just watch me cook... wait where is he... NO NO NO HOW DID HE HEADSHOT ME THROUGH THE WALL!?"
Output:
{{
  "is_viral": true,
  "archetype": "The Plot Twist / Fail",
  "start_word": "Bro",
  "end_word": "WALL",
  "hook_overlay": "HE THOUGHT HE WAS HIM 💀",
  "retention_score": 9,
  "editorial_reasoning": "Instant overconfidence setup followed by immediate catastrophic failure and scream."
}}

[NEGATIVE EXAMPLE]
Transcript: "Okay wait chat let me fix my audio settings... thanks for the 5 gifted subs xXGamerXx appreciate the love man... alright let's queue up again."
Output:
{{
  "is_viral": false,
  "archetype": "None",
  "start_word": "",
  "end_word": "",
  "hook_overlay": "",
  "retention_score": 2,
  "editorial_reasoning": "Administrative filler and sub alerts with zero narrative hook or entertainment value."
}}

---
STREAMER: {streamer_name}
TRANSCRIPT WINDOW:
\"\"\"{window_text}\"\"\"

OUTPUT MUST BE ONLY A SINGLE RAW JSON OBJECT:
{{
  "is_viral": true,
  "archetype": "The Rage / Meltdown" | "The Plot Twist / Fail" | "Unfiltered Storytime" | "Out-of-Context Absurdity" | "None",
  "start_word": "<exact word in transcript>",
  "end_word": "<exact word in transcript>",
  "hook_overlay": "<3-5 word high-impact Gen Z caption>",
  "retention_score": <int 1-10>,
  "editorial_reasoning": "<1 sentence justifying why this converts on TikTok/Shorts>"
}}
"""

    def _parse_llm_json(
        self,
        response: str,
        window_text: str,
        start_sec: float,
        end_sec: float,
        window_segments: list,
    ) -> List[HookCandidate]:
        """Extract and validate JSON clip objects from LLM response with word alignment and strict 8/10 gate."""
        try:
            cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

            # Extract JSON block
            data = None
            code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
            if code_blocks:
                for b in reversed(code_blocks):
                    try:
                        data = json.loads(b)
                        if "is_viral" in data or "retention_score" in data:
                            break
                    except Exception:
                        pass

            if not data:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(cleaned[start:end])

            if not data or not isinstance(data, dict):
                return []

            is_viral = bool(data.get("is_viral", False))
            raw_score = int(data.get("retention_score", 0))

            # Strict 8/10 gate: reject any score < 8 or is_viral == False
            if not is_viral or raw_score < 8:
                logger.debug("Candidate rejected by Lead Editorial gate: viral=%s, score=%d/10", is_viral, raw_score)
                return []

            score_100 = min(100, raw_score * 10)
            archetype = str(data.get("archetype", "Out-of-Context Absurdity"))
            start_word = str(data.get("start_word", "")).strip()
            end_word = str(data.get("end_word", "")).strip()
            hook_overlay = str(data.get("hook_overlay", "")).strip() or "BRO NO WAY 💀"
            reasoning = str(data.get("editorial_reasoning", "")).strip()

            # Map exact Whisper word timestamps
            start_ms, end_ms = self._align_word_timestamps(
                window_segments=window_segments,
                start_word=start_word,
                end_word=end_word,
                fallback_start_sec=start_sec,
                fallback_end_sec=end_sec,
            )

            title = f"{hook_overlay} #shorts"

            return [
                HookCandidate(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    hook_score=score_100,
                    title=title,
                    hook_text=hook_overlay,
                    reasoning=reasoning,
                    transcript_snippet=window_text[:200],
                    archetype=archetype,
                    start_word=start_word,
                    end_word=end_word,
                    editorial_reasoning=reasoning,
                )
            ]

        except Exception as e:
            logger.debug("Failed to parse Lead Editorial Director JSON: %s", e)
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

        # Archetype heuristic classification
        archetype = "Out-of-Context Absurdity"
        if any(k in text_lower for k in ["rage", "lost it", "screaming", "crying", "wtf"]):
            archetype = "The Rage / Meltdown"
        elif any(k in text_lower for k in ["clutch", "hack", "aimbot", "dead", "ruined"]):
            archetype = "The Plot Twist / Fail"
        elif any(k in text_lower for k in ["i ", "my ", "story", "yesterday", "told him"]):
            archetype = "Unfiltered Storytime"

        start_word = words[0] if words else ""
        end_word = words[-1] if words else ""

        return [
            HookCandidate(
                start_ms=int(round(start_sec * 1000.0)),
                end_ms=int(round(c_end_sec * 1000.0)),
                hook_score=base_score,
                title=title[:75],
                hook_text=hook_text[:35],
                reasoning="Evaluated emotional density, hype tokens, and narrative coherence in transcript.",
                transcript_snippet=window_text[:200],
                archetype=archetype,
                start_word=start_word,
                end_word=end_word,
                editorial_reasoning=f"Classified as {archetype} based on acoustic/semantic keyword density.",
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
