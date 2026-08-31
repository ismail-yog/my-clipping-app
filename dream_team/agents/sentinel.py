"""Dream Team — Sentinel Agent
The Content Guardian: reviews clips for quality, safety, and compliance.

Sentinel runs a multi-stage moderation pipeline:
    1. Profanity detection and censoring
    2. Content quality analysis (LLM-powered)
    3. Caption accuracy verification
    4. Auto-moderation with approve / flag / reject decisions
"""
import json
import re
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory
from dream_team.tools import (
    censor_profanity,
    count_words,
    detect_language,
    is_profane,
)


# Minimum word count for a transcript to be considered valid
_MIN_TRANSCRIPT_WORDS = 5
# Maximum word count before a caption is considered too long for Shorts
_MAX_CAPTION_WORDS = 300
# Approval threshold used by auto_moderate
_AUTO_APPROVE_THRESHOLD = 0.7
# Critical flags that block auto-approval regardless of score
_CRITICAL_FLAGS = frozenset({
    "profanity_detected",
    "harmful_content",
    "misleading_claims",
    "hate_speech",
})


class Sentinel(BaseAgent):
    """Content Guardian agent — reviews clips for quality, safety, and compliance.

    Attributes:
        memory: Shared memory store for cross-agent communication.
        cfg: Agent-specific configuration from ``config.SENTINEL_CONFIG``.
    """

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="sentinel",
            description="Content Guardian — reviews clips for quality, safety, and compliance.",
            agent_config=config.SENTINEL_CONFIG,
        )
        self.memory = memory
        self.cfg: Dict[str, Any] = config.SENTINEL_CONFIG

        # Register text-safety tools
        self.register_tool("is_profane", is_profane)
        self.register_tool("censor_profanity", censor_profanity)
        self.register_tool("count_words", count_words)
        self.register_tool("detect_language", detect_language)

        self.logger.info("Sentinel initialised — config: %s", self.cfg)

    # ──────────────────────────────────────────────────────────────────
    # Primary review entry-point
    # ──────────────────────────────────────────────────────────────────

    def review_clip(self, clip_data: dict) -> dict:
        """Run all review checks on a clip and return a consolidated verdict.

        Args:
            clip_data: Dictionary with keys such as *transcript*, *title*,
                *description*, *tags*, and *emotion*.

        Returns:
            A dict with::

                {
                    "approved": bool,
                    "flags": [str, ...],
                    "warnings": [str, ...],
                    "score": float,   # 0.0–1.0
                    "reasoning": str,
                }
        """
        self.logger.info("review_clip() — starting full review")

        transcript: str = clip_data.get("transcript", "")
        title: str = clip_data.get("title", "")
        description: str = clip_data.get("description", "")
        tags: List[str] = clip_data.get("tags", [])
        emotion: str = clip_data.get("emotion", "neutral")

        flags: List[str] = []
        warnings: List[str] = []
        scores: List[float] = []

        # ── 1. Profanity check ───────────────────────────────────────
        if self.cfg.get("check_profanity", True):
            profanity_result = self.check_profanity(transcript)
            if not profanity_result["clean"]:
                flags.append("profanity_detected")
                warnings.append(
                    f"Profanity found: {', '.join(profanity_result['flagged_words'])}"
                )
                scores.append(0.3)
            else:
                scores.append(1.0)

            # Also scan the title and description
            for field_name, field_value in [("title", title), ("description", description)]:
                if field_value and self.use_tool("is_profane", text=field_value):
                    flags.append(f"profanity_in_{field_name}")
                    warnings.append(f"Profanity detected in {field_name}.")
                    scores.append(0.2)

        # ── 2. Content quality check ─────────────────────────────────
        quality_result = self.check_content_quality(transcript, title)
        scores.append(quality_result["quality_score"])
        if quality_result["issues"]:
            for issue in quality_result["issues"]:
                if any(kw in issue.lower() for kw in ("harmful", "hate", "dangerous")):
                    flags.append("harmful_content")
                elif "misleading" in issue.lower():
                    flags.append("misleading_claims")
                else:
                    warnings.append(issue)

        # ── 3. Caption accuracy check ────────────────────────────────
        if self.cfg.get("check_captions", True):
            caption_result = self.check_caption_accuracy(transcript)
            if not caption_result["accurate"]:
                warnings.extend(caption_result["issues"])
                scores.append(0.5)
            else:
                scores.append(1.0)

        # ── 4. Tag sanity ────────────────────────────────────────────
        if tags:
            for tag in tags:
                if self.use_tool("is_profane", text=tag):
                    flags.append("profanity_in_tags")
                    warnings.append(f"Tag contains profanity: '{tag}'")
                    scores.append(0.2)
                    break  # one flag is enough

        # ── Aggregate score ──────────────────────────────────────────
        overall_score = round(sum(scores) / max(len(scores), 1), 2)
        approved = overall_score >= _AUTO_APPROVE_THRESHOLD and not (
            set(flags) & _CRITICAL_FLAGS
        )

        # Build reasoning summary
        reasoning_parts: List[str] = []
        if flags:
            reasoning_parts.append(f"Flagged for: {', '.join(flags)}.")
        if warnings:
            reasoning_parts.append(f"Warnings: {'; '.join(warnings)}.")
        if approved:
            reasoning_parts.append("Clip meets quality and safety standards.")
        else:
            reasoning_parts.append("Clip did NOT pass moderation.")
        reasoning = " ".join(reasoning_parts)

        result = {
            "approved": approved,
            "flags": list(set(flags)),
            "warnings": warnings,
            "score": overall_score,
            "reasoning": reasoning,
        }

        # Persist the review in shared memory
        clip_id = clip_data.get("id", clip_data.get("title", "unknown"))
        self.memory.store(
            key=f"sentinel_review_{clip_id}",
            value=result,
            category="clips",
            agent=self.name,
        )
        self.remember("last_review", result)

        self.logger.info(
            "review_clip() complete — approved=%s, score=%.2f, flags=%s",
            approved, overall_score, flags,
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Profanity
    # ──────────────────────────────────────────────────────────────────

    def check_profanity(self, text: str) -> dict:
        """Scan *text* for profanity and return a clean/censored report.

        Returns:
            A dict with::

                {
                    "clean": bool,
                    "flagged_words": [str, ...],
                    "censored_text": str,
                }
        """
        self.logger.info("check_profanity() — scanning %d chars", len(text))

        if not text or not text.strip():
            return {"clean": True, "flagged_words": [], "censored_text": text}

        has_profanity: bool = self.use_tool("is_profane", text=text)
        censored: str = self.use_tool("censor_profanity", text=text)

        # Extract flagged words by comparing original vs censored tokens
        flagged_words: List[str] = []
        if has_profanity:
            original_tokens = text.split()
            censored_tokens = censored.split()
            for orig, cens in zip(original_tokens, censored_tokens):
                if orig != cens:
                    flagged_words.append(orig)

        result = {
            "clean": not has_profanity,
            "flagged_words": flagged_words,
            "censored_text": censored,
        }

        self.logger.info(
            "check_profanity() — clean=%s, flagged=%d words",
            result["clean"], len(flagged_words),
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Content quality (LLM-powered)
    # ──────────────────────────────────────────────────────────────────

    def check_content_quality(self, transcript: str, title: str) -> dict:
        """Evaluate content quality and appropriateness for YouTube Shorts.

        Uses :py:meth:`self.think` to perform an LLM-based analysis of
        clickbait accuracy, misleading claims, and harmful content.

        Returns:
            A dict with::

                {
                    "quality_score": float,   # 0.0–1.0
                    "issues": [str, ...],
                }
        """
        self.logger.info("check_content_quality() — analysing content")

        # Fast-path: if both transcript and title are empty, nothing to evaluate
        if not transcript.strip() and not title.strip():
            self.logger.warning("check_content_quality() — empty content supplied")
            return {"quality_score": 0.0, "issues": ["Empty transcript and title"]}

        prompt = (
            "You are a YouTube Shorts content moderator. Analyse the following clip and "
            "return ONLY a valid JSON object (no markdown, no explanation) with these keys:\n"
            '  "quality_score": a float 0.0-1.0 (1 = excellent quality, safe, appropriate),\n'
            '  "issues": a list of short issue strings (empty list if no issues).\n\n'
            "Check for:\n"
            "1. Clickbait accuracy — does the title honestly represent the transcript content?\n"
            "2. Misleading claims — any factually dubious or exaggerated statements?\n"
            "3. Harmful content — hate speech, dangerous advice, self-harm, violence?\n"
            "4. Overall appropriateness for a general YouTube Shorts audience.\n\n"
            f"TITLE: {title}\n\n"
            f"TRANSCRIPT: {transcript[:1500]}\n\n"
            "Respond ONLY with the JSON object."
        )

        try:
            response = self.think(prompt, temperature=0.3, max_tokens=256)
            parsed = self._parse_json_response(response)

            quality_score = float(parsed.get("quality_score", 0.5))
            quality_score = max(0.0, min(1.0, quality_score))
            issues: List[str] = parsed.get("issues", [])

            # In strict mode, lower the score penalty
            if self.cfg.get("strict_mode", False) and issues:
                quality_score = min(quality_score, 0.5)

            result = {"quality_score": round(quality_score, 2), "issues": issues}
        except Exception as exc:
            self.logger.error("check_content_quality() LLM analysis failed: %s", exc)
            result = {
                "quality_score": 0.5,
                "issues": ["Content quality analysis unavailable — LLM error"],
            }

        self.logger.info(
            "check_content_quality() — score=%.2f, issues=%d",
            result["quality_score"], len(result["issues"]),
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Caption accuracy
    # ──────────────────────────────────────────────────────────────────

    def check_caption_accuracy(self, transcript: str) -> dict:
        """Verify that the transcript / caption is structurally sound.

        Checks for:
            - Too short (fewer than :data:`_MIN_TRANSCRIPT_WORDS` words)
            - Too long (more than :data:`_MAX_CAPTION_WORDS` words)
            - Garbled text (high ratio of non-alphanumeric characters)
            - Language detection anomaly

        Returns:
            A dict with::

                {
                    "accurate": bool,
                    "issues": [str, ...],
                }
        """
        self.logger.info("check_caption_accuracy() — verifying transcript")

        issues: List[str] = []

        if not transcript or not transcript.strip():
            return {"accurate": False, "issues": ["Transcript is empty"]}

        word_count: int = self.use_tool("count_words", text=transcript)

        # Too short
        if word_count < _MIN_TRANSCRIPT_WORDS:
            issues.append(
                f"Transcript too short ({word_count} words, minimum {_MIN_TRANSCRIPT_WORDS})"
            )

        # Too long for a Short
        if word_count > _MAX_CAPTION_WORDS:
            issues.append(
                f"Transcript unusually long ({word_count} words, expected ≤{_MAX_CAPTION_WORDS})"
            )

        # Garbled text heuristic: >30% non-alphanumeric, non-space characters
        alnum_count = sum(1 for ch in transcript if ch.isalnum() or ch.isspace())
        total_count = len(transcript)
        if total_count > 0:
            clean_ratio = alnum_count / total_count
            if clean_ratio < 0.70:
                issues.append(
                    f"Possible garbled text (only {clean_ratio:.0%} alphanumeric content)"
                )

        # Language detection
        detected_lang: str = self.use_tool("detect_language", text=transcript)
        if detected_lang != "en":
            # Not necessarily an issue, but worth flagging for review
            issues.append(
                f"Non-English content detected (language: {detected_lang})"
            )

        accurate = len(issues) == 0
        result = {"accurate": accurate, "issues": issues}

        self.logger.info(
            "check_caption_accuracy() — accurate=%s, issues=%d",
            accurate, len(issues),
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Auto-moderation pipeline
    # ──────────────────────────────────────────────────────────────────

    def auto_moderate(self, clip_data: dict) -> dict:
        """Full moderation pipeline — review and classify the clip.

        Runs :py:meth:`review_clip` then makes an automated decision:

        - **approve**: score ≥ 0.7 and no critical flags
        - **reject**: score < 0.4 or any critical flag present
        - **flag**: everything else (needs human review)

        Returns:
            A dict with::

                {
                    "action": "approve" | "flag" | "reject",
                    "details": { ... review_clip output ... },
                }
        """
        self.logger.info("auto_moderate() — starting moderation pipeline")

        review = self.review_clip(clip_data)

        has_critical = bool(set(review["flags"]) & _CRITICAL_FLAGS)
        score = review["score"]

        # Decision logic
        if has_critical or score < 0.4:
            action = "reject"
        elif score >= _AUTO_APPROVE_THRESHOLD and not review["flags"]:
            action = "approve"
        else:
            action = "flag"

        result = {"action": action, "details": review}

        # Persist moderation decision
        clip_id = clip_data.get("id", clip_data.get("title", "unknown"))
        self.memory.store(
            key=f"sentinel_moderation_{clip_id}",
            value=result,
            category="clips",
            agent=self.name,
        )
        self.remember("last_moderation", result)

        self.logger.info(
            "auto_moderate() complete — action=%s, score=%.2f",
            action, score,
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """Best-effort extraction of a JSON object from LLM output.

        Handles common LLM quirks like markdown fences and trailing text.
        """
        # Strip markdown code fences
        text = re.sub(r"```(?:json)?", "", text).strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find the first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {}
