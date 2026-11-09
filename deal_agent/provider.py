"""The only implemented LLM backend: downloaded models on local Ollama."""

from __future__ import annotations

from typing import Protocol

import requests

from .trace import Trace


class Provider(Protocol):
    model: str

    def generate(self, prompt: str, schema: dict, stage: str) -> str: ...


class Ollama:
    def __init__(self, cfg: dict, trace: Trace):
        self.model = cfg["model"]
        self.url = cfg["ollama_url"].rstrip("/") + "/api/generate"
        self.timeout = cfg["llm_timeout_seconds"]
        self.num_ctx = cfg["num_ctx"]
        self.trace = trace
        self.session = requests.Session()
        self.session.trust_env = False  # local source text must not go through a proxy

    def generate(self, prompt: str, schema: dict, stage: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "seed": 42, "num_ctx": self.num_ctx},
        }

        def call():
            try:
                response = self.session.post(
                    self.url, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise RuntimeError(
                    "Local Ollama unavailable. Run `ollama serve`, then pull the configured "
                    f"model ({self.model}). No remote fallback is used. {exc}"
                ) from exc
            data = response.json()
            if data.get("error") or not data.get("done") or "response" not in data:
                raise RuntimeError(f"Incomplete Ollama response: {data}")
            return data["response"]

        return self.trace.call(stage, payload, call, kind="llm")
