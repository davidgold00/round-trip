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
        self.last_response = None
        self.session = requests.Session()
        self.session.trust_env = False  # local source text must not go through a proxy

    def generate(self, prompt: str, schema: dict, stage: str) -> str:
        self.last_response = None
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
            self.last_response = data
            if data.get("error") or not data.get("done") or "response" not in data:
                raise RuntimeError(f"Incomplete Ollama response: {data}")
            return data["response"]

        return self.trace.call(stage, payload, call, kind="llm")


def request_payload(cfg, prompt, schema, stage):
    """Exact generation inputs, including options that can change a replay."""
    return {
        "stage": stage, "model": cfg["model"], "prompt": prompt,
        "format": schema, "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": cfg["num_ctx"]},
    }


class Recorder:
    """Record every request, raw Ollama response and failure; never overwrite."""
    mode = "record"

    def __init__(self, provider, cfg, path, *, synthetic=False):
        from pathlib import Path
        self.provider, self.cfg, self.path = provider, dict(cfg), Path(path)
        self.model, self.synthetic = provider.model, synthetic
        if self.path.exists():
            raise ValueError(f"Cassette already exists: {self.path}. Choose a new path.")
        self.data = {"version": 1, "synthetic": synthetic, "model": self.model,
                     "description": "Synthetic test data, not model output" if synthetic else "Live local Ollama requests and responses",
                     "calls": []}

    def generate(self, prompt, schema, stage):
        import json
        from .io import atomic_write
        from .store import encode
        from .trace import digest
        request = request_payload(self.cfg, prompt, schema, stage)
        entry = {"request": request, "request_sha256": digest(encode(request))}
        try:
            response = self.provider.generate(prompt, schema, stage)
            entry["response"] = response
            return response
        except Exception as exc:
            entry["error"] = str(exc)
            raise
        finally:
            entry["ollama_response"] = getattr(self.provider, "last_response", None)
            self.data["calls"].append(entry)
            atomic_write(self.path, json.dumps(self.data, indent=2) + "\n")


class Replay:
    """Strict offline playback; a miss never contacts Ollama or another service."""
    mode = "replay"

    def __init__(self, cfg, path, trace):
        import json
        from pathlib import Path
        from .trace import digest
        self.cfg, self.trace = dict(cfg), trace
        self.path = Path(path)
        self.data = json.loads(self.path.read_text())
        if self.data.get("version") != 1 or type(self.data.get("synthetic")) is not bool:
            raise ValueError("Unsupported cassette or missing synthetic provenance flag")
        self.model = self.data["model"]
        self.synthetic = self.data["synthetic"]
        self.cassette_sha256 = digest(self.path.read_bytes())
        if self.model != cfg["model"]:
            raise ValueError("Cassette model does not match configured model")
        self.position = 0

    def generate(self, prompt, schema, stage):
        from .store import encode
        from .trace import digest
        request = request_payload(self.cfg, prompt, schema, stage)
        calls = self.data["calls"]
        if self.position >= len(calls):
            raise RuntimeError("Replay cassette exhausted; no network fallback")
        entry = calls[self.position]
        if digest(encode(request)) != entry["request_sha256"]:
            raise RuntimeError(f"Replay request mismatch at call {self.position} ({stage})")
        if "request" in entry and entry["request"] != request:
            raise RuntimeError("Cassette request hash/content mismatch")
        self.position += 1
        self.trace.event(stage, request, entry, kind="replay")
        if "error" in entry:
            raise RuntimeError(entry["error"])
        return entry["response"]


def make_provider(cfg, trace, mode="ollama", cassette=None):
    if mode in {"record", "replay"} and cassette is None:
        raise ValueError("--cassette is required for recording or replay")
    if mode == "replay":
        return Replay(cfg, cassette, trace)
    live = Ollama(cfg, trace)
    return Recorder(live, cfg, cassette) if mode == "record" else live
