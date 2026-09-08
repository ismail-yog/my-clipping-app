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
from processor.censor import censor_text

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
                        meta = self._parse_response(response, streamer_name=streamer_name, transcript=transcript, emotion=emotion)
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
                meta = self._parse_response(response, streamer_name=streamer_name, transcript=transcript, emotion=emotion)
                if meta:
                    meta.generated_by = f"ollama:{self.model}"
                    return meta
        except Exception as e:
            logger.warning("Primary Ollama model (%s) failed: %s", self.model, e)

        # 2. Try fallback Ollama model
        if self.fallback_model and self.fallback_model != self.model:
            try:
                logger.info("Requesting SEO metadata from fallback model: %s", self.fallback_model)
                response = self._call_ollama(prompt, self.fallback_model)
                if response:
                    meta = self._parse_response(response, streamer_name=streamer_name, transcript=transcript, emotion=emotion)
                    if meta:
                        meta.generated_by = f"ollama:{self.fallback_model}"
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

    def _get_ai_settings(self) -> dict:
        """Fetch custom prompt and description templates from settings.json."""
        settings_file = config.BASE_DIR / "settings.json"
        if settings_file.exists():
            try:
                return json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read settings.json for AI settings: %s", e)
        return {}

    def _build_prompt(self, transcript: str, streamer_name: str, emotion: str, platform: str) -> str:
        """Engineer viral Gen-Z short-form prompt requesting JSON schema matching SEOMetadata."""
        ai_cfg = self._get_ai_settings()
        custom_prompt = ai_cfg.get("ai_custom_prompt", "").strip()
        desc_template = ai_cfg.get("ai_description_template", "").strip()

        custom_prompt_section = ""
        if custom_prompt:
            custom_prompt_section = f"""
Additional Custom Creator Directives & Persona:
{custom_prompt}
(CRITICAL: Adhere to the custom creator directives above while preserving the JSON output schema.)
"""

        desc_instruction = "2-sentence summary of the moment with 5 viral TikTok hashtags #fyp #streamer #gaming #viral #clutch"
        if desc_template:
            desc_instruction = f"Format description conforming to this template: {desc_template}"

        return f"""You are a top-tier TikTok / YouTube Shorts viral clip editor specializing in Gen-Z retention formulas.
Generate metadata for a short-form video clip using these details:
- Streamer / Creator: {streamer_name}
- Dominant Emotion: {emotion or 'hype'}
- Speech Transcript: "{transcript[:600]}"
{custom_prompt_section}
Rules for Title & Hook:
1. Use authentic Gen-Z / TikTok phrasing (lowercase lowercase or lowercase with emojis: e.g. "bro thought he was him 💀", "ain't no way he said that 😭", "nah chat is cooking him rn", "he really sold the bag 💀").
2. Reference what was actually spoken in the transcript in quotes when applicable (e.g. bro really said "..." 💀).
3. NEVER use generic 2012 words like "EPIC MELTDOWN", "MIND BLOWN", "UNBELIEVABLE", "CRAZY REACTION". Keep it raw, hilarious, and punchy.

Output MUST be a single raw JSON object matching the schema below:
{{
  "title": "Viral Gen-Z title under 75 chars with 1 emoji (e.g. bro thought he was him 💀)",
  "description": "{desc_instruction}",
  "tags": ["{streamer_name.lower()}", "gaming", "streamer", "viral", "fyp", "shorts", "tiktok"],
  "hook_text": "High-retention streamer headline hook between 40-80 chars with 1-2 emojis (e.g. {streamer_name} was HYPED that DDG is back on YT but says he isn't DUB 😭💀)",
  "thumbnail_prompt": "1-2 punchy words (e.g. NO WAY)"
}}
"""

    def _format_description_template(
        self,
        template: str,
        streamer_name: str,
        title: str,
        summary: str,
        tags: list[str],
        emotion: str,
        transcript: str
    ) -> str:
        """Hydrate description template placeholders."""
        tags_hash = " ".join([f"#{t.replace(' ', '')}" for t in tags[:5]]) if tags else "#Shorts #gaming #viral"
        rendered = template
        replacements = {
            "{streamer}": streamer_name,
            "{title}": title,
            "{summary}": summary or title,
            "{hashtags}": tags_hash,
            "{emotion}": emotion or "hype",
            "{transcript}": transcript[:250],
        }
        for k, v in replacements.items():
            rendered = rendered.replace(k, v)
        return rendered.strip()

    def _parse_response(
        self,
        response: str,
        streamer_name: str = "",
        transcript: str = "",
        emotion: str = ""
    ) -> Optional[SEOMetadata]:
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
                hook_text = data.get("hook_text", "")[:85]
                thumbnail_prompt = data.get("thumbnail_prompt", "")[:30]

                # Check if custom description template is active and hydrate if placeholders present
                ai_cfg = self._get_ai_settings()
                desc_template = ai_cfg.get("ai_description_template", "").strip()
                if desc_template and ("{" in desc_template and "}" in desc_template):
                    summary = description.split("\n")[0] if description else title
                    description = self._format_description_template(
                        template=desc_template,
                        streamer_name=streamer_name,
                        title=title,
                        summary=summary,
                        tags=tags,
                        emotion=emotion,
                        transcript=transcript
                    )
                
                return SEOMetadata(
                    title=censor_text(title),
                    description=censor_text(description),
                    tags=tags,
                    hook_text=censor_text(hook_text),
                    thumbnail_prompt=censor_text(thumbnail_prompt),
                    generated_by="nvidia_nim"
                )
        except Exception as e:
            logger.error("Failed to parse JSON response from LLM: %s", e)
        return None

    def _template_generate(self, transcript: str, streamer_name: str, emotion: str) -> SEOMetadata:
        """Authentic Gen-Z title and metadata generator when LLM is unavailable."""
        import random
        words = [w for w in transcript.strip().split() if w]
        snippet = " ".join(words[:6]).strip('",.?!')
        streamer_display = streamer_name or "Bro"
        
        if len(words) >= 3 and len(snippet) > 6:
            snip_lower = snippet.lower()
            snip_upper = snippet.upper()
            if "i " in snip_lower or "my " in snip_lower or "me " in snip_lower:
                title = f"bro really said \"{snip_lower}\" 💀"
            elif emotion in ("surprise", "fear"):
                title = f"ain't no way {snip_lower} 😭"
            elif emotion in ("anger", "rage"):
                title = f"nah he actually lost it over this 💀"
            elif emotion in ("joy", "win"):
                title = f"bro thought he was him 👑"
            else:
                title = f"wait till the end... \"{snip_lower}\" 💀"

            hook_options = [
                f"{streamer_display} was HYPED that {snip_upper} but chat said NO 😭💀",
                f"NO SHOT {streamer_display} REALLY SAID \"{snip_upper}\" 💀🔥",
                f"chat is COOKING {streamer_display} over this 😭💀",
                f"{streamer_display} CAUGHT IN 4K SAYING THIS 😭💀",
            ]
        else:
            fallbacks = [
                f"bro thought he was him 💀",
                f"ain't no way {streamer_display} did this 😭",
                f"nah chat is cooking him rn 💀",
                f"bro sold the bag so fast 😭",
                f"he was NOT ready for this 💀",
                f"wait till the ending bro i'm crying 😭",
            ]
            title = random.choice(fallbacks)
            hook_options = [
                f"{streamer_display} was HYPED on stream but chat wasn't having it 😭💀",
                f"NO SHOT {streamer_display} REALLY SAID THIS ON STREAM 💀🔥",
                f"chat is COOKING {streamer_display} right now 😭💀",
                f"BRO REALLY THOUGHT HE WAS HIM 😭💀",
            ]

        hook_text = random.choice(hook_options)
        tags = [streamer_name.lower(), "fyp", "shorts", "viral", "tiktok", "gaming", "funny"]
        thumbnail_prompt = "NO WAY"

        ai_cfg = self._get_ai_settings()
        desc_template = ai_cfg.get("ai_description_template", "").strip()
        if desc_template and ("{" in desc_template and "}" in desc_template):
            description = self._format_description_template(
                template=desc_template,
                streamer_name=streamer_name,
                title=title,
                summary=title,
                tags=tags,
                emotion=emotion,
                transcript=transcript
            )
        else:
            description = f"{title}\n\nClip from {streamer_name}. #fyp #shorts #viral #gaming #twitch"

        return SEOMetadata(
            title=censor_text(title[:80]),
            description=censor_text(description),
            tags=tags,
            hook_text=censor_text(hook_text[:85]),
            thumbnail_prompt=censor_text(thumbnail_prompt[:30]),
            generated_by="genz_template"
        )
