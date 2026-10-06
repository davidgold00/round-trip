"""Snapshot reproducibility: the same ledger must give the same numbers."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.ledger import load_backlog, load_edges, snapshot, write_edges
from src.metrics import compute, to_json
from src.stress import build_network, cascade, monte_carlo, scenario_library
from src.util import ROOT, load_config


def strip_volatile(payload: dict) -> dict:
    out = json.loads(json.dumps(payload, default=str))
    out.pop("generated", None)
    return out


def test_metrics_are_deterministic():
    cfg = load_config()
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    a = strip_volatile(to_json(compute(e, b, cfg), e, cfg))
    c = strip_volatile(to_json(compute(e, b, cfg), e, cfg))
    assert a == c


def test_row_order_does_not_change_the_answer():
    cfg = load_config()
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    shuffled = e.sample(frac=1.0, random_state=7).reset_index(drop=True)
    a = compute(e, b, cfg)
    c = compute(shuffled, b, cfg)
    for bound in ("LOWER", "CENTRAL", "UPPER"):
        assert a.ecosystem[bound]["rte"] == pytest.approx(c.ecosystem[bound]["rte"])


def test_monte_carlo_is_seeded_and_reproducible():
    cfg = load_config()
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    shock = {"OpenAI": 0.5}
    a = monte_carlo(cfg, e, b, shock, draws=300)
    c = monte_carlo(cfg, e, b, shock, draws=300)
    assert a["ecosystem"] == c["ecosystem"]
    assert a["driver_correlation"] == c["driver_correlation"]


def test_scenarios_are_deterministic():
    cfg = load_config()
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    net = build_network(e, b, cfg, "central")
    a = scenario_library(net, cfg)
    c = scenario_library(net, cfg)
    for k in a:
        assert a[k]["cascade"]["ecosystem_at_risk_share"] == pytest.approx(
            c[k]["cascade"]["ecosystem_at_risk_share"])


def test_snapshot_round_trips_through_csv(tmp_path):
    e = load_edges()
    if e.empty:
        pytest.skip("no ledger yet")
    p = tmp_path / "edges_test.csv"
    write_edges(e, p)
    from src.ledger import load_edges as load
    back = load(p)
    assert len(back) == len(e)
    assert set(back.edge_id) == set(e.edge_id)
    cfg = load_config()
    b = load_backlog()
    a = compute(e, b, cfg).ecosystem
    c = compute(back, b, cfg).ecosystem
    for bound in ("LOWER", "CENTRAL", "UPPER"):
        assert a[bound]["rte"] == pytest.approx(c[bound]["rte"])


def test_committed_snapshots_still_reproduce_their_own_metrics():
    """Each snapshot's edges must still regenerate that snapshot's headline."""
    snaps = sorted((ROOT / "ledger" / "snapshots").glob("edges_*.csv"))
    if not snaps:
        pytest.skip("no snapshots yet")
    cfg = load_config()
    b = load_backlog()
    from src.ledger import load_edges as load
    for sp in snaps:
        mp = sp.parent / sp.name.replace("edges_", "metrics_").replace(".csv", ".json")
        if not mp.exists():
            continue
        stored = json.loads(mp.read_text())
        fresh = compute(load(sp), b, cfg)
        for bound in ("LOWER", "CENTRAL", "UPPER"):
            assert fresh.ecosystem[bound]["rte"] == pytest.approx(
                stored["ecosystem"][bound]["rte"], abs=1e-9), (
                f"{sp.name} no longer reproduces its stored {bound} figure")


def test_refresh_builds_every_file_the_dashboard_fetches():
    """site/index.html fetches five JSON files; all five must exist after a refresh.

    `src/site_data.py` was once missing from the refresh pipeline, so a clean
    `make refresh` produced a dashboard that could not load its own ledger.
    """
    import re
    site = ROOT / "site"
    html = (site / "index.html").read_text()
    app = (site / "app.js").read_text()
    wanted = set(re.findall(r'fetch\("(data/[^"]+)"\)', app))
    assert wanted, "no data fetches found in app.js"
    for rel in sorted(wanted):
        assert (site / rel).exists(), f"{rel} is fetched by the dashboard but not built"
    import src.refresh as refresh_mod
    src = refresh_mod.__file__
    text = open(src).read()
    assert "site_data" in text, "refresh must build the dashboard payload"
