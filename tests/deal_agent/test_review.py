import csv
import json

import pytest

from deal_agent.io import atomic_write
from deal_agent.review import Review, recover


def queued(runtime, deal):
    cfg, store, _, factory = runtime
    pipe = factory([{"relevant": True, "reason": "investment"}, {"edges": [deal]}])
    meta = {
        "company": "Nvidia",
        "source_url": deal["source_url"],
        "published_date": deal["announced_date"],
        "doc_type": "company_release",
        "evidence_tier": "T2",
        "accession_no": "",
    }
    store.job(meta["source_url"], "document", meta)
    store.save_document(
        meta,
        deal["evidence_quote"].encode(),
        deal["evidence_quote"],
        cfg["_root"] / "raw",
    )
    pipe.run_documents()
    return Review(pipe, "Test Reviewer"), store.candidates()[0]["id"]


def approval(deal, **overrides):
    return dict(
        quote=deal["evidence_quote"],
        status="announced",
        basis="notional",
        low=0,
        high=deal["amount_usd"] or 0,
        reason="Read original evidence and chose conservative bounds",
        **overrides,
    )


def test_approval_applies_only_after_review_and_audits(runtime, deal_dict):
    reviewer, ident = queued(runtime, deal_dict)
    store = runtime[1]
    before = reviewer.graph.read_bytes()
    reviewer.approve(ident, **approval(deal_dict))
    assert reviewer.graph.read_bytes() != before
    assert not store.candidates()
    assert store.candidates("approved")[0]["id"] == ident
    rows = list(csv.DictReader(reviewer.graph.open()))
    assert rows[0]["source_node"] == "Nvidia"
    assert rows[0]["agent_candidate_id"] == ident
    assert rows[0]["consideration_type"] == "cash"
    audit = store.rows("SELECT * FROM audit")[0]
    assert (
        audit["actor"] == "Test Reviewer"
        and audit["state"] == "applied"
        and audit["created"]
    )
    assert json.loads(audit["payload"])["before"] is None
    with pytest.raises(Exception, match="immutable"):
        store.db.execute("UPDATE audit SET payload='{}'")


def test_review_rechecks_edited_evidence_and_preserves_failure(
    runtime, deal_dict, tmp_path
):
    reviewer, ident = queued(runtime, deal_dict)
    path = tmp_path / "edited.json"
    path.write_text(json.dumps({**deal_dict, "evidence_quote": "Made up quote"}))
    reviewer.edit(ident, path, "Try unsupported evidence")
    with pytest.raises(ValueError, match="Verification failed"):
        reviewer.approve(ident, **approval(deal_dict))
    assert reviewer.store.candidates()[0]["status"] == "pending"
    assert len(reviewer.store.rows("SELECT * FROM audit")) == 1


def test_rejection_is_persistent_and_does_not_change_graph(runtime, deal_dict):
    reviewer, ident = queued(runtime, deal_dict)
    before = reviewer.graph.read_bytes()
    reviewer.reject(ident, "Not an eligible deal")
    assert reviewer.graph.read_bytes() == before
    assert reviewer.store.candidates("rejected")[0]["id"] == ident
    assert reviewer.store.rows("SELECT action FROM audit")[0]["action"] == "reject"


@pytest.mark.parametrize(
    "overrides",
    [
        {"quote": "Paraphrase not present"},
        {"low": -1},
        {"high": float("inf")},
        {"low": 1e9, "high": 1},
        {"high": 2e9},
        {"reason": ""},
        {"status": "binding-ish"},
    ],
)
def test_invalid_approval_leaves_candidate_pending(runtime, deal_dict, overrides):
    reviewer, ident = queued(runtime, deal_dict)
    arguments = approval(deal_dict)
    arguments.update(overrides)
    before = reviewer.graph.read_bytes()
    with pytest.raises((ValueError, SystemExit)):
        reviewer.approve(ident, **arguments)
    assert reviewer.graph.read_bytes() == before
    assert reviewer.store.candidates()[0]["status"] == "pending"


def test_update_requires_explicit_target_and_keeps_one_edge(
    runtime, deal_dict, tmp_path
):
    reviewer, ident = queued(runtime, deal_dict)
    reviewer.approve(ident, **approval(deal_dict))
    original = list(csv.DictReader(reviewer.graph.open()))[0]
    # Another source, same deal day/identity: approval must see the current graph.
    new_deal = {**deal_dict, "source_url": "https://publisher.test/update"}
    meta = {
        "company": "Nvidia",
        "source_url": new_deal["source_url"],
        "published_date": new_deal["announced_date"],
        "doc_type": "company_release",
        "evidence_tier": "T2",
        "accession_no": "",
    }
    text = "Update: " + new_deal["evidence_quote"]
    doc, _ = reviewer.store.save_document(meta, text.encode(), text, tmp_path / "raw2")
    from deal_agent.verify import verify
    from deal_agent.models import Deal

    checked = verify(
        Deal.model_validate_json(json.dumps(new_deal)),
        text,
        reviewer.resolver,
        meta["source_url"],
    )
    reviewer.store.propose(doc, new_deal, checked, {"classification": "NEW"})
    ident2 = reviewer.store.candidates()[0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        reviewer.approve(ident2, **approval(new_deal))
    reviewer.approve(ident2, **approval(new_deal), target_edge=original["edge_id"])
    assert len(list(csv.DictReader(reviewer.graph.open()))) == 1
    event = reviewer.store.rows("SELECT * FROM audit ORDER BY id DESC LIMIT 1")[0]
    assert event["action"] == "update"
    assert json.loads(event["payload"])["before"]["edge_id"] == original["edge_id"]


def test_atomic_write_failure_is_recoverable_and_does_not_mark_approved(
    runtime, deal_dict, monkeypatch
):
    reviewer, ident = queued(runtime, deal_dict)
    before = reviewer.graph.read_bytes()

    def crash(*args):
        raise OSError("disk error")

    monkeypatch.setattr("deal_agent.review.atomic_write", crash)
    with pytest.raises(OSError):
        reviewer.approve(ident, **approval(deal_dict))
    assert reviewer.graph.read_bytes() == before
    assert reviewer.store.candidates()
    recover(reviewer.store, reviewer.graph)
    assert reviewer.store.rows("SELECT state FROM audit")[0]["state"] == "aborted"


def test_crash_after_replace_finalises_only_prepared_review(
    runtime, deal_dict, monkeypatch
):
    reviewer, ident = queued(runtime, deal_dict)

    def write_then_crash(path, text):
        atomic_write(path, text)
        raise OSError("crashed after rename")

    monkeypatch.setattr("deal_agent.review.atomic_write", write_then_crash)
    with pytest.raises(OSError):
        reviewer.approve(ident, **approval(deal_dict))
    assert reviewer.store.candidates()
    recover(reviewer.store, reviewer.graph)
    assert reviewer.store.candidates("approved")
    assert reviewer.store.rows("SELECT state FROM audit")[0]["state"] == "applied"


def test_explicit_new_same_day_contract_gets_distinct_stable_id(
    runtime, deal_dict, tmp_path
):
    reviewer, ident = queued(runtime, deal_dict)
    reviewer.approve(ident, **approval(deal_dict))
    text = deal_dict["evidence_quote"] + " A separate contract."
    meta = {
        "company": "Nvidia",
        "source_url": deal_dict["source_url"],
        "published_date": deal_dict["announced_date"],
        "doc_type": "company_release",
        "evidence_tier": "T2",
        "accession_no": "",
    }
    document_id, _ = reviewer.store.save_document(
        meta, text.encode(), text, tmp_path / "different_raw"
    )
    separate = {**deal_dict, "term_or_duration": "separate tranche"}
    reviewer.store.propose(document_id, separate, {}, {})
    ident2 = reviewer.store.candidates()[0]["id"]
    reviewer.approve(ident2, **approval(separate), new_edge=True)
    rows = list(csv.DictReader(reviewer.graph.open()))
    assert len(rows) == len({row["edge_id"] for row in rows}) == 2
    assert rows[-1]["edge_id"].endswith(ident2[2:10])
