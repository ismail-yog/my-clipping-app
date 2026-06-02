"""
StreamClipper — SEO Generator
Uses Ollama (local LLM) to generate optimized titles, descriptions,
tags, hook text, and thumbnail prompts for YouTube Shorts.
Zero API cost — fully local.
Falls back to templates when Ollama is unavailable.
"""

import json
import logging
import random
from typing import Optional
from dataclasses import dataclass

import requests

import config

logger = logging.getLogger("streamclipper.seo")


@dataclass
class SEOMetadata:
    title: str
    description: str
    tags: list[str]
    hook_text: str  # Bold overlay text for first 3 seconds
    thumbnail_prompt: str  # Text to overlay on thumbnail
    generated_by: str  # "ollama" or "template"


class SEOGenerator:
    """
    Generates optimized YouTube Shorts metadata using a local LLM via Ollama.
    Falls back to template-based generation if Ollama is unavailable.

    Zero cost — no API keys, no subscriptions.
    """

    def __init__(self):
        self._ollama_available: Optional[bool] = None

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and the model is available."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            resp = requests.get(
                f"{config.OLLAMA_HOST}/api/tags",
                timeout=3,
            )
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                # Check for primary or fallback model
                primary = config.OLLAMA_MODEL.split(":")[0]
                if any(primary in m for m in models):
                    self._ollama_available = True
                    logger.info("Ollama connected — model '%s' available", config.OLLAMA_MODEL)
                    return True
                # Check fallback
                fallback = config.OLLAMA_FALLBACK_MODEL.split(":")[0]
                if any(fallback in m for m in models):
                    logger.info(
                        "Primary model '%s' not found, using fallback '%s'",
                        config.OLLAMA_MODEL, config.OLLAMA_FALLBACK_MODEL,
                    )
                    config.OLLAMA_MODEL = config.OLLAMA_FALLBACK_MODEL
                    self._ollama_available = True
                    return True

                logger.warning(
                    "Ollama running but models not found. Available: %s",
                    ", ".join(models) if models else "(none)",
                )
                self._ollama_available = False
                return False

            self._ollama_available = False
            return False

        except requests.RequestException:
            logger.warning("Ollama not reachable at %s — using templates", config.OLLAMA_HOST)
            self._ollama_available = False
            return False

    def generate(
        self,
        transcript: str,
        streamer_name: str,
        emotion: str = "",
        platform: str = "kick",
    ) -> SEOMetadata:
        """Generate SEO metadata. Ollama → template fallback."""
        if self._check_ollama():
            try:
                return self._generate_with_ollama(
                    transcript, streamer_name, emotion, platform
                )
            except Exception as e:
                logger.warning("Ollama SEO failed, using template: %s", e)
                # Reset availability so we retry next time
                self._ollama_available = None

        return self._generate_template(streamer_name, emotion, platform)

    def _generate_with_ollama(
        self,
        transcript: str,
        streamer_name: str,
        emotion: str,
        platform: str,
    ) -> SEOMetadata:
        """Generate SEO using local Ollama LLM."""
        prompt = f"""You are a YouTube Shorts SEO expert. Generate viral metadata for a highlight clip.

Streamer: {streamer_name}
Platform: {platform}
Dominant emotion: {emotion or 'exciting'}
Transcript excerpt: {transcript[:500]}

Return ONLY this JSON (no markdown, no explanation):
{{
  "title": "catchy title under 100 chars with emojis, optimized for YouTube search",
  "description": "2-3 sentence description with 5 hashtags at the end",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "hook_text": "3-5 word bold hook for first 3 seconds overlay (e.g. 'HE ACTUALLY DID IT')",
  "thumbnail_prompt": "short punchy text for thumbnail overlay (e.g. 'INSANE PLAY')"
}}

Rules:
- Title MUST be under 100 characters, attention-grabbing, include 1-2 emojis
- Hook text is a BOLD overlay burned into the first 3 seconds — make it irresistible
- Tags should include streamer name, platform, and content-relevant terms
- Optimize everything for YouTube Shorts discovery and CTR
- Description must end with 5 relevant hashtags"""

        resp = requests.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 500,
                },
            },
            timeout=60,
        )
        resp.raise_for_status()

        response_text = resp.json().get("response", "").strip()

        # Parse JSON — handle potential markdown wrapping
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        # Find JSON object boundaries
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            response_text = response_text[start:end]

        data = json.loads(response_text)

        return SEOMetadata(
            title=data.get("title", f"{streamer_name} highlight")[:100],
            description=data.get("description", ""),
            tags=data.get("tags", [])[:15],
            hook_text=data.get("hook_text", "MUST WATCH")[:50],
            thumbnail_prompt=data.get("thumbnail_prompt", "INSANE")[:30],
            generated_by="ollama",
        )

    def _generate_template(
        self,
        streamer_name: str,
        emotion: str,
        platform: str,
    ) -> SEOMetadata:
        """Fallback: generate SEO using templates when Ollama is unavailable."""
        emotion_map = {
            "joy": {
                "titles": ["😂 FUNNIEST moment", "💀 I CAN'T BREATHE", "😭 THIS IS TOO FUNNY"],
                "hooks": ["YOU WON'T BELIEVE THIS", "I'M DYING 💀", "WAIT FOR IT"],
                "thumbs": ["HILARIOUS", "LMAOOO", "SO FUNNY"],
            },
            "anger": {
                "titles": ["😡 RAGE MOMENT", "🤬 LOST IT COMPLETELY", "💢 THE RAGE IS REAL"],
                "hooks": ["HE SNAPPED", "FULL RAGE MODE", "LOST IT"],
                "thumbs": ["RAGE QUIT", "SO MAD", "TILTED"],
            },
            "surprise": {
                "titles": ["😱 NO WAY THIS HAPPENED", "🤯 ABSOLUTELY INSANE", "😲 DID THAT JUST HAPPEN"],
                "hooks": ["WAIT WHAT?!", "NO WAY", "IMPOSSIBLE"],
                "thumbs": ["INSANE", "NO WAY", "CRAZY"],
            },
            "fear": {
                "titles": ["😨 TERRIFYING MOMENT", "💀 SCARIEST CLIP EVER", "😰 SO SCARY"],
                "hooks": ["DON'T LOOK AWAY", "SCARY AF", "TERRIFYING"],
                "thumbs": ["SCARY", "HORROR", "TERRIFYING"],
            },
        }

        emo = emotion_map.get(emotion, {
            "titles": ["🔥 MUST WATCH MOMENT", "💯 BEST CLIP TODAY", "⚡ INSANE HIGHLIGHT"],
            "hooks": ["WATCH THIS", "INSANE PLAY", "MUST SEE"],
            "thumbs": ["EPIC", "INSANE", "VIRAL"],
        })

        title = f"{random.choice(emo['titles'])} from {streamer_name}! #shorts"
        hook = random.choice(emo["hooks"])
        thumb = random.choice(emo["thumbs"])

        description = (
            f"Insane highlight from {streamer_name}'s {platform} stream! "
            f"Watch this {emotion or 'epic'} moment that had chat going crazy. "
            f"#shorts #{streamer_name.lower()} #{platform} #gaming #highlights"
        )

        tags = [
            streamer_name.lower(),
            platform,
            "shorts",
            "highlights",
            "clips",
            "gaming",
            "viral",
            "best moments",
            f"{streamer_name} clips",
            f"{platform} clips",
        ]

        return SEOMetadata(
            title=title[:100],
            description=description,
            tags=tags,
            hook_text=hook,
            thumbnail_prompt=thumb,
            generated_by="template",
        )
