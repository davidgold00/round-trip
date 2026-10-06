"""Toy-graph correctness for the pre-registered metrics (DECISIONS Part A)."""
import numpy as np
import pytest

from src.metrics import BOUND_LABEL, compute, structure
from src.util import load_config
from tests import toy


@pytest.fixture
def cfg():
    return load_config()


def test_perfect_round_trip_is_100_percent_on_every_bound(cfg):
    e, b = toy.perfect_round_trip()
    res = compute(e, b, cfg)
    row = res.rte.set_index("supplier").loc["A"]
    assert row["rte_low"] == pytest.approx(1.0)
    assert row["rte_central"] == pytest.approx(1.0)
    assert row["rte_high"] == pytest.approx(1.0)
    for label in ("LOWER", "CENTRAL", "UPPER"):
        assert res.ecosystem[label]["rte"] == pytest.approx(1.0)


def test_half_funded_gives_50_percent_lower_and_central(cfg):
    e, b = toy.half_funded()
    res = compute(e, b, cfg)
    row = res.rte.set_index("supplier").loc["A"]
    assert row["rte_low"] == pytest.approx(0.5)
    assert row["rte_central"] == pytest.approx(0.5)
    assert row["rte_high"] == pytest.approx(1.0), "UPPER treats any funding link as full"


def test_dependency_matrix_is_share_of_backlog(cfg):
    e, b = toy.half_funded()
    res = compute(e, b, cfg)
    assert res.D["central"].loc["A", "B"] == pytest.approx(1.0)
    assert res.D["central"].loc["A", "C"] == pytest.approx(0.0)


def test_two_hop_lower_is_zero_central_is_alpha_squared(cfg):
    e, b = toy.two_hop()
    res = compute(e, b, cfg)
    row = res.rte.set_index("supplier").loc["A"]
    assert row["rte_low"] == pytest.approx(0.0), "LOWER is direct funding only"
    alpha = float(cfg["multihop"]["alpha"])
    assert row["rte_central"] == pytest.approx(alpha, rel=1e-9), \
        "one intermediary, so one factor of alpha"
    assert row["rte_high"] == pytest.approx(1.0), "multi-hop link counts for UPPER"


def test_lower_bound_never_exceeds_central_never_exceeds_upper(cfg):
    for maker in (toy.perfect_round_trip, toy.half_funded, toy.two_hop):
        e, b = maker()
        res = compute(e, b, cfg)
        for _, r in res.rte.iterrows():
            assert r["rte_low"] <= r["rte_central"] + 1e-12
            assert r["rte_central"] <= r["rte_high"] + 1e-12


def test_status_weight_scales_amounts(cfg):
    e, b = toy.perfect_round_trip()
    e.loc[e.edge_type == "purchase_commitment", "status"] = "LOI_nonbinding"
    res = compute(e, b, cfg)
    row = res.rte.set_index("supplier").loc["A"]
    w = cfg["status_weights"]["LOI_nonbinding"]
    # D scales with the demand-edge weight; LOWER provenance is capped at 1 and
    # the funding leg still exceeds the shrunken commitment, so it stays 1.
    assert row["rte_low"] == pytest.approx(w["low"])
    assert row["rte_central"] == pytest.approx(w["central"])


def test_per_year_basis_is_multiplied_by_term(cfg):
    e, b = toy.perfect_round_trip()
    e.loc[e.edge_type == "purchase_commitment", "amount_basis"] = "per-year"
    e.loc[e.edge_type == "purchase_commitment", "amount_usd_low"] = 2.0
    e.loc[e.edge_type == "purchase_commitment", "amount_usd_high"] = 2.0
    e.loc[e.edge_type == "purchase_commitment", "term_start"] = "2026-01-01"
    e.loc[e.edge_type == "purchase_commitment", "term_end"] = "2031-01-01"
    res = compute(e, b, cfg)
    # 2 per year over 5 years = 10 = the whole backlog
    assert res.D["central"].loc["A", "B"] == pytest.approx(1.0, rel=1e-3)


def test_multihop_converges_and_matches_closed_form(cfg):
    e, b = toy.two_hop()
    res = compute(e, b, cfg)
    info = res.convergence["central"]
    assert info["spectral_radius_damped"] < 1.0
    assert info["closed_form_available"] is True
    assert info["max_abs_diff_vs_closed_form"] < 1e-6


def test_aggregate_exceeding_backlog_warns_but_is_not_rescaled(cfg):
    e, b = toy.frames(
        [toy.edge("A", "B", "equity_investment", 10),
         toy.edge("B", "A", "purchase_commitment", 10),
         toy.edge("C", "A", "purchase_commitment", 10)],
        [toy.backlog("A", 10)])
    res = compute(e, b, cfg)
    assert any("exceed disclosed backlog" in w for w in res.warnings)
    assert res.D["central"].loc["A", "B"] == pytest.approx(1.0)
    assert res.D["central"].loc["A", "C"] == pytest.approx(1.0)


def test_real_ledger_bounds_are_ordered_and_in_range():
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "outputs" / "metrics.json"
    if not p.exists():
        pytest.skip("run `make build` first")
    m = json.loads(p.read_text())
    eco = m["ecosystem"]
    assert 0.0 <= eco["LOWER"]["rte"] <= eco["CENTRAL"]["rte"] <= eco["UPPER"]["rte"] <= 1.0
    for s in m["suppliers"]:
        assert 0.0 <= s["rte_low"] <= s["rte_central"] <= s["rte_high"] <= 1.0
