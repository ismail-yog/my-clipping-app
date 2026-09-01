"""Dream Team — Base Agent
Thread-safe foundation class for all Dream Team agents.
Supports Ollama (primary), OpenAI (fallback), and Anthropic (fallback).
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from dream_team import config


class BaseAgent:
    """Base class for all Dream Team agents.

    Provides:
        - AI inference via Ollama / OpenAI / Anthropic
        - Thread-safe in-memory key-value memory
        - Tool registration and invocation
        - Per-agent file logging
        - API cost tracking
    """

    # ── Class-level cost tracker (shared across all agents) ──────────
    _total_cost: float = 0.0
    _cost_lock = threading.Lock()

    def __init__(self, name: str, description: str, agent_config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.description = description
        self.agent_config = agent_config or {}

        # Logger – per-agent log file
        self.logger = logging.getLogger(f"dreamteam.{self.name}")
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

        log_file = config.LOGS_DIR / f"agent_{self.name}.log"
        if not self.logger.handlers:
            fh = logging.FileHandler(str(log_file), encoding="utf-8")
            fh.setFormatter(
                logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
            )
            self.logger.addHandler(fh)

        # Thread-safe in-memory store
        self._memory: Dict[str, Any] = {}
        self._memory_lock = threading.Lock()

        # Registered tools
        self._tools: Dict[str, callable] = {}

        # Cost tracking
        self._agent_cost: float = 0.0

        self.logger.info("Agent '%s' initialised – %s", self.name, self.description)

    # ──────────────────────────────────────────────────────────────────
    # AI Inference
    # ──────────────────────────────────────────────────────────────────

    def think(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 512) -> str:
        """Send *prompt* to the configured LLM and return the response text.

        Tries providers in order: Ollama → OpenAI → Anthropic.
        """
        self.logger.info("think() called – prompt length %d chars", len(prompt))

        # 0. NVIDIA NIM (Nemotron 3 Ultra / Nemotron 3.5)
        if getattr(config, "USE_NVIDIA", False) and getattr(config, "NVIDIA_API_KEY", ""):
            result = self._call_nvidia_nim(prompt, temperature, max_tokens)
            if result is not None:
                return result

        # 1. Ollama
        if config.USE_OLLAMA:
            result = self._call_ollama(prompt, temperature, max_tokens)
            if result is not None:
                return result

        # 2. OpenAI
        if config.USE_OPENAI and config.OPENAI_API_KEY:
            result = self._call_openai(prompt, temperature, max_tokens)
            if result is not None:
                return result

        # 3. Anthropic
        if config.USE_ANTHROPIC and config.ANTHROPIC_API_KEY:
            result = self._call_anthropic(prompt, temperature, max_tokens)
            if result is not None:
                return result

        self.logger.error("All LLM providers failed for prompt.")
        return ""

    # ── NVIDIA NIM ───────────────────────────────────────────────────

    def _call_nvidia_nim(self, prompt: str, temperature: float, max_tokens: int) -> Optional[str]:
        """Call NVIDIA NIM / AI Foundation Cloud Endpoint."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        }
        models_to_try = [
            getattr(config, "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
            getattr(config, "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
            "meta/llama-3.2-11b-vision-instruct",
        ]

        import re
        for model in models_to_try:
            if not model:
                continue
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=config.AGENT_TIMEOUT_SECONDS)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        text = choices[0].get("message", {}).get("content", "").strip()
                        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
                        if text:
                            self._track_cost("nvidia_nim", model, len(prompt), len(text))
                            self.logger.info("NVIDIA NIM/%s responded – %d chars", model, len(text))
                            return text
                else:
                    self.logger.warning("NVIDIA NIM/%s returned HTTP %d: %s", model, resp.status_code, resp.text[:120])
            except Exception as exc:
                self.logger.warning("NVIDIA NIM/%s failed: %s", model, exc)

        return None

    # ── Ollama ───────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str, temperature: float, max_tokens: int) -> Optional[str]:
        """Call the local Ollama server."""
        url = f"{config.OLLAMA_HOST}/api/generate"
        models_to_try = [config.OLLAMA_MODEL, config.OLLAMA_FALLBACK_MODEL]

        for model in models_to_try:
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                }
                resp = requests.post(url, json=payload, timeout=config.AGENT_TIMEOUT_SECONDS)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("response", "").strip()
                if text:
                    self._track_cost("ollama", model, len(prompt), len(text))
                    self.logger.info("Ollama/%s responded – %d chars", model, len(text))
                    return text
            except Exception as exc:
                self.logger.warning("Ollama/%s failed: %s", model, exc)

        return None

    # ── OpenAI ───────────────────────────────────────────────────────

    def _call_openai(self, prompt: str, temperature: float, max_tokens: int) -> Optional[str]:
        """Call the OpenAI chat completions API."""
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=config.AGENT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            if text:
                self._track_cost("openai", config.OPENAI_MODEL, len(prompt), len(text))
                self.logger.info("OpenAI responded – %d chars", len(text))
                return text
        except Exception as exc:
            self.logger.warning("OpenAI failed: %s", exc)
        return None

    # ── Anthropic ────────────────────────────────────────────────────

    def _call_anthropic(self, prompt: str, temperature: float, max_tokens: int) -> Optional[str]:
        """Call the Anthropic messages API."""
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=config.AGENT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"].strip()
            if text:
                self._track_cost("anthropic", config.ANTHROPIC_MODEL, len(prompt), len(text))
                self.logger.info("Anthropic responded – %d chars", len(text))
                return text
        except Exception as exc:
            self.logger.warning("Anthropic failed: %s", exc)
        return None

    # ──────────────────────────────────────────────────────────────────
    # Memory (in-process key-value)
    # ──────────────────────────────────────────────────────────────────

    def remember(self, key: str, value: Any) -> None:
        """Store a value in the agent's in-memory store (thread-safe)."""
        with self._memory_lock:
            self._memory[key] = {"value": value, "timestamp": datetime.utcnow().isoformat()}
        self.logger.debug("remember(%s) stored", key)

    def recall(self, key: str) -> Optional[Any]:
        """Retrieve a value from the agent's in-memory store."""
        with self._memory_lock:
            entry = self._memory.get(key)
        if entry is None:
            self.logger.debug("recall(%s) – key not found", key)
            return None
        return entry["value"]

    # ──────────────────────────────────────────────────────────────────
    # Tool Registry
    # ──────────────────────────────────────────────────────────────────

    def register_tool(self, tool_name: str, func: callable) -> None:
        """Register a callable tool that the agent can invoke."""
        self._tools[tool_name] = func
        self.logger.debug("Tool registered: %s", tool_name)

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        """Invoke a registered tool by name."""
        if tool_name not in self._tools:
            self.logger.error("Tool '%s' not registered", tool_name)
            raise ValueError(f"Tool '{tool_name}' is not registered on agent '{self.name}'")
        self.logger.info("use_tool(%s) called with %s", tool_name, list(kwargs.keys()))
        try:
            result = self._tools[tool_name](**kwargs)
            self.logger.info("use_tool(%s) succeeded", tool_name)
            return result
        except Exception as exc:
            self.logger.error("use_tool(%s) failed: %s", tool_name, exc)
            raise

    # ──────────────────────────────────────────────────────────────────
    # Cost Tracking
    # ──────────────────────────────────────────────────────────────────

    def _track_cost(self, provider: str, model: str, input_chars: int, output_chars: int) -> None:
        """Estimate and accumulate API cost for an inference call.

        Rough heuristic: 4 chars ≈ 1 token.
        Pricing (per 1K tokens, approximate):
            Ollama – free (local)
            OpenAI gpt-4o-mini – $0.00015 input / $0.0006 output
            Anthropic haiku   – $0.00025 input / $0.00125 output
        """
        input_tokens = input_chars / 4
        output_tokens = output_chars / 4

        cost = 0.0
        if provider == "openai":
            cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
        elif provider == "anthropic":
            cost = (input_tokens / 1000) * 0.00025 + (output_tokens / 1000) * 0.00125
        # Ollama is free

        with BaseAgent._cost_lock:
            BaseAgent._total_cost += cost
            self._agent_cost += cost

        if config.COST_TRACKING_ENABLED:
            self.logger.info(
                "Cost [%s/%s]: $%.6f (agent total: $%.4f, global total: $%.4f)",
                provider, model, cost, self._agent_cost, BaseAgent._total_cost,
            )

        # Budget guard
        if config.MAX_DAILY_API_COST and BaseAgent._total_cost >= config.MAX_DAILY_API_COST:
            self.logger.warning(
                "⚠️  Daily API cost limit ($%.2f) reached! Total: $%.4f",
                config.MAX_DAILY_API_COST, BaseAgent._total_cost,
            )

    @classmethod
    def get_total_cost(cls) -> float:
        """Return the cumulative cost across all agents."""
        with cls._cost_lock:
            return cls._total_cost

    @classmethod
    def reset_cost(cls) -> None:
        """Reset the global cost counter (e.g. at start of day)."""
        with cls._cost_lock:
            cls._total_cost = 0.0

    # ──────────────────────────────────────────────────────────────────
    # Representation
    # ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<Agent:{self.name} tools={list(self._tools.keys())} cost=${self._agent_cost:.4f}>"
