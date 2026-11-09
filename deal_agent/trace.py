"""Append-only JSONL for every model, HTTP, storage and deterministic stage call."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def digest(value: str | bytes) -> str:
    return hashlib.sha256(
        value.encode() if isinstance(value, str) else value
    ).hexdigest()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Trace:
    def __init__(self, directory: Path, model: str | None, run_id: str | None = None):
        self.run_id = run_id or uuid4().hex
        self.model = model
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{self.run_id}.jsonl"

    def event(self, stage: str, inputs, outputs, latency_ms: float = 0, kind="stage"):
        record = dict(
            run_id=self.run_id,
            timestamp=stamp(),
            stage=stage,
            kind=kind,
            inputs=inputs,
            outputs=outputs,
            latency_ms=round(latency_ms, 3),
            model=self.model if kind == "llm" else None,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def call(self, stage, inputs, function, *, kind="tool", summarize=None):
        start = time.perf_counter()
        try:
            result = function()
        except Exception as exc:
            self.event(
                stage,
                inputs,
                {"error": str(exc), "error_type": type(exc).__name__},
                1000 * (time.perf_counter() - start),
                kind,
            )
            raise
        self.event(
            stage,
            inputs,
            summarize(result) if summarize else result,
            1000 * (time.perf_counter() - start),
            kind,
        )
        return result
