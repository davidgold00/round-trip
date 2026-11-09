import json
from pathlib import Path

import pytest

from deal_agent.pipeline import chunks


def save(store, cfg, deal, text=None):
    text = text or deal["evidence_quote"]
    meta = {
        "source_url": deal["source_url"],
        "company": "Nvidia",
        "published_date": "2025-09-22",
        "doc_type": "company_release",
        "evidence_tier": "T2",
        "accession_no": "",
    }
    store.job(meta["source_url"], "document", meta)
    return store.save_document(meta, text.encode(), text, cfg["_root"] / "raw")[0]


def test_twice_no_new_candidates_or_model_calls_and_graph_untouched(runtime, deal_dict):
    cfg, store, trace, factory = runtime
    pipe = factory([{"relevant": True, "reason": "Investment"}, {"edges": [deal_dict]}])
    save(store, cfg, deal_dict)
    graph = (cfg["_root"] / "ledger/edges.csv").read_bytes()
    first = pipe.run_documents()
    assert first["candidates_proposed"] == 1
    assert first["verification_pass_rate"] == 1
    assert len(pipe.provider.calls) == 2
    assert pipe.run_documents()["candidates_proposed"] == 0
    assert len(pipe.provider.calls) == 2
    assert (cfg["_root"] / "ledger/edges.csv").read_bytes() == graph
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert {"triage.keyword", "triage.decision", "verify", "reconcile", "propose"} <= {
        e["stage"] for e in events
    }
    assert all(
        {"run_id", "stage", "inputs", "outputs", "latency_ms", "model"} <= e.keys()
        for e in events
    )


def test_failed_evidence_is_queued_even_if_retry_returns_empty(runtime, deal_dict):
    cfg, store, trace, factory = runtime
    bad = {
        **deal_dict,
        "evidence_quote": "NVIDIA invested $1 billion in OpenAI. Invented extra words.",
    }
    pipe = factory(
        [{"relevant": True, "reason": "investment"}, {"edges": [bad]}, {"edges": []}]
    )
    save(store, cfg, deal_dict)
    result = pipe.run_documents()
    assert len(pipe.provider.calls) == 3
    assert result["candidates_proposed"] == 1
    candidate = store.candidates()[0]
    assert not candidate["verification"]["passed"]
    assert candidate["verification"]["history"]["retry"]["error"]
    assert result["verification_pass_rate"] == 0


def test_repair_retains_original_failure(runtime, deal_dict):
    cfg, store, _, factory = runtime
    bad = {**deal_dict, "amount_usd": 2e9}
    pipe = factory(
        [
            {"relevant": True, "reason": "investment"},
            {"edges": [bad]},
            {"edges": [deal_dict]},
        ]
    )
    save(store, cfg, deal_dict)
    pipe.run_documents()
    candidate = store.candidates()[0]
    assert candidate["verification"]["passed"]
    assert (
        candidate["verification"]["history"]["original_failure"]["deal"]["amount_usd"]
        == 2e9
    )
    assert "amount_usd" in pipe.provider.calls[-1][1]


def test_json_failure_is_observable_and_retry_is_bounded(runtime, deal_dict):
    cfg, store, trace, factory = runtime
    pipe = factory(
        [{"relevant": True, "reason": "investment"}, "not json", "still not json"]
    )
    save(store, cfg, deal_dict)
    result = pipe.run_documents()
    assert result["document_errors"] == 1
    assert store.rows("SELECT * FROM issues")
    assert not store.candidates()
    assert "extract.invalid_json" in trace.path.read_text()
    assert len(pipe.provider.calls) == 3


def test_no_prefix_truncation_and_overlap_merges(runtime, deal_dict):
    cfg, store, trace, factory = runtime
    cfg["deal_agent"].update(chunk_chars=150, chunk_overlap=80)
    text = (
        "Nothing relevant here. " * 30 + deal_dict["evidence_quote"] + " Padding." * 30
    )
    pieces = list(chunks(text, 150, 80))
    assert any(deal_dict["evidence_quote"] in p for p in pieces)
    assert all(len(p) <= 150 for p in pieces)
    # Tiny chunks repeat the relationship; semantic merge produces one edge.
    responses = []
    for piece in pieces:
        if "NVIDIA" in piece and "OpenAI" in piece:
            responses.extend(
                [{"relevant": True, "reason": "investment"}, {"edges": [deal_dict]}]
            )
    pipe = factory(responses)
    meta = {"source_url": deal_dict["source_url"], "published_date": "2025-09-22"}
    result = pipe.process_text(text, meta)
    assert len(result["edges"]) == 1


def test_content_dedupe_and_rejection_survive(runtime, deal_dict):
    cfg, store, _, factory = runtime
    pipe = factory([{"relevant": True, "reason": "investment"}, {"edges": [deal_dict]}])
    first = save(store, cfg, deal_dict)
    pipe.run_documents()
    store.db.execute("UPDATE candidates SET status='rejected'")
    second = save(
        store, cfg, {**deal_dict, "source_url": "https://syndicated.test/deal"}
    )
    assert first == second
    assert pipe.run_documents()["candidates_proposed"] == 0
    assert len(store.candidates("rejected")) == 1


def test_tampered_source_fails_before_model(runtime, deal_dict):
    cfg, store, _, factory = runtime
    pipe = factory()
    save(store, cfg, deal_dict)
    row = store.rows("SELECT * FROM documents")[0]
    Path(row["text_path"]).write_text("Altered source")
    with pytest.raises(ValueError, match="hash mismatch"):
        pipe.run_documents()
    assert not pipe.provider.calls


def test_retry_cannot_swap_known_entity_for_a_different_deal(runtime, deal_dict):
    cfg, store, _, factory = runtime
    bad = {**deal_dict, "amount_usd": 2e9}
    swapped = {
        **deal_dict,
        "target_entity": "Microsoft",
        "evidence_quote": "NVIDIA will invest $1 billion in Microsoft.",
    }
    pipe = factory(
        [
            {"relevant": True, "reason": "investment"},
            {"edges": [bad]},
            {"edges": [swapped]},
        ]
    )
    save(
        store,
        cfg,
        deal_dict,
        text=deal_dict["evidence_quote"] + " " + swapped["evidence_quote"],
    )
    pipe.run_documents()
    candidate = store.candidates()[0]
    assert candidate["deal"]["target_entity"] == "OpenAI"
    assert not candidate["verification"]["passed"]
    assert (
        "Retry changed target_entity identity"
        in candidate["verification"]["history"]["retry"]["verification"]["errors"]
    )


def test_filing_company_metadata_supplies_first_person_context(runtime, deal_dict):
    cfg, store, _, factory = runtime
    first_person = {
        **deal_dict,
        "evidence_quote": "We will invest $1 billion in OpenAI.",
    }
    pipe = factory(
        [{"relevant": True, "reason": "Filer investment"}, {"edges": [first_person]}]
    )
    save(store, cfg, first_person)
    result = pipe.run_documents()
    assert result["candidates_proposed"] == 1
    assert result["verification_pass_rate"] == 1
