from deal_agent.reconcile import reconcile


def graph_row(deal, **overrides):
    return {
        "edge_id": "known",
        "source_node": "Nvidia",
        "target_node": "OpenAI",
        "edge_type": "equity_investment",
        "as_of_date": deal["announced_date"],
        "source_url": deal["source_url"],
        "amount_usd_high": "1000000000",
        **overrides,
    }


def test_new_update_duplicate_and_direction(runtime, deal_dict):
    resolver = runtime[3]().resolver
    row = graph_row(deal_dict)
    assert reconcile(deal_dict, [], [], resolver)["classification"] == "NEW"
    assert reconcile(deal_dict, [row], [], resolver)["classification"] == "DUPLICATE"
    expanded = {**deal_dict, "amount_usd": 2e9}
    assert reconcile(expanded, [row], [], resolver)["classification"] == "UPDATE"
    reversed_row = {**row, "source_node": "OpenAI", "target_node": "Nvidia"}
    assert reconcile(deal_dict, [reversed_row], [], resolver)["classification"] == "NEW"


def test_pending_and_ambiguous_matches_are_explained(runtime, deal_dict):
    resolver = runtime[3]().resolver
    pending = {"id": "pending1", "deal": deal_dict}
    rec = reconcile(deal_dict, [], [pending], resolver)
    assert rec["classification"] == "DUPLICATE"
    assert rec["match_queue"] == "agent"
    result = reconcile(deal_dict, [graph_row(deal_dict)], [pending], resolver)
    assert result["classification"] == "NEW"
    assert "ambiguous" in result["reason"]


def test_same_pair_on_different_date_is_not_automatically_an_update(runtime, deal_dict):
    resolver = runtime[3]().resolver
    old = graph_row(deal_dict, as_of_date="2025-08-01", source_url="https://old.test")
    assert reconcile(deal_dict, [old], [], resolver)["classification"] == "NEW"
    expanded = {
        **deal_dict,
        "evidence_quote": "NVIDIA expanded its investment in OpenAI.",
    }
    assert reconcile(expanded, [old], [], resolver)["classification"] == "DUPLICATE"
    new_amount = {**expanded, "amount_usd": 2e9}
    assert reconcile(new_amount, [old], [], resolver)["classification"] == "UPDATE"


def test_specific_subtypes_not_collapsed_into_legacy_family(runtime, deal_dict):
    resolver = runtime[3]().resolver
    a = {**deal_dict, "deal_type": "cloud_services_contract"}
    b = {**deal_dict, "deal_type": "compute_purchase_commitment"}
    assert (
        reconcile(a, [], [{"id": "b", "deal": b}], resolver)["classification"] == "NEW"
    )


def test_migrated_range_with_blank_scalar_is_valid_match(runtime, deal_dict):
    resolver = runtime[3]().resolver
    row = graph_row(deal_dict, amount_usd="", amount_usd_low="0")
    assert reconcile(deal_dict, [row], [], resolver)["classification"] == "DUPLICATE"


def test_same_filing_can_describe_distinct_historical_deals(runtime, deal_dict):
    resolver = runtime[3]().resolver
    row = graph_row(deal_dict, as_of_date="2023-01-23")
    assert reconcile(deal_dict, [row], [], resolver)["classification"] == "NEW"


def test_unmapped_types_still_reconcile_in_pending_queue(runtime, deal_dict):
    resolver = runtime[3]().resolver
    deal = {**deal_dict, "deal_type": "revenue_share"}
    assert (
        reconcile(deal, [], [{"id": "other", "deal": deal}], resolver)["classification"]
        == "DUPLICATE"
    )
