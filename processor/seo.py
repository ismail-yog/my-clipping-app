"""
StreamClipper — SEO Generator
Generates YouTube Shorts metadata (titles, descriptions, tags, hooks, thumbnail text)
using a local Ollama instance or static templates as fallback.
"""

import json
import logging
from typing import Optional
from dataclasses import dataclass, field

import requests

import config

logger = logging.getLogger("streamclipper.processor.seo")


@dataclass
class SEOMetadata:
    """SEO and thumbnail overlay metadata for a video clip."""
    title: str
    description: str
    tags: list[str]
    hook_text: str  # 3-second opening text overlay
    thumbnail_prompt: str  # Text overlay for thumbnail
    generated_by: str  # "ollama" or "template"


class SEOGenerator:
    """Generates viral, search-optimized video metadata."""

    def __init__(self):
        self.ollama_host = getattr(config, "OLLAMA_HOST", "http://localhost:11434")
        self.model = getattr(config, "OLLAMA_MODEL", "llama3")
        self.fallback_model = getattr(config, "OLLAMA_FALLBACK_MODEL", "mistral")

    def generate(self, transcript: str, streamer_name: str, emotion: str, platform: str) -> SEOMetadata:
        """Generate metadata using primary Ollama model, fallback model, or templates."""
        prompt = self._build_prompt(transcript, streamer_name, emotion, platform)

        # 1. Try primary Ollama model
        try:
            logger.info("Requesting SEO metadata from primary model: %s", self.model)
            response = self._call_ollama(prompt, self.model)
            if response:
                meta = self._parse_response(response)
                if meta:
                    return meta
        except Exception as e:
            logger.warning("Primary Ollama model (%s) failed: %s", self.model, e)

        # 2. Try fallback Ollama model
        try:
            logger.info("Requesting SEO metadata from fallback model: %s", self.fallback_model)
            response = self._call_ollama(prompt, self.fallback_model)
            if response:
                meta = self._parse_response(response)
                if meta:
                    return meta
        except Exception as e:
            logger.warning("Fallback Ollama model (%s) failed: %s", self.fallback_model, e)

        # 3. Fallback to static template-based generation
        logger.info("Ollama unavailable or failed — falling back to template-based SEO")
        return self._template_generate(transcript, streamer_name, emotion)

    def _call_ollama(self, prompt: str, model: str) -> Optional[str]:
        """Execute HTTP POST call to the local Ollama api/generate endpoint."""
        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("response")
        except Exception as e:
            logger.debug("Ollama request failed for model %s: %s", model, e)
        return None

    def _build_prompt(self, transcript: str, streamer_name: str, emotion: str, platform: str) -> str:
        """Engineer viral prompt requesting JSON schema matching SEOMetadata."""
        return f"""You are a YouTube Shorts and TikTok viral marketing expert. 
Generate metadata for a highlight clip using these details:
- Streamer Name: {streamer_name}
- Stream Platform: {platform}
- Dominant Emotion: {emotion or 'exciting'}
- Transcript: "{transcript[:500]}"

You must generate optimized metadata using viral clickbait formulas, such as:
1. "INSANE {{action}} by {streamer_name}!"
2. "{streamer_name} just {{action}} and chat went WILD"
3. "This is the funniest moment EVER"

Your output MUST be a single raw JSON object matching the schema below. Do not include markdown blocks (like ```json), introduction, or commentary.

JSON Output Schema:
{{
  "title": "A clickbait title under 80 characters (with 1-2 emojis, e.g., 'INSANE clutch by {streamer_name}! 😱')",
  "description": "A 2-sentence description containing the streamer name, summary of what happened, and 5 viral hashtags.",
  "tags": ["array", "of", "5-8", "short", "lowercase", "keywords", "including", "streamer", "name"],
  "hook_text": "Irresistible 3-second opening text overlay (under 30 characters, e.g. 'HE DID WHAT?!')",
  "thumbnail_prompt": "Punchy 1-2 word text overlay for the thumbnail (e.g. 'UNBELIEVABLE')"
}}

Constraints:
- title length <= 80 characters
- hook_text length <= 30 characters
- tags list size must be between 5 and 8 elements
"""

    def _parse_response(self, response: str) -> Optional[SEOMetadata]:
        """Robustly parse JSON object from LLM generation response string."""
        try:
            cleaned = response.strip()
            
            # Remove potential markdown block wraps
            if "```" in cleaned:
                blocks = cleaned.split("```")
                for block in blocks:
                    block_clean = block.strip()
                    if block_clean.startswith("json"):
                        block_clean = block_clean[4:].strip()
                    if block_clean.startswith("{") and block_clean.endswith("}"):
                        cleaned = block_clean
                        break
            
            # Find boundaries of the JSON object
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = cleaned[start:end]
                data = json.loads(json_str)
                
                # Apply length constraints safely
                title = data.get("title", "")[:80]
                description = data.get("description", "")
                tags = [str(t).lower() for t in data.get("tags", [])][:8]
                hook_text = data.get("hook_text", "")[:30]
                thumbnail_prompt = data.get("thumbnail_prompt", "")[:30]
                
                return SEOMetadata(
                    title=title,
                    description=description,
                    tags=tags,
                    hook_text=hook_text,
                    thumbnail_prompt=thumbnail_prompt,
                    generated_by="ollama"
                )
        except Exception as e:
            logger.error("Failed to parse JSON response from Ollama: %s", e)
        return None

    def _template_generate(self, transcript: str, streamer_name: str, emotion: str) -> SEOMetadata:
        """Static template generator used as fallback if Ollama model calls fail."""
        emo_str = emotion or "epic"
        title = f"{emo_str.upper()} moment from {streamer_name}!"
        description = transcript[:200] + "..." if transcript else f"Epic highlight moment featuring {streamer_name}!"
        tags = [streamer_name.lower(), "twitch", "funny", "viral", "clip", emo_str.lower(), "highlights", "gaming"]
        hook_text = "WATCH THIS 👀"
        thumbnail_prompt = f"{streamer_name} REACTS"

        return SEOMetadata(
            title=title[:80],
            description=description,
            tags=tags,
            hook_text=hook_text[:30],
            thumbnail_prompt=thumbnail_prompt[:30],
            generated_by="template"
        )
