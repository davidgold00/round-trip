import json
from pathlib import Path
import subprocess

import pytest

from deal_agent.config import ROOT, load
from deal_agent.evaluate import evaluate
from deal_agent.models import Extraction
from deal_agent.benchmark import benchmark
from deal_agent.trace import digest


def test_v1_unchanged_and_default_v2_has_distinct_prompt(runtime):
    cfg, _, _, factory = runtime
    assert load()["deal_agent"]["prompt_version"] == "v1"
    for name in ("triage", "extract", "retry"):
        original=subprocess.check_output(["git","show",f"8a5fadcd7a02a3eda983bdbbf45a84d504f9ca77:deal_agent/prompts/v1/{name}.txt"],cwd=ROOT)
        assert (ROOT / f"deal_agent/prompts/v1/{name}.txt").read_bytes() == original
    first=factory().prompt("extract", Extraction, "source", {"source_url":"https://source.test"})
    cfg["deal_agent"]["prompt_version"] = "v2"
    second=factory().prompt("extract", Extraction, "source", {"source_url":"https://source.test"})
    assert first != second and "government penalties" not in first
    assert "fines" in second and "multi-party" in second


def test_invalid_prompt_version_rejected_before_provider(tmp_path):
    path=tmp_path/"config.yaml"
    path.write_text((ROOT/"config.yaml").read_text().replace("prompt_version: v1", "prompt_version: ../v1"))
    with pytest.raises(ValueError, match="prompt_version"):
        load(path)


def test_eval_hashes_selected_prompt_version(runtime, tmp_path):
    cfg, _, _, factory=runtime
    cfg["deal_agent"]["prompt_version"]="v2"
    report=evaluate(factory(), ROOT/"eval/gold", tmp_path/"v2.md", validate_only=True)
    assert report["prompt_version"] == "v2" and report["metrics"] is None
    assert report["prompt_hashes"]["extract.txt"] == digest((ROOT/"deal_agent/prompts/v2/extract.txt").read_bytes())


def test_benchmark_model_prompt_cross_product_isolated(runtime, tmp_path, monkeypatch):
    cfg, _, _, factory=runtime
    seen=[];providers=[]
    monkeypatch.setattr("deal_agent.benchmark.preflight", lambda *args:None)
    def provider(agent, trace, mode, cassette):
        providers.append((mode,str(cassette)))
        return factory().provider
    monkeypatch.setattr("deal_agent.benchmark.make_provider",provider)
    def fake_evaluate(pipe, directory, output, **kwargs):
        seen.append((kwargs["extractor"],pipe.agent["model"],pipe.agent["prompt_version"]))
        return {"extractor":kwargs["extractor"], "model":pipe.agent["model"],
                "prompt_version":pipe.agent["prompt_version"],"manifest_sha256":"test-only",
                "exclude_uncertain":False,"metrics":None,"status":"complete",
                "label_failures":[],"run_id":"synthetic orchestration test"}
    monkeypatch.setattr("deal_agent.benchmark.evaluate", fake_evaluate)
    output=tmp_path/"comparison.md"
    assert benchmark(cfg,models=["one:7b","two:8b"],prompt_versions=["v1","v2"],output=output) == 0
    assert seen == [("rules","one:7b","v1"),("llm","one:7b","v1"),("llm","one:7b","v2"),("llm","two:8b","v1"),("llm","two:8b","v2")]
    assert len({path for mode,path in providers if mode=="record"}) == 4
    assert cfg["deal_agent"]["model"] != "one:7b" and cfg["deal_agent"]["prompt_version"] == "v1"
    assert len(json.loads(output.with_suffix('.json').read_text())["reports"]) == 5
