"""
StreamClipper — SEO Generator
Generates YouTube Shorts metadata (titles, descriptions, tags, hooks, thumbnail text)
using a local Ollama instance or static templates as fallback.
"""

import os
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
    """Generates viral, search-optimized video metadata using NVIDIA NIMs, Ollama, or templates."""

    def __init__(self):
        self.nvidia_api_key = getattr(config, "NVIDIA_API_KEY", "") or os.environ.get("NVIDIA_API_KEY", "")
        self.nvidia_model = getattr(config, "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
        self.nvidia_fallback_model = getattr(config, "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.ollama_host = getattr(config, "OLLAMA_HOST", "http://localhost:11434")
        self.model = getattr(config, "OLLAMA_MODEL", "llama3")
        self.fallback_model = getattr(config, "OLLAMA_FALLBACK_MODEL", "mistral")

    def generate(self, transcript: str, streamer_name: str, emotion: str, platform: str) -> SEOMetadata:
        """Generate metadata using NVIDIA NIM Blueprint API, Ollama, or templates."""
        prompt = self._build_prompt(transcript, streamer_name, emotion, platform)

        # 0. Try NVIDIA NIM Cloud Endpoint (Nemotron 3 Ultra / Nemotron 3.5 / Llama 3.2)
        if self.nvidia_api_key:
            for n_model in [self.nvidia_model, self.nvidia_fallback_model, "meta/llama-3.2-11b-vision-instruct"]:
                if not n_model:
                    continue
                try:
                    logger.info("Requesting SEO metadata from NVIDIA NIM model: %s", n_model)
                    response = self._call_nvidia_nim(prompt, n_model)
                    if response:
                        meta = self._parse_response(response)
                        if meta:
                            meta.generated_by = f"nvidia_nim:{n_model}"
                            return meta
                except Exception as e:
                    logger.warning("NVIDIA NIM call (%s) failed: %s", n_model, e)

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
        logger.info("NVIDIA NIM / Ollama unavailable — falling back to template-based SEO")
        return self._template_generate(transcript, streamer_name, emotion)

    def _call_nvidia_nim(self, prompt: str, model: str) -> Optional[str]:
        """Execute HTTP POST request to NVIDIA NIM / AI Foundation OpenAPI endpoint."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.nvidia_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 1024,
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                json_data = resp.json()
                choices = json_data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            else:
                logger.error("NVIDIA NIM request failed with HTTP %d: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.error("NVIDIA NIM request exception: %s", e)
        return None

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
        import re
        try:
            cleaned = response.strip()
            # Remove thinking/reasoning tags if present
            cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
            
            data = None
            # 1. Try markdown code block matches
            code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
            if code_blocks:
                for block in reversed(code_blocks):
                    try:
                        data = json.loads(block)
                        if isinstance(data, dict) and "title" in data:
                            break
                    except Exception:
                        data = None

            # 2. Try raw_decode iteratively
            if not data:
                decoder = json.JSONDecoder()
                pos = 0
                while pos < len(cleaned):
                    start = cleaned.find("{", pos)
                    if start == -1:
                        break
                    try:
                        obj, idx = decoder.raw_decode(cleaned[start:])
                        if isinstance(obj, dict) and ("title" in obj or "description" in obj):
                            data = obj
                            break
                        pos = start + 1
                    except Exception:
                        pos = start + 1

            # 3. Fallback to outermost braces
            if not data:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(cleaned[start:end])

            if isinstance(data, dict):
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
                    generated_by="nvidia_nim"
                )
        except Exception as e:
            logger.error("Failed to parse JSON response from LLM: %s", e)
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
