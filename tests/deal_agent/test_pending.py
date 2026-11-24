import json

from deal_agent.pending import export, snapshot
from test_pipeline import save


def test_pending_snapshot_readonly_limits_and_excludes_approved(runtime, deal_dict, tmp_path):
    cfg, store, _, factory = runtime
    # Point at the fixture database, never the production queue.
    cfg["deal_agent"]["state_db"] = "queue.sqlite3"
    pipe=factory([{"relevant":True,"reason":"fixture"},{"edges":[deal_dict]}])
    save(store,cfg,deal_dict);pipe.run_documents()
    before=store.rows("SELECT * FROM candidates")
    result=export(cfg,tmp_path/"export")
    assert result["pending_count"] == 1 and result["items"][0]["verification_status"] == "passed"
    assert result["items"][0]["evidence_quote"] == deal_dict["evidence_quote"]
    assert store.rows("SELECT * FROM candidates") == before
    store.db.execute("UPDATE candidates SET status='approved'")
    assert snapshot(cfg)["pending_count"] == 0
    assert json.loads((tmp_path/"export/pending_agent.json").read_text())["pending_count"] == 1


def test_missing_queue_is_not_created(runtime):
    cfg=runtime[0]
    path=cfg["_root"] / cfg["deal_agent"]["state_db"]
    assert not path.exists()
    assert snapshot(cfg)["pending_count"] == 0
    assert not path.exists()


def test_review_amount_keeps_qualification_and_full_evidence(deal_dict):
    from deal_agent.pending import review_item
    quote = "NVIDIA intends to invest up to $1 billion in OpenAI."
    deal = {**deal_dict, "evidence_quote": quote + " " + "Context. " * 80}
    checked = {"passed": False, "errors": ["amount_text is missing from evidence_quote"]}
    rec = {"classification": "UPDATE", "reason": "Compare tranche and total.", "match_id": "prior", "match_queue": "graph"}
    item = review_item("sample", deal, checked, rec)
    assert item["amount_reading"] == "up to $1 billion"
    assert item["evidence_quote"] == deal["evidence_quote"]
    assert item["failed_checks"] == checked["errors"] and item["match_id"] == "prior"
