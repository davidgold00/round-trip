"""Cascade stress test: convergence, monotonicity, and the second method."""
import numpy as np
import pytest

from src.stress import (build_network, cascade, debt_rank, eisenberg_noe,
                        scenario_library, tornado)
from src.util import load_config
from tests import toy


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def net(cfg):
    e, b = toy.perfect_round_trip()
    return build_network(e, b, cfg, "central")


def test_no_shock_leaves_nothing_at_risk(net, cfg):
    out = cascade(net, {n: 0.0 for n in net.nodes}, 0.6, 0.5)
    assert out["converged"]
    assert out["ecosystem_at_risk_share"] == pytest.approx(0.0)


def test_full_shock_with_full_passthrough_wipes_the_backlog(net):
    out = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=0.0)
    assert out["converged"]
    assert out["backlog_at_risk_share"]["A"] == pytest.approx(1.0)


def test_passthrough_scales_the_loss_linearly(net):
    half = cascade(net, {"B": 1.0}, passthrough=0.5, capacity_to_invest=0.0)
    full = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=0.0)
    assert half["backlog_at_risk_share"]["A"] == pytest.approx(0.5)
    assert full["backlog_at_risk_share"]["A"] == pytest.approx(1.0)


def test_loss_is_monotonic_in_shock_size(net):
    prev = -1.0
    for x in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = cascade(net, {"B": x}, 0.6, 0.5)
        v = out["ecosystem_at_risk_share"]
        assert v >= prev - 1e-12
        prev = v


def test_feedback_loop_amplifies_but_converges(cfg):
    """A funds B, B buys from A, and A also funds C which buys from A.

    Shocking B impairs A, which cuts A's funding of C, which impairs C's
    purchases from A. The second round must add to the loss and must terminate.
    """
    e, b = toy.frames(
        [toy.edge("A", "B", "equity_investment", 10),
         toy.edge("B", "A", "purchase_commitment", 10),
         toy.edge("A", "C", "equity_investment", 10),
         toy.edge("C", "A", "purchase_commitment", 10)],
        [toy.backlog("A", 20)])
    net = build_network(e, b, cfg, "central")
    no_fb = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=0.0)
    with_fb = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=0.8)
    assert with_fb["converged"] and no_fb["converged"]
    assert with_fb["ecosystem_at_risk_share"] > no_fb["ecosystem_at_risk_share"]
    assert with_fb["iterations"] <= 200


def test_results_are_bounded_in_zero_one(net):
    out = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=1.0)
    for v in out["backlog_at_risk_share"].values():
        assert 0.0 <= v <= 1.0
    for v in out["honour"].values():
        assert 0.0 <= v <= 1.0


def test_eisenberg_noe_converges_and_is_bounded(net):
    out = eisenberg_noe(net, {"B": 1.0}, passthrough=1.0)
    assert out["converged"]
    for v in out["debtor_shortfall"].values():
        assert -1e-9 <= v <= 1.0 + 1e-9


def test_debt_rank_terminates_and_respects_the_once_only_rule(net):
    out = debt_rank(net, {"B": 1.0})
    assert out["rounds"] <= 50
    assert 0.0 <= out["ecosystem_at_risk_share"] <= 1.0


def test_methods_agree_on_the_trivial_full_wipe(cfg):
    """With one buyer, one seller and funding equal to the commitment, all three
    methods must put the whole backlog at risk under a total funding loss."""
    e, b = toy.perfect_round_trip()
    net = build_network(e, b, cfg, "central")
    c = cascade(net, {"B": 1.0}, passthrough=1.0, capacity_to_invest=0.0)
    d = debt_rank(net, {"B": 1.0})
    assert c["backlog_at_risk_share"]["A"] == pytest.approx(1.0)
    assert d["backlog_at_risk_share"]["A"] == pytest.approx(1.0)


def test_scenarios_and_tornado_run_on_the_real_ledger(cfg):
    from src.ledger import load_backlog, load_edges
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    net = build_network(e, b, cfg, "central")
    sc = scenario_library(net, cfg)
    assert len(sc) == 5
    for v in sc.values():
        assert v["cascade"]["converged"]
        assert 0.0 <= v["cascade"]["ecosystem_at_risk_share"] <= 1.0
    t = tornado(cfg, e, b, sc["lab_raise_falls_50"]["shock"])
    assert len(t) >= 5
    assert all(r["swing"] >= 0 for r in t)
    assert t == sorted(t, key=lambda r: -r["swing"]), "tornado must be sorted by swing"


def test_monte_carlo_is_reproducible(cfg):
    from src.ledger import load_backlog, load_edges
    from src.stress import monte_carlo
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    shock = {"OpenAI": 0.5, "Anthropic": 0.5}
    a = monte_carlo(cfg, e, b, shock, draws=400)
    c = monte_carlo(cfg, e, b, shock, draws=400)
    assert a["ecosystem"]["median"] == pytest.approx(c["ecosystem"]["median"])
    assert a["ecosystem"]["p10"] <= a["ecosystem"]["median"] <= a["ecosystem"]["p90"]
