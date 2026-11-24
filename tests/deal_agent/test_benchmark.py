from copy import deepcopy
from types import SimpleNamespace

import pytest
import requests

from deal_agent.benchmark import comparison, preflight


def test_preflight_local_models_and_actionable_missing(runtime, monkeypatch):
    cfg = runtime[0]["deal_agent"]
    def get(session, url, **kwargs):
        assert session.trust_env is False and url.startswith("http://127.0.0.1:")
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"models": [{"name": "one:7b"}]})
    monkeypatch.setattr(requests.Session, "get", get)
    preflight(cfg, ["one:7b"])
    with pytest.raises(RuntimeError, match="ollama pull two:8b"):
        preflight(cfg, ["one:7b", "two:8b"])
    with pytest.raises(ValueError, match="local"):
        preflight(cfg, ["one-cloud"])


def test_preflight_unavailable_service_is_actionable(runtime, monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline fixture")
    monkeypatch.setattr(requests.Session, "get", fail)
    with pytest.raises(RuntimeError, match="ollama serve"):
        preflight(runtime[0]["deal_agent"], ["one:7b"])


def test_comparison_keeps_failure_unmeasured_and_rejects_unlike_corpora(tmp_path):
    base = {"manifest_sha256": "same", "exclude_uncertain": False,
            "extractor": "rules", "model": "original-rules", "metrics": {"edge_precision": .25},
            "status": "complete", "run_id": "fixture"}
    llm = {**base, "extractor": "llm", "model": "fixture-llm", "metrics": None, "status": "incomplete"}
    path = tmp_path / "comparison.md"
    comparison([base, llm], path)
    assert "| edge_precision | 25.0% | Not measured |" in path.read_text()
    other = deepcopy(llm)
    other["manifest_sha256"] = "different"
    with pytest.raises(ValueError, match="different gold"):
        comparison([base, other], path)
