"""Phase 2: exposure metrics.

Implements DECISIONS.md Part A exactly:
  A.4 backlog dependency matrix D
  A.5 funding provenance bounds LOWER / CENTRAL / UPPER
  A.6 multi-hop provenance via damped Leontief inverse
  A.7 headline Round-Trip Exposure
  A.8 structure: SCCs, Johnson cycles with bottlenecks, PageRank, betweenness

Pure local computation. No network, no LLM.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from .entities import SEED
from .ledger import (DEMAND_TYPES, FUNDING_TYPES, filter_tiers, load_backlog,
                     load_edges, status_weight, tcv, validate, weighted_amount)
from .util import ROOT, ensure_dirs, fmt_usd, get_logger, load_config

LOG = get_logger("metrics")

OUTPUTS = ROOT / "outputs"
SITE_DATA = ROOT / "site" / "data"

BOUNDS = ("low", "central", "high")
BOUND_LABEL = {"low": "LOWER", "central": "CENTRAL", "high": "UPPER"}

NON_FILERS = {n for n, v in SEED.items() if not v[2]}


# ----------------------------------------------------------------------------
# Backlog denominators
# ----------------------------------------------------------------------------
def backlog_table(edges: pd.DataFrame, backlog: pd.DataFrame,
                  cfg: dict | None = None) -> pd.DataFrame:
    """Supplier denominators by the strict preference order of DECISIONS A.4."""
    cfg = cfg or load_config()
    rows: list[dict] = []
    pref = ["rpo", "contracted_backlog", "revenue_ttm"]
    # The supplier universe is every node that either receives a demand edge OR
    # discloses a backlog figure. Including disclosed-backlog nodes with no named
    # customers (Oracle is the big one) is essential: dropping them would shrink
    # the ecosystem denominator and inflate the headline percentage.
    suppliers = sorted(
        set(edges.loc[edges.edge_type.isin(DEMAND_TYPES), "target_node"])
        | set(backlog.loc[backlog.metric.isin(pref), "node"]))
    for node in suppliers:
        sub = backlog[backlog.node == node]
        chosen = None
        for metric in pref:
            m = sub[sub.metric == metric]
            if len(m):
                chosen = m.sort_values("as_of_date").iloc[-1]
                break
        if chosen is not None:
            rows.append({
                "node": node, "basis": chosen["metric"],
                "as_of_date": chosen["as_of_date"],
                "backlog_low": float(chosen["amount_usd_low"]),
                "backlog_high": float(chosen["amount_usd_high"]),
                "evidence_tier": chosen["evidence_tier"],
                "source_url": chosen["source_url"],
                "accession_no": chosen["accession_no"],
                "quote_snippet": chosen["quote_snippet"],
                "flag": "", "confidence": "normal",
            })
        else:
            inbound = edges[(edges.target_node == node) & edges.edge_type.isin(DEMAND_TYPES)]
            inbound = tcv(inbound, cfg)
            lo = float(weighted_amount(inbound, "low", cfg).sum())
            hi = float(weighted_amount(inbound, "high", cfg).sum())
            rows.append({
                "node": node, "basis": "sum_of_ledger_demand_edges",
                "as_of_date": cfg["project"]["as_of"],
                "backlog_low": lo, "backlog_high": hi,
                "evidence_tier": "derived", "source_url": "", "accession_no": "",
                "quote_snippet": "",
                "flag": "backlog_from_edges", "confidence": "low",
            })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# D, F and provenance
# ----------------------------------------------------------------------------
@dataclass
class MetricResult:
    nodes: list[str]
    D: dict[str, pd.DataFrame] = field(default_factory=dict)
    S: dict[str, pd.DataFrame] = field(default_factory=dict)
    P: dict[str, pd.DataFrame] = field(default_factory=dict)
    prov: dict[str, pd.DataFrame] = field(default_factory=dict)
    rte: pd.DataFrame | None = None
    ecosystem: dict = field(default_factory=dict)
    backlog: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)
    convergence: dict = field(default_factory=dict)
    network: pd.DataFrame | None = None


def _matrix(nodes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=nodes, columns=nodes)


def demand_matrix(edges: pd.DataFrame, nodes: list[str], bound: str,
                  cfg: dict) -> pd.DataFrame:
    """C[j, i] = weighted committed demand from buyer j to seller i (dollars)."""
    d = edges[edges.edge_type.isin(DEMAND_TYPES)].copy()
    d = tcv(d, cfg)
    d["amt"] = weighted_amount(d, bound, cfg)
    C = _matrix(nodes)
    for _, r in d.iterrows():
        if r.source_node in C.index and r.target_node in C.columns:
            C.loc[r.source_node, r.target_node] += float(r["amt"])
    return C


def funding_matrix(edges: pd.DataFrame, nodes: list[str], bound: str,
                   cfg: dict) -> pd.DataFrame:
    """Fm[i, j] = weighted funding dollars from funder i into recipient j."""
    f = edges[edges.edge_type.isin(FUNDING_TYPES)].copy()
    f = tcv(f, cfg)
    f["amt"] = weighted_amount(f, bound, cfg)
    Fm = _matrix(nodes)
    for _, r in f.iterrows():
        if r.source_node in Fm.index and r.target_node in Fm.columns:
            Fm.loc[r.source_node, r.target_node] += float(r["amt"])
    return Fm


def dependency_matrix(C: pd.DataFrame, backlog: pd.DataFrame, bound: str,
                      warnings: list[str]) -> pd.DataFrame:
    """D[i, j] = share of supplier i's disclosed backlog committed by customer j.

    Bound-correct denominators (DECISIONS A.4): a LOWER bound on a share is the
    smallest numerator over the LARGEST denominator, so `low` divides by
    backlog_high and `high` divides by backlog_low.
    """
    col = {"low": "backlog_high", "central": None, "high": "backlog_low"}[bound]
    D = pd.DataFrame(0.0, index=C.columns, columns=C.index)
    bl = backlog.set_index("node")
    for i in D.index:
        if i not in bl.index:
            continue
        if bound == "central":
            denom = (float(bl.loc[i, "backlog_low"]) + float(bl.loc[i, "backlog_high"])) / 2.0
        else:
            denom = float(bl.loc[i, col])
        if denom <= 0:
            continue
        # LOWER bound of a share uses the smallest numerator over the largest
        # denominator; the numerator is already bound-weighted via C.
        row = C[i] / denom
        total = float(row.sum())
        if total > 1.0 + 1e-9:
            warnings.append(
                f"{i}: ledger demand edges ({fmt_usd(float(C[i].sum()))}) exceed "
                f"disclosed backlog ({fmt_usd(denom)}) on the {BOUND_LABEL[bound]} "
                f"bound, share sum {total:.2f}. Not rescaled (DECISIONS P2).")
        D.loc[i, :] = row.clip(upper=1.0).values
    return D


def share_matrix(Fm: pd.DataFrame) -> pd.DataFrame:
    """S[i, j] = i's share of j's documented external funding. Columns sum to <=1."""
    totals = Fm.sum(axis=0)
    S = Fm.copy()
    for j in S.columns:
        t = float(totals[j])
        S[j] = (S[j] / t) if t > 0 else 0.0
    return S


def multihop(S: pd.DataFrame, alpha: float, max_hops: int) -> tuple[pd.DataFrame, dict]:
    """Damped Leontief / absorbing walk over the funding share matrix.

        P = sum_{k=1..max_hops} d_k * S^k,    d_1 = 1,  d_k = alpha^(k-1) for k >= 2

    The direct term carries full weight because a directly documented funding
    edge is the strongest evidence available; each additional intermediary is
    discounted by `alpha`. The series already contains the direct term, so
    callers must NOT add S back on top of it.

    Damping also guarantees convergence: the funding graph contains genuine
    cycles, so the undamped Leontief inverse is not guaranteed to exist.
    """
    Sv = S.values.astype(float)
    n = Sv.shape[0]
    P = np.zeros((n, n))
    term = np.eye(n)
    residual = float("inf")
    for k in range(1, max_hops + 1):
        term = term @ Sv
        d = 1.0 if k == 1 else alpha ** (k - 1)
        contribution = d * term
        P += contribution
        residual = float(np.abs(contribution).sum())
    A = alpha * Sv
    rho = float(max(abs(np.linalg.eigvals(A)))) if n else 0.0
    closed = None
    if rho < 1 - 1e-9:
        try:
            # Closed form of the same series: S + (1/alpha) * (sum_{k>=2} A^k)
            inv = np.linalg.inv(np.eye(n) - A)
            tail = (inv @ A @ A) / alpha if alpha > 0 else np.zeros((n, n))
            closed = Sv + tail
        except np.linalg.LinAlgError:
            closed = None
    info = {
        "alpha": alpha, "max_hops": max_hops,
        "spectral_radius_damped": rho,
        "truncation_residual_l1": residual,
        "closed_form_available": closed is not None,
        "max_abs_diff_vs_closed_form": (
            float(np.abs(P - closed).max()) if closed is not None else None),
    }
    return pd.DataFrame(P, index=S.index, columns=S.columns), info


def link_matrix(edges: pd.DataFrame, nodes: list[str]) -> pd.DataFrame:
    """L[i, j] = 1 if i has ANY documented funding edge into j.

    Deliberately amount-independent. Share-denominated instruments such as the
    AMD warrants issued to OpenAI and Meta carry no disclosed dollar value, so
    they contribute nothing to the dollar-weighted bounds, but they are still a
    funding link and the UPPER bound is defined on links, not dollars.
    """
    L = _matrix(nodes)
    f = edges[edges.edge_type.isin(FUNDING_TYPES)]
    for _, r in f.iterrows():
        if r.source_node in L.index and r.target_node in L.columns:
            L.loc[r.source_node, r.target_node] = 1.0
    return L


def provenance(Fm: pd.DataFrame, C: pd.DataFrame, S: pd.DataFrame,
               P: pd.DataFrame, bound: str, L: pd.DataFrame | None = None) -> pd.DataFrame:
    """Prov[i, j] in [0,1] per DECISIONS A.5 and A.6."""
    nodes = list(Fm.index)
    out = pd.DataFrame(0.0, index=nodes, columns=nodes)
    if bound == "low":
        for i in nodes:
            for j in nodes:
                commit = float(C.loc[j, i]) if (j in C.index and i in C.columns) else 0.0
                fund = float(Fm.loc[i, j])
                out.loc[i, j] = min(1.0, fund / commit) if commit > 0 else 0.0
        return out
    if bound == "central":
        # P already includes the undamped direct term (see multihop docstring).
        return P.clip(upper=1.0)
    # high: any documented funding link, direct or multi-hop, counts fully
    direct = L if L is not None else (Fm > 0).astype(float)
    link = (direct > 0) | (P > 1e-12)
    return link.astype(float)


def round_trip_exposure(D: pd.DataFrame, Prov: pd.DataFrame,
                        backlog: pd.DataFrame, bound: str) -> pd.DataFrame:
    """RTE_b(i) = sum_j D[i,j] * Prov[i->j]."""
    rows = []
    bl_index = set(backlog.loc[(backlog.backlog_low > 0) | (backlog.backlog_high > 0),
                              "node"]) if len(backlog) else set()
    for i in D.index:
        if i not in bl_index:
            continue
        contrib = {}
        total = 0.0
        for j in D.columns:
            d = float(D.loc[i, j])
            if d <= 0:
                continue
            p = float(Prov.loc[i, j]) if (i in Prov.index and j in Prov.columns) else 0.0
            v = d * p
            if v > 0 or d > 0:
                contrib[j] = {"D": d, "prov": p, "rte": v}
            total += v
        rows.append({"supplier": i, "rte": min(1.0, total), "contributions": contrib})
    return pd.DataFrame(rows)


def network_financed_share(D: pd.DataFrame, L: pd.DataFrame, P: pd.DataFrame,
                          backlog: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """SECONDARY metric, not the headline.

    Share of supplier i's backlog owed by customers who are financed by ANY
    supplier or platform in the network, not only by i. CoreWeave is the reason
    this exists: it finances none of its own customers, so its Round-Trip
    Exposure is zero, yet almost all of its backlog is owed by labs whose cash
    comes from other sellers of compute. The headline metric answers "is the
    seller financing its own buyer?"; this one answers "is the buyer financed by
    someone with compute to sell?".
    """
    financiers = set(L.index[(L.sum(axis=1) > 0)])
    bl_index = set(backlog.loc[(backlog.backlog_high > 0), "node"]) if len(backlog) else set()
    rows = []
    for i in D.index:
        if i not in bl_index:
            continue
        total = 0.0
        detail = {}
        for j in D.columns:
            d = float(D.loc[i, j])
            if d <= 0:
                continue
            funders = sorted(f for f in financiers
                             if f != j and (float(L.loc[f, j]) > 0
                                            or float(P.loc[f, j]) > 1e-12))
            if funders:
                total += d
                detail[j] = funders
        rows.append({"supplier": i, "network_financed_share": min(1.0, total),
                     "financiers_by_customer": detail})
    return pd.DataFrame(rows)


def ecosystem_total(rte: pd.DataFrame, backlog: pd.DataFrame, bound: str) -> dict:
    """Backlog-weighted ecosystem RTE. Weights use the same bound's denominator."""
    col = {"low": "backlog_high", "central": None, "high": "backlog_low"}[bound]
    bl = backlog.set_index("node")
    num = den = 0.0
    for _, r in rte.iterrows():
        i = r["supplier"]
        if i not in bl.index:
            continue
        if bound == "central":
            b = (float(bl.loc[i, "backlog_low"]) + float(bl.loc[i, "backlog_high"])) / 2.0
        else:
            b = float(bl.loc[i, col])
        num += b * float(r["rte"])
        den += b
    return {"rte": (num / den if den > 0 else 0.0), "backlog_total": den,
            "backlog_at_risk": num}


# ----------------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------------
def structure(edges: pd.DataFrame, cfg: dict) -> dict:
    e = tcv(edges, cfg)
    e["amt"] = weighted_amount(e, "central", cfg)
    G = nx.MultiDiGraph()
    for _, r in e.iterrows():
        G.add_edge(r.source_node, r.target_node, key=r.edge_id,
                   amount=float(r["amt"]), edge_type=r.edge_type,
                   status=r.status, tier=r.evidence_tier)
    simple = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        if simple.has_edge(u, v):
            simple[u][v]["amount"] += data["amount"]
            simple[u][v]["edge_types"].add(data["edge_type"])
        else:
            simple.add_edge(u, v, amount=data["amount"],
                            edge_types={data["edge_type"]})

    sccs = [sorted(c) for c in nx.strongly_connected_components(simple) if len(c) > 1]

    max_len = int(cfg["structure"]["max_cycle_len"])
    cycles = []
    for cyc in nx.simple_cycles(simple, length_bound=max_len):
        if len(cyc) < 2:
            continue
        legs = []
        for k in range(len(cyc)):
            u, v = cyc[k], cyc[(k + 1) % len(cyc)]
            data = simple[u][v]
            legs.append({"source": u, "target": v,
                         "amount": float(data["amount"]),
                         "edge_types": sorted(data["edge_types"])})
        bottleneck = min(l["amount"] for l in legs)
        has_funding = any(set(l["edge_types"]) & FUNDING_TYPES for l in legs)
        has_demand = any(set(l["edge_types"]) & DEMAND_TYPES for l in legs)
        cycles.append({
            "nodes": cyc, "length": len(cyc), "legs": legs,
            "bottleneck_usd": bottleneck,
            "is_round_trip": bool(has_funding and has_demand),
        })
    cycles.sort(key=lambda c: -c["bottleneck_usd"])

    fund = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        if data["edge_type"] in FUNDING_TYPES and data["amount"] > 0:
            if fund.has_edge(u, v):
                fund[u][v]["weight"] += data["amount"]
            else:
                fund.add_edge(u, v, weight=data["amount"])
    pagerank = nx.pagerank(fund, weight="weight") if fund.number_of_edges() else {}
    try:
        betw = nx.betweenness_centrality(simple, weight=None, normalized=True)
    except Exception:
        betw = {}
    return {
        "nodes": sorted(simple.nodes()),
        "sccs": sccs,
        "cycles": cycles,
        "round_trip_cycles": [c for c in cycles if c["is_round_trip"]],
        "pagerank_funding": dict(sorted(pagerank.items(), key=lambda kv: -kv[1])),
        "betweenness": dict(sorted(betw.items(), key=lambda kv: -kv[1])),
        "n_edges": simple.number_of_edges(),
        "n_nodes": simple.number_of_nodes(),
    }


# ----------------------------------------------------------------------------
# Top level
# ----------------------------------------------------------------------------
def compute(edges: pd.DataFrame | None = None,
            backlog_rows: pd.DataFrame | None = None,
            cfg: dict | None = None,
            tiers: list[str] | None = None) -> MetricResult:
    cfg = cfg or load_config()
    edges = load_edges() if edges is None else edges
    backlog_rows = load_backlog() if backlog_rows is None else backlog_rows
    tiers = tiers or cfg["tiers"]["headline_allowed"]
    e = filter_tiers(edges, tiers)

    # Nodes include every disclosed-backlog supplier even if no edge touches it.
    # Oracle is the case that matters: $664bn of RPO and not one named customer.
    pref_metrics = {"rpo", "contracted_backlog", "revenue_ttm"}
    nodes = sorted(set(e.source_node) | set(e.target_node)
                   | set(backlog_rows.loc[backlog_rows.metric.isin(pref_metrics), "node"]))
    res = MetricResult(nodes=nodes)
    if not nodes:
        res.warnings.append("no edges survive the tier gate")
        return res

    bl = backlog_table(e, backlog_rows, cfg)
    res.backlog = bl

    for b in BOUNDS:
        C = demand_matrix(e, nodes, b, cfg)
        Fm = funding_matrix(e, nodes, b, cfg)
        S = share_matrix(Fm)
        P, conv = multihop(S, float(cfg["multihop"]["alpha"]),
                           int(cfg["multihop"]["max_hops"]))
        D = dependency_matrix(C, bl, b, res.warnings)
        Prov = provenance(Fm, C, S, P, b, L=link_matrix(e, nodes))
        res.D[b] = D
        res.S[b] = S
        res.P[b] = P
        res.prov[b] = Prov
        res.convergence[b] = conv
        rte = round_trip_exposure(D, Prov, bl, b)
        rte = rte.rename(columns={"rte": f"rte_{b}", "contributions": f"contrib_{b}"})
        res.rte = rte if res.rte is None else res.rte.merge(rte, on="supplier", how="outer")
        res.ecosystem[BOUND_LABEL[b]] = ecosystem_total(
            rte.rename(columns={f"rte_{b}": "rte"}), bl, b)
        if b == "central":
            res.network = network_financed_share(D, link_matrix(e, nodes), P, bl, cfg)

    res.warnings = sorted(set(res.warnings))
    return res


def to_json(res: MetricResult, edges: pd.DataFrame, cfg: dict) -> dict:
    struct = structure(filter_tiers(edges, cfg["tiers"]["headline_allowed"]), cfg)
    struct_sens = structure(filter_tiers(edges, cfg["tiers"]["sensitivity_allowed"]), cfg)
    bl = res.backlog
    suppliers = []
    for _, r in (res.rte if res.rte is not None else pd.DataFrame()).iterrows():
        i = r["supplier"]
        brow = bl[bl.node == i]
        b = brow.iloc[0].to_dict() if len(brow) else {}
        tops = []
        contrib = r.get("contrib_central") or {}
        for j, v in sorted(contrib.items(), key=lambda kv: -kv[1]["D"]):
            tops.append({"customer": j, "D": v["D"], "provenance": v["prov"],
                         "rte": v["rte"], "is_private": j in NON_FILERS})
        suppliers.append({
            "supplier": i,
            "rte_low": float(r.get("rte_low", 0.0)),
            "rte_central": float(r.get("rte_central", 0.0)),
            "rte_high": float(r.get("rte_high", 0.0)),
            "backlog_low": float(b.get("backlog_low", 0.0)),
            "backlog_high": float(b.get("backlog_high", 0.0)),
            "backlog_basis": b.get("basis", ""),
            "backlog_as_of": b.get("as_of_date", ""),
            "backlog_source_url": b.get("source_url", ""),
            "backlog_accession": b.get("accession_no", ""),
            "backlog_quote": b.get("quote_snippet", ""),
            "backlog_flag": b.get("flag", ""),
            "confidence": b.get("confidence", ""),
            "top_counterparties": tops,
        })
    # Attribution coverage: how much of each supplier's disclosed backlog can be
    # tied to a NAMED customer at all. The complement is the part of the number
    # that no filing lets anyone attribute, and it is the headline's biggest
    # single caveat.
    net = {}
    if res.network is not None and len(res.network):
        net = {r["supplier"]: r for _, r in res.network.iterrows()}
    for sup in suppliers:
        i = sup["supplier"]
        named = sum(t["D"] for t in sup["top_counterparties"])
        sup["named_customer_share"] = min(1.0, named)
        sup["unattributable_share"] = max(0.0, 1.0 - min(1.0, named))
        nrow = net.get(i)
        sup["network_financed_share"] = (
            float(nrow["network_financed_share"]) if nrow is not None else 0.0)
        sup["financiers_by_customer"] = (
            nrow["financiers_by_customer"] if nrow is not None else {})

    bl_tot = sum(s["backlog_high"] for s in suppliers) or 1.0
    coverage = {
        "backlog_total_high": bl_tot,
        "named_share_weighted": sum(s["backlog_high"] * s["named_customer_share"]
                                    for s in suppliers) / bl_tot,
        "unattributable_weighted": sum(s["backlog_high"] * s["unattributable_share"]
                                       for s in suppliers) / bl_tot,
        "network_financed_weighted": sum(s["backlog_high"] * s["network_financed_share"]
                                         for s in suppliers) / bl_tot,
        "suppliers_with_no_named_customer": [s["supplier"] for s in suppliers
                                             if s["named_customer_share"] == 0.0],
    }

    suppliers.sort(key=lambda s: -s["rte_central"])
    return {
        "coverage": coverage,
        "as_of": cfg["project"]["as_of"],
        "generated": pd.Timestamp.utcnow().isoformat(),
        "tier_gate": cfg["tiers"]["headline_allowed"],
        "ecosystem": res.ecosystem,
        "suppliers": suppliers,
        "backlog": bl.to_dict(orient="records") if bl is not None else [],
        "convergence": res.convergence,
        "warnings": res.warnings,
        "structure": struct,
        "structure_sensitivity_T3": {
            "cycles": struct_sens["cycles"],
            "n_edges": struct_sens["n_edges"],
            "pagerank_funding": struct_sens["pagerank_funding"],
        },
        "status_weights": cfg["status_weights"],
        "non_filers": sorted(NON_FILERS),
    }


def sensitivity_t3(edges: pd.DataFrame, backlog_rows: pd.DataFrame, cfg: dict) -> dict:
    res = compute(edges, backlog_rows, cfg, tiers=cfg["tiers"]["sensitivity_allowed"])
    return {"ecosystem": res.ecosystem,
            "suppliers": [
                {"supplier": r["supplier"],
                 "rte_low": float(r.get("rte_low", 0.0)),
                 "rte_central": float(r.get("rte_central", 0.0)),
                 "rte_high": float(r.get("rte_high", 0.0))}
                for _, r in (res.rte if res.rte is not None else pd.DataFrame()).iterrows()],
            "warnings": res.warnings}


def main() -> None:
    cfg = load_config()
    ensure_dirs(OUTPUTS, SITE_DATA)
    edges = load_edges()
    backlog_rows = load_backlog()
    problems = validate(edges)
    if problems:
        LOG.warning("ledger validation found %d problems:", len(problems))
        for p in problems[:30]:
            LOG.warning("  %s", p)
    res = compute(edges, backlog_rows, cfg)
    payload = to_json(res, edges, cfg)
    payload["sensitivity_T3"] = sensitivity_t3(edges, backlog_rows, cfg)
    payload["ledger_validation"] = problems
    payload["edge_counts_by_tier"] = (
        edges.evidence_tier.value_counts().to_dict() if len(edges) else {})
    payload["edge_counts_by_status"] = (
        edges.status.value_counts().to_dict() if len(edges) else {})
    payload["edge_counts_by_type"] = (
        edges.edge_type.value_counts().to_dict() if len(edges) else {})

    (OUTPUTS / "metrics.json").write_text(json.dumps(payload, indent=2, default=str))
    (SITE_DATA / "metrics.json").write_text(json.dumps(payload, default=str))
    eco = payload["ecosystem"]
    LOG.info("ecosystem RTE  LOWER %.1f%%  CENTRAL %.1f%%  UPPER %.1f%%",
             100 * eco["LOWER"]["rte"], 100 * eco["CENTRAL"]["rte"],
             100 * eco["UPPER"]["rte"])
    for s in payload["suppliers"][:12]:
        LOG.info("  %-12s RTE %5.1f%% / %5.1f%% / %5.1f%%  backlog %s (%s)",
                 s["supplier"], 100 * s["rte_low"], 100 * s["rte_central"],
                 100 * s["rte_high"], fmt_usd(s["backlog_high"]), s["backlog_basis"])
    print(json.dumps({"ecosystem": eco}, indent=2))


if __name__ == "__main__":
    main()
