"""Dream Team — Scribe Agent
The SEO Wordsmith.

Scribe generates optimised titles, descriptions, and tags for streaming
clips destined for YouTube Shorts and similar platforms.  It leverages
LLM inference for creative copywriting and applies deterministic
guardrails (length limits, profanity filtering, tag counts).
"""
import json
import re
from typing import Any, Dict, List, Optional

from dream_team import config
from dream_team.base_agent import BaseAgent
from dream_team.memory import SharedMemory
from dream_team.tools import TOOL_REGISTRY


class Scribe(BaseAgent):
    """SEO Wordsmith — generates titles, descriptions, and tags.

    Usage::

        memory = SharedMemory()
        scribe = Scribe(memory)
        title = scribe.generate_title(
            transcript="No way, that was insane!",
            emotion="excited",
            streamer_name="DrDisrespect",
        )
        print(title)  # "🤯 DrDisrespect Can't BELIEVE What Just Happened!"
    """

    # Popular gaming / streaming emojis for title injection
    _EMOTION_EMOJIS: Dict[str, List[str]] = {
        "excited": ["🔥", "🤯", "😱", "⚡"],
        "angry": ["😡", "💢", "🤬", "👊"],
        "surprised": ["😱", "🤯", "😳", "❗"],
        "happy": ["😂", "🎉", "💯", "😄"],
        "sad": ["😢", "💔", "😭", "🥺"],
        "frustrated": ["😤", "💀", "🫠", "😩"],
        "scared": ["😨", "😰", "💀", "👀"],
        "neutral": ["👀", "🎮", "🎯", "💬"],
    }

    # Fallback emojis when emotion is unrecognised
    _DEFAULT_EMOJIS: List[str] = ["🔥", "💥", "🎮", "⚡"]

    def __init__(self, memory: SharedMemory) -> None:
        super().__init__(
            name="scribe",
            description="SEO Wordsmith — generates titles, descriptions, and tags",
            agent_config=config.SCRIBE_CONFIG,
        )
        self.memory = memory

        # Register text-processing tools
        for tool_name in ("count_words", "detect_language", "is_profane", "slugify", "truncate_text"):
            if tool_name in TOOL_REGISTRY:
                self.register_tool(tool_name, TOOL_REGISTRY[tool_name])

        self.logger.info(
            "Scribe ready — max_title=%d, style=%s, emoji=%s, tags=%d–%d",
            self.agent_config.get("max_title_length", 80),
            self.agent_config.get("title_style", "clickbait"),
            self.agent_config.get("include_emoji", True),
            self.agent_config.get("min_tags", 5),
            self.agent_config.get("max_tags", 8),
        )

    # ──────────────────────────────────────────────────────────────────
    # Title generation
    # ──────────────────────────────────────────────────────────────────

    def generate_title(
        self,
        transcript: str,
        emotion: str,
        streamer_name: str,
    ) -> str:
        """Generate a clickbait-style title for a clip.

        The title is capped at :pydata:`max_title_length` characters
        (default 80), optionally prefixed with an emoji, and checked
        for profanity.

        Args:
            transcript: Clip transcript / captions.
            emotion: Dominant detected emotion.
            streamer_name: Display name of the streamer.

        Returns:
            A ready-to-publish title string.
        """
        self.logger.info(
            "generate_title() — streamer=%s, emotion=%s", streamer_name, emotion,
        )

        max_length: int = self.agent_config.get("max_title_length", 80)
        include_emoji: bool = self.agent_config.get("include_emoji", True)
        style: str = self.agent_config.get("title_style", "clickbait")

        prompt = self._build_title_prompt(transcript, emotion, streamer_name, style, max_length)
        raw_title = self.think(prompt, temperature=0.8, max_tokens=100)

        # Clean up the response — strip quotes, extra whitespace, newlines
        title = self._clean_title(raw_title)

        # Add emoji prefix if enabled
        if include_emoji:
            title = self._add_emoji(title, emotion)

        # Enforce length limit
        if len(title) > max_length:
            title = self.use_tool("truncate_text", text=title, max_length=max_length)

        # Profanity check
        try:
            if self.use_tool("is_profane", text=title):
                self.logger.warning("Profanity detected in generated title — sanitising")
                title = self._sanitise_title(title)
        except Exception as exc:
            self.logger.debug("Profanity check skipped: %s", exc)

        self.logger.info("Generated title (%d chars): %s", len(title), title)
        return title

    # ──────────────────────────────────────────────────────────────────
    # Description generation
    # ──────────────────────────────────────────────────────────────────

    def generate_description(
        self,
        transcript: str,
        title: str,
        streamer_name: str,
        tags: List[str],
    ) -> str:
        """Create a YouTube Shorts description with hashtags and CTA.

        Args:
            transcript: Clip transcript.
            title: The already-generated title.
            streamer_name: Streamer display name.
            tags: List of tags to convert into hashtags.

        Returns:
            Multi-line description string ready for upload.
        """
        self.logger.info("generate_description() — title=%s", title[:50])

        prompt = f"""You are a YouTube Shorts copywriter for gaming/streaming content.

Write a short, engaging description for a YouTube Shorts clip.

TITLE: {title}
STREAMER: {streamer_name}
TRANSCRIPT EXCERPT: {transcript[:300]}

Requirements:
- 2-3 sentences maximum
- Include a call to action (like, subscribe, follow)
- Engaging and casual tone
- Do NOT include hashtags (they will be added separately)
- Do NOT repeat the title verbatim

Respond with ONLY the description text, no quotes or labels."""

        raw_desc = self.think(prompt, temperature=0.7, max_tokens=200)
        description = raw_desc.strip().strip('"').strip("'")

        # Build hashtag section
        hashtags = self._format_hashtags(tags, streamer_name)

        # Assemble final description
        full_description = f"{description}\n\n{hashtags}"

        self.logger.info("Generated description (%d chars)", len(full_description))
        return full_description

    # ──────────────────────────────────────────────────────────────────
    # Tag generation
    # ──────────────────────────────────────────────────────────────────

    def generate_tags(
        self,
        transcript: str,
        emotion: str,
        streamer_name: str,
    ) -> List[str]:
        """Generate SEO-optimised tags for a clip.

        Produces between ``min_tags`` (5) and ``max_tags`` (8) tags
        combining streamer-specific, emotion, content, and trending
        keywords.

        Args:
            transcript: Clip transcript.
            emotion: Dominant detected emotion.
            streamer_name: Streamer display name.

        Returns:
            A list of tag strings.
        """
        self.logger.info(
            "generate_tags() — streamer=%s, emotion=%s", streamer_name, emotion,
        )

        min_tags: int = self.agent_config.get("min_tags", 5)
        max_tags: int = self.agent_config.get("max_tags", 8)

        prompt = f"""You are an SEO expert for YouTube Shorts gaming/streaming content.

Generate {max_tags} relevant tags for a clip.

TRANSCRIPT: {transcript[:400]}
EMOTION: {emotion}
STREAMER: {streamer_name}

Requirements:
- Mix of: streamer-specific, emotion-based, game/content, and trending tags
- Each tag should be 1-3 words
- No hashtag symbols, just the words
- Optimised for YouTube search and discovery

Respond with ONLY a JSON array of strings, e.g. ["tag1", "tag2", ...]"""

        raw_response = self.think(prompt, temperature=0.6, max_tokens=150)
        tags = self._parse_tags_response(raw_response, streamer_name, emotion)

        # Enforce count bounds
        if len(tags) < min_tags:
            tags = self._pad_tags(tags, min_tags, streamer_name, emotion)
        tags = tags[:max_tags]

        self.logger.info("Generated %d tags: %s", len(tags), tags)
        return tags

    # ──────────────────────────────────────────────────────────────────
    # One-stop SEO enhancement
    # ──────────────────────────────────────────────────────────────────

    def enhance_seo(self, clip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance a clip dict with title, description, tags, and hook text.

        This is the primary entry-point that orchestrates all Scribe
        capabilities in a single call.

        Args:
            clip_data: Dict expected to contain at minimum:
                ``transcript`` (str), ``emotion`` (str),
                ``streamer_name`` (str).  Optional: ``tags`` (list).

        Returns:
            A copy of *clip_data* enriched with ``title``,
            ``description``, ``tags``, and ``hook_text``.
        """
        self.logger.info("enhance_seo() — processing clip data")

        transcript: str = clip_data.get("transcript", "")
        emotion: str = clip_data.get("emotion", "neutral")
        streamer_name: str = clip_data.get("streamer_name", "Streamer")

        if not transcript:
            self.logger.warning("enhance_seo() called with empty transcript")
            return {**clip_data, "title": "", "description": "", "tags": [], "hook_text": ""}

        # Generate all SEO assets
        tags = self.generate_tags(transcript, emotion, streamer_name)
        title = self.generate_title(transcript, emotion, streamer_name)
        description = self.generate_description(transcript, title, streamer_name, tags)
        hook_text = self._generate_hook(transcript, emotion)

        enhanced = {
            **clip_data,
            "title": title,
            "description": description,
            "tags": tags,
            "hook_text": hook_text,
        }

        # Persist the SEO result in shared memory
        try:
            clip_id = clip_data.get("clip_id", clip_data.get("id", "unknown"))
            self.memory.store(
                key=f"seo_{clip_id}",
                value={"title": title, "tags": tags, "hook_text": hook_text},
                category="clips",
                agent=self.name,
            )
        except Exception as exc:
            self.logger.error("Failed to store SEO data in memory: %s", exc)

        self.logger.info("enhance_seo() complete — title='%s'", title[:60])
        return enhanced

    # ──────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────

    def _build_title_prompt(
        self,
        transcript: str,
        emotion: str,
        streamer_name: str,
        style: str,
        max_length: int,
    ) -> str:
        """Build the LLM prompt for title generation."""
        return f"""You are a viral YouTube Shorts title writer for gaming/streaming clips.

Write ONE {style}-style title for this clip.

TRANSCRIPT: {transcript[:300]}
STREAMER: {streamer_name}
EMOTION: {emotion}

Rules:
- Maximum {max_length} characters (STRICT — do not exceed)
- {style.upper()} style — attention-grabbing and dramatic
- Include the streamer's name when it fits naturally
- Use CAPS for 1-2 key words for emphasis
- Do NOT include emojis (they will be added separately)
- Do NOT use quotation marks around the title

Respond with ONLY the title text, nothing else."""

    def _clean_title(self, raw: str) -> str:
        """Strip formatting artefacts from LLM-generated title text."""
        title = raw.strip()
        # Remove surrounding quotes
        for quote in ('"', "'", '"', '"', "'", "'"):
            if title.startswith(quote) and title.endswith(quote):
                title = title[1:-1]
        # Take only the first line
        title = title.split("\n")[0].strip()
        # Remove "Title:" prefix if present
        title = re.sub(r"^(?:title\s*[:：]\s*)", "", title, flags=re.IGNORECASE)
        return title.strip()

    def _add_emoji(self, title: str, emotion: str) -> str:
        """Prepend an emotion-appropriate emoji to the title."""
        emojis = self._EMOTION_EMOJIS.get(emotion.lower(), self._DEFAULT_EMOJIS)
        emoji = emojis[0] if emojis else "🔥"
        # Avoid duplicating if the title already starts with an emoji
        if title and title[0] in "".join(
            e for elist in self._EMOTION_EMOJIS.values() for e in elist
        ):
            return title
        return f"{emoji} {title}"

    def _sanitise_title(self, title: str) -> str:
        """Remove or mask profane words from a title."""
        from dream_team.tools import censor_profanity
        return censor_profanity(title)

    def _format_hashtags(self, tags: List[str], streamer_name: str) -> str:
        """Format tags as a hashtag string including #Shorts."""
        hashtags = ["#Shorts"]
        # Add streamer hashtag
        streamer_tag = f"#{streamer_name.replace(' ', '')}"
        if streamer_tag not in hashtags:
            hashtags.append(streamer_tag)
        # Add content hashtags
        for tag in tags:
            ht = "#" + tag.replace(" ", "").replace("-", "")
            if ht not in hashtags:
                hashtags.append(ht)
        return " ".join(hashtags)

    def _parse_tags_response(
        self,
        raw_response: str,
        streamer_name: str,
        emotion: str,
    ) -> List[str]:
        """Parse a JSON array of tags from the LLM response."""
        try:
            # Try to find a JSON array in the response
            json_match = re.search(r"\[[\s\S]*?\]", raw_response)
            if json_match:
                tags = json.loads(json_match.group())
                if isinstance(tags, list):
                    return [str(t).strip() for t in tags if str(t).strip()]
            raise ValueError("No JSON array found")
        except Exception as exc:
            self.logger.warning(
                "Failed to parse tags from LLM, using fallback: %s", exc,
            )
            return self._fallback_tags(streamer_name, emotion)

    def _fallback_tags(self, streamer_name: str, emotion: str) -> List[str]:
        """Generate deterministic fallback tags when LLM parsing fails."""
        return [
            streamer_name,
            emotion,
            "gaming",
            "stream highlights",
            "funny moments",
            "best clips",
            "twitch clips",
        ]

    def _pad_tags(
        self,
        tags: List[str],
        target_count: int,
        streamer_name: str,
        emotion: str,
    ) -> List[str]:
        """Add generic tags until we reach *target_count*."""
        filler = [
            streamer_name, emotion, "gaming", "stream highlights",
            "funny moments", "best clips", "twitch clips", "viral gaming",
        ]
        existing_lower = {t.lower() for t in tags}
        for filler_tag in filler:
            if len(tags) >= target_count:
                break
            if filler_tag.lower() not in existing_lower:
                tags.append(filler_tag)
                existing_lower.add(filler_tag.lower())
        return tags

    def _generate_hook(self, transcript: str, emotion: str) -> str:
        """Generate a short hook / overlay text for the clip's first 2 seconds.

        Uses a lightweight LLM call for a punchy one-liner.
        """
        prompt = f"""Write a VERY short hook text (max 8 words) for a streaming clip overlay.
This is shown in the first 2 seconds to grab attention.

EMOTION: {emotion}
TRANSCRIPT START: {transcript[:150]}

Rules:
- Maximum 8 words
- All caps
- Punchy and attention-grabbing
- Examples: "WAIT FOR IT...", "HE DIDN'T JUST DO THAT", "THIS IS INSANE"

Respond with ONLY the hook text, nothing else."""

        raw_hook = self.think(prompt, temperature=0.9, max_tokens=30)
        hook = raw_hook.strip().strip('"').strip("'").upper()

        # Enforce word limit
        words = hook.split()
        if len(words) > 8:
            hook = " ".join(words[:8])

        return hook
