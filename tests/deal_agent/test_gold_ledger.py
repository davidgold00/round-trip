import csv

from deal_agent.gold_ledger import check_gold_ledger
from src.ledger import EDGE_FIELDS


def test_gold_ledger_checks_direction_type_and_missing_explicit_id(runtime):
    cfg, _, _, factory = runtime
    resolver = factory().resolver
    row = {k: "" for k in EDGE_FIELDS}
    row.update(edge_id="reviewed", source_node="Nvidia", target_node="OpenAI",
               edge_type="equity_investment", source_url="https://source.test/deal")
    with (cfg["_root"] / "ledger/edges.csv").open("w") as f:
        w=csv.DictWriter(f, fieldnames=EDGE_FIELDS);w.writeheader();w.writerow(row)
    edge = {"source_entity": "OpenAI", "target_entity": "Nvidia", "deal_type": "debt_or_loan"}
    doc = {"id": "fixture", "source_url": row["source_url"], "expected_edges": [edge]}
    before = (cfg["_root"] / "ledger/edges.csv").read_bytes()
    result=check_gold_ledger([doc], cfg, resolver)
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["reason"] == "direction, type mapping"
    edge.update(source_entity="Nvidia", target_entity="OpenAI", deal_type="equity_investment")
    assert len(check_gold_ledger([doc], cfg, resolver)["matched"]) == 1
    doc["ledger_edge_id"] = "missing"
    assert "does not exist" in check_gold_ledger([doc], cfg, resolver)["mismatches"][0]["reason"]
    assert (cfg["_root"] / "ledger/edges.csv").read_bytes() == before
