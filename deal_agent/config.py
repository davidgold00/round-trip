"""Load paths, prompts, models and extraction constraints from project YAML.
The CLI supplies the configuration path; defaults resolve beside that file.
Return validated loopback and chunk settings to the agent components.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent


PROMPT_VERSIONS = ("v1", "v2", "roles", "span", "roles-span")


def prompt_templates(version):
    """Assemble effective stage templates so reports hash precisely what ran."""
    if version not in PROMPT_VERSIONS:
        raise ValueError(f"Unknown prompt_version: {version}")
    directory = ROOT / "deal_agent/prompts"
    base = version if version in ("v1", "v2") else "v1"
    templates = {stage: (directory / base / f"{stage}.txt").read_text()
                 for stage in ("triage", "extract", "retry")}
    if version != base:
        additions = [(directory / f"{part}.txt").read_text().strip()
                     for part in version.split("-")]
        templates["extract"] = templates["extract"].replace(
            "<document>", "\n".join(additions) + "\n<document>")
    return templates


def load(path: Path | None = None) -> dict:
    path = (path or ROOT / "config.yaml").resolve()
    cfg = yaml.safe_load(path.read_text())
    cfg["_root"] = path.parent
    agent = cfg["deal_agent"]
    agent.setdefault("prompt_version", "v1")
    if agent["prompt_version"] not in PROMPT_VERSIONS:
        raise ValueError("Unknown prompt_version")
    if not 0 < float(cfg["sec"]["max_requests_per_second"]) <= 10:
        raise ValueError("SEC max_requests_per_second must be in (0, 10]")
    if float(agent["polite_delay_seconds"]) < 0.1:
        raise ValueError("polite_delay_seconds must be at least 0.1")
    if not 0 <= agent["chunk_overlap"] < agent["chunk_chars"]:
        raise ValueError("chunk_overlap must be smaller than chunk_chars")
    host = urlparse(agent["ollama_url"])
    if host.scheme != "http" or host.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Ollama must use a local loopback HTTP endpoint")
    if ":cloud" in agent["model"].lower() or "-cloud" in agent["model"].lower():
        raise ValueError("Choose a downloaded local Ollama model, not a cloud model")
    return cfg


def path_for(cfg: dict, key: str) -> Path:
    return cfg["_root"] / cfg["deal_agent"][key]
