"""The browser stress lab must reproduce the Python model exactly.

Runs site/cascade.js under node against the same inputs as src/stress.py and
compares every scenario preset. Skips if node is unavailable.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.ledger import load_backlog, load_edges
from src.site_data import build as build_site
from src.stress import build_network, cascade, debt_rank, eisenberg_noe, scenario_library
from src.util import ROOT, load_config

NODE = shutil.which("node")
TOL = 1e-9


@pytest.fixture(scope="module")
def payloads():
    if NODE is None:
        pytest.skip("node not available")
    e, b = load_edges(), load_backlog()
    if e.empty:
        pytest.skip("no ledger yet")
    cfg = load_config()
    site = build_site()
    return cfg, e, b, site


def run_js(script: str) -> dict:
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                         cwd=str(ROOT))
    if out.returncode != 0:
        raise AssertionError(f"node failed:\n{out.stderr}")
    return json.loads(out.stdout)


def js_driver(bound: str, shock: dict, passthrough: float, capacity: float,
              loi=None, conditional=None) -> dict:
    return f"""
const C = require('./site/cascade.js');
const fs = require('fs');
const ledger = JSON.parse(fs.readFileSync('./site/data/ledger.json','utf8'));
const net = C.buildNetwork(ledger.edges, ledger.backlog_rows, {{
  bound: {json.dumps(bound)},
  tiers: ledger.config.tiers.headline_allowed,
  weights: ledger.status_weights,
  assumedTerm: ledger.config.amounts.assumed_term_years,
  loiWeight: {json.dumps(loi)},
  conditionalWeight: {json.dumps(conditional)},
}});
const shock = {json.dumps(shock)};
const cas = C.cascade(net, shock, {passthrough}, {capacity}, 1e-9, 200);
const en  = C.eisenbergNoe(net, shock, {passthrough});
const dr  = C.debtRank(net, shock);
console.log(JSON.stringify({{
  nodes: net.nodes, suppliers: net.suppliers, buyers: net.buyers,
  backlog: Array.from(net.backlog), external: Array.from(net.external),
  cascade: cas, en: en, dr: dr
}}));
"""


def test_network_construction_matches(payloads):
    cfg, e, b, site = payloads
    pynet = build_network(e, b, cfg, "central")
    js = run_js(js_driver("central", {}, 0.6, 0.5))
    assert js["nodes"] == pynet.nodes
    assert js["suppliers"] == pynet.suppliers
    assert sorted(js["buyers"]) == sorted(pynet.buyers)
    for i, n in enumerate(pynet.nodes):
        assert js["backlog"][i] == pytest.approx(float(pynet.backlog[n]), abs=1e-6)
        assert js["external"][i] == pytest.approx(float(pynet.external[n]), abs=1e-6)


@pytest.mark.parametrize("bound", ["low", "central", "high"])
def test_cascade_matches_on_every_bound(payloads, bound):
    cfg, e, b, site = payloads
    shock = {"OpenAI": 0.5, "Anthropic": 0.5}
    pynet = build_network(e, b, cfg, bound)
    py = cascade(pynet, shock, 0.6, 0.5, tol=1e-9, max_iter=200)
    js = run_js(js_driver(bound, shock, 0.6, 0.5))["cascade"]
    assert js["converged"] == py["converged"]
    assert js["iterations"] == py["iterations"]
    assert js["ecosystem_at_risk_share"] == pytest.approx(
        py["ecosystem_at_risk_share"], abs=TOL)
    for k, v in py["backlog_at_risk_share"].items():
        assert js["backlog_at_risk_share"][k] == pytest.approx(v, abs=TOL)


def test_all_scenario_presets_match(payloads):
    cfg, e, b, site = payloads
    pynet = build_network(e, b, cfg, "central")
    sc = scenario_library(pynet, cfg)
    for key, p in sc.items():
        js = run_js(js_driver("central", p["shock"], p["passthrough"],
                              p["capacity_to_invest"]))
        assert js["cascade"]["ecosystem_at_risk_share"] == pytest.approx(
            p["cascade"]["ecosystem_at_risk_share"], abs=TOL), f"cascade mismatch on {key}"
        assert js["en"]["ecosystem_at_risk_share"] == pytest.approx(
            p["eisenberg_noe"]["ecosystem_at_risk_share"], abs=TOL), f"EN mismatch on {key}"
        assert js["dr"]["ecosystem_at_risk_share"] == pytest.approx(
            p["debt_rank"]["ecosystem_at_risk_share"], abs=TOL), f"DebtRank mismatch on {key}"


def test_slider_overrides_match(payloads):
    """LOI and conditional weight sliders must reweight exactly as Python does."""
    cfg, e, b, site = payloads
    shock = {"OpenAI": 0.5}
    for loi, cond, pt, cap in [(0.05, 0.25, 0.3, 0.2), (0.60, 0.80, 0.9, 0.8)]:
        pynet = build_network(e, b, cfg, "central", loi_weight=loi,
                              conditional_weight=cond)
        py = cascade(pynet, shock, pt, cap, tol=1e-9, max_iter=200)
        js = run_js(js_driver("central", shock, pt, cap, loi=loi,
                              conditional=cond))["cascade"]
        assert js["ecosystem_at_risk_share"] == pytest.approx(
            py["ecosystem_at_risk_share"], abs=TOL)
