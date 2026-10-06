"""Phase 3: cascade stress test, Monte Carlo, and a second-method cross-check.

Pre-registered in DECISIONS.md A.9. Pure local computation.

Model
-----
A funding shock hits buyer j: its new external funding falls by `x`. Its ability
to honour commitments scales by `1 - passthrough * x`. Suppliers lose the
corresponding share of backlog. A supplier that loses revenue reduces its own
outbound funding and purchases by `capacity_to_invest` times its revenue loss
rate, which re-shocks the buyers it was financing. Iterate to a fixed point.

Cross-checked against two independent methods:
  * Eisenberg-Noe style proportional clearing on the commitment network.
  * DebtRank adapted to commitments.
Disagreements are reported, not reconciled away.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from .ledger import (DEMAND_TYPES, FUNDING_TYPES, filter_tiers, load_backlog,
                     load_edges, status_weight, tcv, weighted_amount)
from .metrics import backlog_table, demand_matrix, funding_matrix, link_matrix
from .util import ROOT, ensure_dirs, fmt_usd, get_logger, load_config

LOG = get_logger("stress")
OUTPUTS = ROOT / "outputs"
SITE_DATA = ROOT / "site" / "data"


# ---------------------------------------------------------------------------
# Network container shared by every method
# ---------------------------------------------------------------------------
@dataclass
class Network:
    nodes: list[str]
    C: pd.DataFrame        # C[buyer, seller] committed demand dollars
    F: pd.DataFrame        # F[funder, recipient] funding dollars
    backlog: pd.Series     # seller -> disclosed backlog dollars
    external: pd.Series    # node -> documented external funding dollars
    suppliers: list[str] = field(default_factory=list)
    buyers: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.nodes)


def build_network(edges: pd.DataFrame | None = None,
                  backlog_rows: pd.DataFrame | None = None,
                  cfg: dict | None = None,
                  bound: str = "central",
                  loi_weight: float | None = None,
                  conditional_weight: float | None = None) -> Network:
    cfg = cfg or load_config()
    edges = load_edges() if edges is None else edges
    backlog_rows = load_backlog() if backlog_rows is None else backlog_rows
    e = filter_tiers(edges, cfg["tiers"]["headline_allowed"])

    # Allow the Monte Carlo to override the status weights it samples over.
    if loi_weight is not None or conditional_weight is not None:
        cfg = json.loads(json.dumps(cfg))
        if loi_weight is not None:
            cfg["status_weights"]["LOI_nonbinding"][bound] = float(loi_weight)
        if conditional_weight is not None:
            cfg["status_weights"]["conditional"][bound] = float(conditional_weight)

    pref = {"rpo", "contracted_backlog", "revenue_ttm"}
    nodes = sorted(set(e.source_node) | set(e.target_node)
                   | set(backlog_rows.loc[backlog_rows.metric.isin(pref), "node"]))
    C = demand_matrix(e, nodes, bound, cfg)
    F = funding_matrix(e, nodes, bound, cfg)
    bl = backlog_table(e, backlog_rows, cfg).set_index("node")
    col = {"low": "backlog_high", "central": None, "high": "backlog_low"}[bound]
    backlog = pd.Series(0.0, index=nodes)
    for i in nodes:
        if i in bl.index:
            if bound == "central":
                backlog[i] = (float(bl.loc[i, "backlog_low"])
                              + float(bl.loc[i, "backlog_high"])) / 2.0
            else:
                backlog[i] = float(bl.loc[i, col])
    external = F.sum(axis=0)
    suppliers = [i for i in nodes if backlog[i] > 0]
    buyers = [j for j in nodes if C.loc[j].sum() > 0]
    return Network(nodes, C, F, backlog, external, suppliers, buyers)


# ---------------------------------------------------------------------------
# Method 1: iterative cascade to a fixed point
# ---------------------------------------------------------------------------
def cascade(net: Network, shock: dict[str, float], passthrough: float,
            capacity_to_invest: float, tol: float = 1e-9,
            max_iter: int = 200) -> dict:
    """`shock` maps node -> fractional loss of new external funding in [0, 1]."""
    nodes = net.nodes
    idx = {n: k for k, n in enumerate(nodes)}
    C = net.C.values.astype(float)        # C[buyer, seller]
    F = net.F.values.astype(float)        # F[funder, recipient]
    backlog = net.backlog.values.astype(float)
    ext = net.external.values.astype(float)

    funding_loss = np.zeros(len(nodes))   # fraction of external funding lost
    for n, x in shock.items():
        if n in idx:
            funding_loss[idx[n]] = float(np.clip(x, 0.0, 1.0))

    # honour[j] = fraction of j's commitments it can still pay
    honour = np.ones(len(nodes))
    prev_honour = honour.copy()
    iterations = 0
    residual = np.inf
    history = []

    for iterations in range(1, max_iter + 1):
        # 1. buyers' ability to pay falls with their funding shortfall
        honour = np.clip(1.0 - passthrough * funding_loss, 0.0, 1.0)

        # 2. suppliers lose the committed demand of impaired buyers
        #    lost[seller] = sum over buyers of C[buyer, seller] * (1 - honour[buyer])
        lost = (C * (1.0 - honour)[:, None]).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            backlog_loss_rate = np.where(backlog > 0, lost / backlog, 0.0)
        backlog_loss_rate = np.clip(backlog_loss_rate, 0.0, 1.0)

        # 3. impaired suppliers cut their own outbound funding
        #    cut[funder] = capacity_to_invest * backlog_loss_rate[funder]
        cut = np.clip(capacity_to_invest * backlog_loss_rate, 0.0, 1.0)
        #    the recipients lose that share of the funding those funders provided
        withdrawn = (F * cut[:, None]).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            induced = np.where(ext > 0, withdrawn / ext, 0.0)
        induced = np.clip(induced, 0.0, 1.0)

        # 4. a node's total funding loss is its exogenous shock plus induced loss
        new_loss = np.zeros(len(nodes))
        for n, x in shock.items():
            if n in idx:
                new_loss[idx[n]] = float(np.clip(x, 0.0, 1.0))
        new_loss = np.clip(np.maximum(new_loss, 0.0) + induced, 0.0, 1.0)

        residual = float(np.abs(new_loss - funding_loss).max())
        history.append(residual)
        funding_loss = new_loss
        if residual < tol:
            break
        prev_honour = honour.copy()

    honour = np.clip(1.0 - passthrough * funding_loss, 0.0, 1.0)
    lost = (C * (1.0 - honour)[:, None]).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        at_risk = np.where(backlog > 0, lost / backlog, 0.0)
    at_risk = np.clip(at_risk, 0.0, 1.0)

    tot_bl = float(backlog.sum())
    return {
        "converged": residual < tol,
        "iterations": iterations,
        "residual": residual,
        "residual_history": history[:25],
        "funding_loss": {n: float(funding_loss[idx[n]]) for n in nodes},
        "honour": {n: float(honour[idx[n]]) for n in nodes},
        "backlog_at_risk_share": {n: float(at_risk[idx[n]]) for n in net.suppliers},
        "backlog_at_risk_usd": {n: float(lost[idx[n]]) for n in net.suppliers},
        "ecosystem_at_risk_share": (float(lost.sum() / tot_bl) if tot_bl > 0 else 0.0),
        "ecosystem_at_risk_usd": float(lost.sum()),
    }


# ---------------------------------------------------------------------------
# Method 2: Eisenberg-Noe style proportional clearing on commitments
# ---------------------------------------------------------------------------
def eisenberg_noe(net: Network, shock: dict[str, float],
                  passthrough: float, tol: float = 1e-10,
                  max_iter: int = 500) -> dict:
    """Clearing vector on the commitment network.

    Commitments are treated as obligations. Each node's resources are its
    documented external funding, scaled down by the shock, plus the payments it
    receives from others. A node pays its obligations in full if it can, and
    otherwise pays pro rata. The fixed point is the greatest clearing vector,
    reached by iterating from full payment downwards (Eisenberg and Noe 2001).
    """
    nodes = net.nodes
    idx = {n: k for k, n in enumerate(nodes)}
    L = net.C.values.astype(float)          # obligations[debtor, creditor]
    obligations = L.sum(axis=1)
    ext = net.external.values.astype(float)

    loss = np.zeros(len(nodes))
    for n, x in shock.items():
        if n in idx:
            loss[idx[n]] = float(np.clip(x, 0.0, 1.0))
    resources = ext * (1.0 - passthrough * loss)

    with np.errstate(divide="ignore", invalid="ignore"):
        Pi = np.where(obligations[:, None] > 0, L / obligations[:, None], 0.0)

    p = obligations.copy()                  # start at full payment
    for it in range(1, max_iter + 1):
        inflow = Pi.T @ p
        p_new = np.minimum(obligations, resources + inflow)
        p_new = np.maximum(p_new, 0.0)
        delta = float(np.abs(p_new - p).max())
        p = p_new
        if delta < tol:
            break

    with np.errstate(divide="ignore", invalid="ignore"):
        shortfall_rate = np.where(obligations > 0, 1.0 - p / obligations, 0.0)
    received = Pi.T @ p
    promised = L.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        creditor_shortfall = np.where(promised > 0, 1.0 - received / promised, 0.0)
    backlog = net.backlog.values.astype(float)
    at_risk_usd = creditor_shortfall * np.minimum(promised, backlog)
    tot = float(backlog.sum())
    return {
        "iterations": it, "residual": delta, "converged": delta < tol,
        "debtor_shortfall": {n: float(shortfall_rate[idx[n]]) for n in nodes},
        "backlog_at_risk_share": {
            n: float(np.clip(at_risk_usd[idx[n]] / backlog[idx[n]], 0, 1))
            for n in net.suppliers if backlog[idx[n]] > 0},
        "ecosystem_at_risk_share": float(at_risk_usd.sum() / tot) if tot > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Method 3: DebtRank adapted to commitments
# ---------------------------------------------------------------------------
def debt_rank(net: Network, shock: dict[str, float]) -> dict:
    """DebtRank (Battiston et al.) with commitment exposure as the impact weight.

    W[i, j] = share of j's backlog that i has committed, capped at 1. Distress
    propagates once per node (the standard DebtRank restriction that stops a node
    re-spreading distress), from buyers to the sellers exposed to them.
    """
    nodes = net.nodes
    idx = {n: k for k, n in enumerate(nodes)}
    C = net.C.values.astype(float)
    backlog = net.backlog.values.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        W = np.where(backlog[None, :] > 0, C / backlog[None, :], 0.0)
    W = np.clip(W, 0.0, 1.0)

    h = np.zeros(len(nodes))
    for n, x in shock.items():
        if n in idx:
            h[idx[n]] = float(np.clip(x, 0.0, 1.0))
    state = np.where(h > 0, 1, 0)           # 0 undistressed, 1 distressed, 2 inactive
    rounds = 0
    while (state == 1).any() and rounds < 50:
        rounds += 1
        active = state == 1
        new_h = h.copy()
        for i in np.flatnonzero(active):
            new_h = np.minimum(1.0, new_h + W[i, :] * h[i])
        newly = (new_h > h + 1e-15) & (state == 0)
        state[active] = 2
        state[newly] = 1
        h = new_h
    tot = float(backlog.sum())
    at_risk = h * backlog
    return {
        "rounds": rounds,
        "distress": {n: float(h[idx[n]]) for n in nodes},
        "backlog_at_risk_share": {n: float(h[idx[n]]) for n in net.suppliers},
        "ecosystem_at_risk_share": float(at_risk.sum() / tot) if tot > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Scenario library
# ---------------------------------------------------------------------------
def scenario_library(net: Network, cfg: dict) -> dict:
    s = cfg["stress"]
    labs = [n for n in ("OpenAI", "Anthropic", "xAI") if n in net.nodes]
    hyperscalers = [n for n in ("Microsoft", "Amazon", "Alphabet", "Meta") if n in net.nodes]
    presets = {
        "lab_raise_falls_50": {
            "label": "Lab raise falls 50%",
            "description": "Every private AI lab in the ledger raises half of what it planned.",
            "shock": {n: 0.50 for n in labs},
            "passthrough": s["passthrough"],
            "capacity_to_invest": s["capacity_to_invest"],
        },
        "single_tranche_fails": {
            "label": "Single tranche fails",
            "description": ("One named conditional tranche does not close. Modelled as the "
                            "largest conditional funding edge going to zero, which here is "
                            "the loss of that share of the recipient's documented funding."),
            "shock": _largest_conditional_shock(net),
            "passthrough": s["passthrough"],
            "capacity_to_invest": s["capacity_to_invest"],
        },
        "lab_cannot_refinance": {
            "label": "Lab cannot refinance debt",
            "description": ("The most funding-dependent lab loses all new external funding. "
                            "Debt and convertible facilities are not rolled."),
            "shock": _most_dependent_lab_shock(net),
            "passthrough": min(1.0, s["passthrough"] + 0.2),
            "capacity_to_invest": s["capacity_to_invest"],
        },
        "hyperscaler_capex_cut_20": {
            "label": "One hyperscaler cuts capex 20%",
            "description": ("The largest hyperscaler buyer in the ledger cuts spending 20%. "
                            "Hits the neoclouds whose backlog it dominates."),
            "shock": _largest_hyperscaler_shock(net, 0.20),
            "passthrough": 1.0,
            "capacity_to_invest": s["capacity_to_invest"],
        },
        "chip_supply_shock": {
            "label": "Chip supply shock raises costs",
            "description": ("Costs rise so every buyer gets 15% less compute per dollar; "
                            "modelled as a uniform 15% funding shortfall across all buyers, "
                            "with high pass-through because the contracts are priced in "
                            "dollars, not in delivered capacity."),
            "shock": {n: 0.15 for n in net.buyers},
            "passthrough": min(1.0, s["passthrough"] + 0.25),
            "capacity_to_invest": s["capacity_to_invest"],
        },
    }
    out = {}
    for key, p in presets.items():
        res = cascade(net, p["shock"], p["passthrough"], p["capacity_to_invest"],
                      tol=s["fixed_point_tol"], max_iter=s["max_iter"])
        en = eisenberg_noe(net, p["shock"], p["passthrough"])
        dr = debt_rank(net, p["shock"])
        out[key] = {
            "label": p["label"], "description": p["description"],
            "shock": p["shock"], "passthrough": p["passthrough"],
            "capacity_to_invest": p["capacity_to_invest"],
            "cascade": res,
            "eisenberg_noe": {k: en[k] for k in
                              ("iterations", "converged", "backlog_at_risk_share",
                               "ecosystem_at_risk_share")},
            "debt_rank": {k: dr[k] for k in
                          ("rounds", "backlog_at_risk_share", "ecosystem_at_risk_share")},
            "method_disagreement": {
                "cascade_vs_eisenberg_noe": (res["ecosystem_at_risk_share"]
                                             - en["ecosystem_at_risk_share"]),
                "cascade_vs_eisenberg_noe_excess_over_baseline": None,
                "cascade_vs_debt_rank": (res["ecosystem_at_risk_share"]
                                         - dr["ecosystem_at_risk_share"]),
            },
        }
    return out


def _largest_conditional_shock(net: Network) -> dict[str, float]:
    e = filter_tiers(load_edges(), ["T1", "T2"])
    cond = e[(e.status.isin(["conditional", "LOI_nonbinding"]))
             & e.edge_type.isin(FUNDING_TYPES)].copy()
    if cond.empty:
        return {}
    cond["amt"] = pd.to_numeric(cond.amount_usd_high, errors="coerce").fillna(0.0)
    row = cond.sort_values("amt").iloc[-1]
    j = row.target_node
    ext = float(net.external.get(j, 0.0))
    share = min(1.0, float(row["amt"]) / ext) if ext > 0 else 1.0
    return {j: share}


def _most_dependent_lab_shock(net: Network) -> dict[str, float]:
    labs = [n for n in ("OpenAI", "Anthropic", "xAI") if n in net.nodes]
    if not labs:
        return {}
    j = max(labs, key=lambda n: float(net.external.get(n, 0.0)))
    return {j: 1.0}


def _largest_hyperscaler_shock(net: Network, x: float) -> dict[str, float]:
    cands = [n for n in ("Meta", "Microsoft", "Amazon", "Alphabet") if n in net.nodes]
    if not cands:
        return {}
    j = max(cands, key=lambda n: float(net.C.loc[n].sum()) if n in net.C.index else 0.0)
    return {j: x}


# ---------------------------------------------------------------------------
# Monte Carlo and tornado sensitivity
# ---------------------------------------------------------------------------
def monte_carlo(cfg: dict, edges: pd.DataFrame, backlog_rows: pd.DataFrame,
                base_shock: dict[str, float], draws: int | None = None) -> dict:
    s = cfg["stress"]
    draws = draws or int(s["monte_carlo_draws"])
    rng = np.random.default_rng(int(s["random_seed"]))

    pt_lo, pt_hi = s["passthrough_range"]
    ci_lo, ci_hi = s["capacity_to_invest_range"]
    loi_lo, loi_hi = s["loi_conversion_range"]
    cond_lo, cond_hi = s["conditional_realisation_range"]
    bounds = ["low", "central", "high"]
    bound_p = [0.25, 0.50, 0.25]

    # Pre-build one network per (bound, loi, cond) grid cell to keep this fast;
    # the matrices are tiny but rebuilding 20k times is wasteful.
    grid_n = 12
    loi_grid = np.linspace(loi_lo, loi_hi, grid_n)
    cond_grid = np.linspace(cond_lo, cond_hi, grid_n)
    cache: dict[tuple, Network] = {}

    def get_net(bound: str, li: int, ci: int) -> Network:
        key = (bound, li, ci)
        if key not in cache:
            cache[key] = build_network(edges, backlog_rows, cfg, bound,
                                       loi_weight=float(loi_grid[li]),
                                       conditional_weight=float(cond_grid[ci]))
        return cache[key]

    samples: dict[str, list[float]] = {}
    eco: list[float] = []
    params: list[dict] = []
    for _ in range(draws):
        bound = rng.choice(bounds, p=bound_p)
        li = int(rng.integers(0, grid_n))
        ci = int(rng.integers(0, grid_n))
        pt = float(rng.uniform(pt_lo, pt_hi))
        cap = float(rng.uniform(ci_lo, ci_hi))
        net = get_net(str(bound), li, ci)
        res = cascade(net, base_shock, pt, cap,
                      tol=s["fixed_point_tol"], max_iter=s["max_iter"])
        eco.append(res["ecosystem_at_risk_share"])
        for k, v in res["backlog_at_risk_share"].items():
            samples.setdefault(k, []).append(v)
        params.append({"passthrough": pt, "capacity_to_invest": cap,
                       "loi": float(loi_grid[li]), "conditional": float(cond_grid[ci]),
                       "bound": {"low": 0, "central": 1, "high": 2}[str(bound)],
                       "y": res["ecosystem_at_risk_share"]})

    def band(v: list[float]) -> dict:
        a = np.asarray(v, dtype=float)
        return {"p10": float(np.percentile(a, 10)), "median": float(np.median(a)),
                "p90": float(np.percentile(a, 90)), "mean": float(a.mean()),
                "min": float(a.min()), "max": float(a.max())}

    pdf = pd.DataFrame(params)
    corr = {}
    for c in ("passthrough", "capacity_to_invest", "loi", "conditional", "bound"):
        if pdf[c].std() > 0 and pdf["y"].std() > 0:
            corr[c] = float(np.corrcoef(pdf[c], pdf["y"])[0, 1])
        else:
            corr[c] = 0.0

    return {"draws": draws, "ecosystem": band(eco),
            "suppliers": {k: band(v) for k, v in samples.items()},
            "driver_correlation": dict(sorted(corr.items(), key=lambda kv: -abs(kv[1]))),
            "grid": {"loi": loi_grid.tolist(), "conditional": cond_grid.tolist()}}


def tornado(cfg: dict, edges: pd.DataFrame, backlog_rows: pd.DataFrame,
            base_shock: dict[str, float]) -> list[dict]:
    """One-at-a-time sensitivity: swing each parameter across its range."""
    s = cfg["stress"]
    base_net = build_network(edges, backlog_rows, cfg, "central")
    base = cascade(base_net, base_shock, s["passthrough"], s["capacity_to_invest"],
                   tol=s["fixed_point_tol"], max_iter=s["max_iter"])["ecosystem_at_risk_share"]
    rows = []

    def run(**kw) -> float:
        net = kw.pop("net", base_net)
        return cascade(net, base_shock,
                       kw.get("passthrough", s["passthrough"]),
                       kw.get("capacity_to_invest", s["capacity_to_invest"]),
                       tol=s["fixed_point_tol"],
                       max_iter=s["max_iter"])["ecosystem_at_risk_share"]

    lo, hi = s["passthrough_range"]
    rows.append({"parameter": "passthrough", "low_value": lo, "high_value": hi,
                 "low_result": run(passthrough=lo), "high_result": run(passthrough=hi)})
    lo, hi = s["capacity_to_invest_range"]
    rows.append({"parameter": "capacity_to_invest", "low_value": lo, "high_value": hi,
                 "low_result": run(capacity_to_invest=lo),
                 "high_result": run(capacity_to_invest=hi)})
    lo, hi = s["loi_conversion_range"]
    rows.append({"parameter": "LOI_weight", "low_value": lo, "high_value": hi,
                 "low_result": run(net=build_network(edges, backlog_rows, cfg, "central",
                                                     loi_weight=lo)),
                 "high_result": run(net=build_network(edges, backlog_rows, cfg, "central",
                                                      loi_weight=hi))})
    lo, hi = s["conditional_realisation_range"]
    rows.append({"parameter": "conditional_weight", "low_value": lo, "high_value": hi,
                 "low_result": run(net=build_network(edges, backlog_rows, cfg, "central",
                                                     conditional_weight=lo)),
                 "high_result": run(net=build_network(edges, backlog_rows, cfg, "central",
                                                      conditional_weight=hi))})
    rows.append({"parameter": "attribution_bound", "low_value": "LOWER", "high_value": "UPPER",
                 "low_result": run(net=build_network(edges, backlog_rows, cfg, "low")),
                 "high_result": run(net=build_network(edges, backlog_rows, cfg, "high"))})
    lo, hi = cfg["amounts"]["assumed_term_years_sensitivity"]
    for v, key in ((lo, "low_result"), (hi, "high_result")):
        import copy
        c2 = copy.deepcopy(cfg)
        c2["amounts"]["assumed_term_years"] = v
        val = run(net=build_network(edges, backlog_rows, c2, "central"))
        if key == "low_result":
            row = {"parameter": "assumed_term_years", "low_value": lo, "high_value": hi,
                   "low_result": val}
            rows.append(row)
        else:
            rows[-1]["high_result"] = val

    for r in rows:
        r["base_result"] = base
        r["swing"] = abs(r["high_result"] - r["low_result"])
    rows.sort(key=lambda r: -r["swing"])
    return rows


def main() -> None:
    cfg = load_config()
    ensure_dirs(OUTPUTS, SITE_DATA)
    edges = load_edges()
    backlog_rows = load_backlog()
    if edges.empty:
        LOG.error("ledger is empty, nothing to stress")
        return
    net = build_network(edges, backlog_rows, cfg, "central")
    LOG.info("network: %d nodes, %d suppliers with backlog, %d buyers, backlog %s",
             net.n, len(net.suppliers), len(net.buyers), fmt_usd(float(net.backlog.sum())))

    # No-shock baselines. Without these the method disagreement is impossible to
    # read: Eisenberg-Noe treats commitments as obligations and documented
    # external funding as resources, and in this dataset commitments already
    # exceed documented funding by a wide margin, so it reports a large
    # shortfall before any shock is applied at all.
    zero = {n: 0.0 for n in net.nodes}
    baseline = {
        "cascade": cascade(net, zero, cfg["stress"]["passthrough"],
                           cfg["stress"]["capacity_to_invest"])["ecosystem_at_risk_share"],
        "eisenberg_noe": eisenberg_noe(net, zero, cfg["stress"]["passthrough"])[
            "ecosystem_at_risk_share"],
        "debt_rank": debt_rank(net, zero)["ecosystem_at_risk_share"],
    }
    baseline["note"] = (
        "Cascade and DebtRank are shock-relative and start at zero by construction. "
        "Eisenberg-Noe is a level measure: it asks whether the network can clear its "
        "commitments out of documented funding, and its unshocked value of "
        f"{100 * baseline['eisenberg_noe']:.1f}% says it cannot. The gap between the "
        "methods under a shock is therefore mostly this standing level, not a "
        "disagreement about how the shock propagates. Read Eisenberg-Noe minus its "
        "own baseline when comparing.")

    scenarios = scenario_library(net, cfg)
    for sc in scenarios.values():
        sc["method_disagreement"]["eisenberg_noe_excess_over_baseline"] = (
            sc["eisenberg_noe"]["ecosystem_at_risk_share"] - baseline["eisenberg_noe"])
        sc["method_disagreement"]["cascade_vs_eisenberg_noe_excess_over_baseline"] = (
            sc["cascade"]["ecosystem_at_risk_share"]
            - sc["method_disagreement"]["eisenberg_noe_excess_over_baseline"])
    base_shock = scenarios["lab_raise_falls_50"]["shock"]
    LOG.info("monte carlo: %d draws", cfg["stress"]["monte_carlo_draws"])
    mc = monte_carlo(cfg, edges, backlog_rows, base_shock)
    LOG.info("tornado sensitivity")
    torn = tornado(cfg, edges, backlog_rows, base_shock)

    dominated = torn[0]["swing"] > 0.5 * max(1e-9, torn[0]["base_result"]) if torn else False
    payload = {
        "as_of": cfg["project"]["as_of"],
        "config": cfg["stress"],
        "network": {
            "nodes": net.nodes, "suppliers": net.suppliers, "buyers": net.buyers,
            "backlog_usd": {k: float(v) for k, v in net.backlog.items() if v > 0},
            "external_funding_usd": {k: float(v) for k, v in net.external.items() if v > 0},
        },
        "baseline_no_shock": baseline,
        "scenarios": scenarios,
        "monte_carlo": mc,
        "tornado": torn,
        "assumption_dominated": bool(dominated),
        "assumption_note": (
            "The widest parameter swing is larger than half the base result, so the "
            "answer is driven as much by assumptions as by data."
            if dominated else
            "The widest parameter swing is smaller than half the base result, so the "
            "data constrains the answer more than any single assumption does."),
    }
    (OUTPUTS / "stress.json").write_text(json.dumps(payload, indent=2, default=str))
    (SITE_DATA / "stress.json").write_text(json.dumps(payload, default=str))

    for key, sc in scenarios.items():
        c = sc["cascade"]
        LOG.info("%-28s eco at risk %5.2f%%  (EN %5.2f%%, DebtRank %5.2f%%)  "
                 "iters %d conv=%s", sc["label"],
                 100 * c["ecosystem_at_risk_share"],
                 100 * sc["eisenberg_noe"]["ecosystem_at_risk_share"],
                 100 * sc["debt_rank"]["ecosystem_at_risk_share"],
                 c["iterations"], c["converged"])
    e = mc["ecosystem"]
    LOG.info("MC ecosystem at risk: median %.2f%%  p10 %.2f%%  p90 %.2f%%",
             100 * e["median"], 100 * e["p10"], 100 * e["p90"])
    for r in torn[:4]:
        LOG.info("tornado %-22s swing %5.2f pp", r["parameter"], 100 * r["swing"])
    print(json.dumps({"mc_ecosystem": e, "assumption_dominated": dominated}, indent=2))


if __name__ == "__main__":
    main()
