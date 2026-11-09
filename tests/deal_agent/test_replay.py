import json

import pytest

from deal_agent.config import ROOT
from deal_agent.pipeline import Pipeline
from deal_agent.provider import Replay, Recorder
from deal_agent.evaluate import evaluate

IDS = {"microsoft_openai_2019", "nvidia_openai_2025"}


def documents():
    return [d for d in json.loads((ROOT / "eval/gold/manifest.json").read_text())["documents"] if d["id"] in IDS]


def seed(cfg, store):
    for item in documents():
        text = (ROOT / "eval/gold" / item["text_file"]).read_text()
        meta = {k: item[k] for k in ("source_url", "company", "published_date", "doc_type")}
        ident, _ = store.save_document(meta, text.encode(), text, cfg["_root"] / "raw")
        # Stable fixture metadata makes prompt hashes portable across machines.
        store.db.execute("UPDATE documents SET meta=? WHERE id=?", (json.dumps(meta), ident))


def test_synthetic_cassette_full_pipeline_and_retry(runtime):
    cfg, store, trace, _ = runtime
    seed(cfg, store)
    provider = Replay(cfg["deal_agent"], ROOT / "tests/fixtures/deal_agent/synthetic-cassette.json", trace)
    pipe = Pipeline(cfg, store, trace, provider)
    graph = (cfg["_root"] / "ledger/edges.csv").read_bytes()
    result = pipe.run_documents()
    assert result["candidates_proposed"] == 2
    assert result["verification_pass_rate"] == 1
    assert provider.position == 5
    assert all(c["status"] == "pending" for c in store.candidates())
    assert any(c["verification"]["history"].get("original_failure") for c in store.candidates())
    assert pipe.run_documents()["candidates_proposed"] == 0
    assert provider.position == 5
    assert (cfg["_root"] / "ledger/edges.csv").read_bytes() == graph


def test_replay_request_mismatch_has_no_fallback(runtime):
    cfg, _, trace, _ = runtime
    provider = Replay(cfg["deal_agent"], ROOT / "tests/fixtures/deal_agent/synthetic-cassette.json", trace)
    with pytest.raises(RuntimeError, match="mismatch"):
        provider.generate("changed input", {}, "triage")


def test_record_response_and_failure_roundtrip(runtime, tmp_path):
    cfg, _, trace, factory = runtime
    fake = factory(["response", RuntimeError("failed")]).provider
    # A live provider's model must match its request configuration.
    cfg["deal_agent"]["model"] = fake.model
    path = tmp_path / "cassette.json"
    recorded = Recorder(fake, cfg["deal_agent"], path, synthetic=True)
    assert recorded.generate("one", {}, "extract") == "response"
    with pytest.raises(RuntimeError, match="failed"):
        recorded.generate("two", {}, "extract")
    replay = Replay(cfg["deal_agent"], path, trace)
    assert replay.generate("one", {}, "extract") == "response"
    with pytest.raises(RuntimeError, match="failed"):
        replay.generate("two", {}, "extract")
    with pytest.raises(RuntimeError, match="exhausted"):
        replay.generate("three", {}, "extract")
    with pytest.raises(ValueError, match="already exists"):
        Recorder(fake, cfg["deal_agent"], path)


def test_synthetic_results_cannot_be_model_metrics(runtime, tmp_path):
    pipe = runtime[3]([RuntimeError("fixture input")]*50)
    pipe.provider.synthetic = True
    report = evaluate(pipe, ROOT / "eval/gold", tmp_path / "synthetic.md")
    assert report["synthetic"] and report["metrics"] is None
