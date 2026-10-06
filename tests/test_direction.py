"""Direction convention: money-flow, and a round trip is a 2-cycle."""
import networkx as nx
import pytest

from src.ledger import DEMAND_TYPES, FUNDING_TYPES, load_edges
from src.metrics import structure
from src.util import load_config
from tests import toy


def test_funding_and_demand_families_are_disjoint_and_complete():
    from src.ledger import EDGE_TYPES
    assert FUNDING_TYPES.isdisjoint(DEMAND_TYPES)
    assert FUNDING_TYPES | DEMAND_TYPES == EDGE_TYPES


def test_round_trip_is_a_two_cycle_with_one_leg_from_each_family():
    e, b = toy.perfect_round_trip()
    st = structure(e, load_config())
    assert len(st["round_trip_cycles"]) == 1
    cyc = st["round_trip_cycles"][0]
    assert sorted(cyc["nodes"]) == ["A", "B"]
    fams = [set(l["edge_types"]) for l in cyc["legs"]]
    assert any(f & FUNDING_TYPES for f in fams)
    assert any(f & DEMAND_TYPES for f in fams)


def test_cycle_bottleneck_is_the_narrowest_leg():
    e, b = toy.frames(
        [toy.edge("A", "B", "equity_investment", 10),
         toy.edge("B", "A", "purchase_commitment", 3)],
        [toy.backlog("A", 10)])
    st = structure(e, load_config())
    assert st["cycles"][0]["bottleneck_usd"] == pytest.approx(3.0)


def test_real_ledger_funding_edges_point_from_funder_to_recipient():
    """Spot-check the convention against rows whose direction is unambiguous."""
    df = load_edges()
    if df.empty:
        pytest.skip("no ledger yet")
    checks = [
        # (source, target, edge_type) that MUST exist with this orientation
        ("Microsoft", "OpenAI", "equity_investment"),   # Microsoft pays, OpenAI receives
        ("Nvidia", "Nscale", "warrants"),               # Nvidia funds Nscale
        ("OpenAI", "Microsoft", "cloud_capacity_contract"),  # OpenAI pays Microsoft
        ("Anthropic", "Amazon", "cloud_capacity_contract"),  # Anthropic pays AWS
    ]
    pairs = set(zip(df.source_node, df.target_node, df.edge_type))
    for src, tgt, et in checks:
        assert (src, tgt, et) in pairs, f"missing or reversed: {src} -> {tgt} [{et}]"
        assert (tgt, src, et) not in pairs, f"both orientations present for {src}/{tgt} {et}"


def test_no_self_edges_in_real_ledger():
    df = load_edges()
    if df.empty:
        pytest.skip("no ledger yet")
    assert not (df.source_node == df.target_node).any()
