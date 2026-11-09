"""Assemble the JSON the static dashboard reads.

Everything the page shows must be traceable to ledger rows, so the graph, the
supplier cards and the ledger explorer all carry the edge ids, quotes, URLs and
as-of dates with them.
"""
from __future__ import annotations

import json

from .entities import SEED, load_nodes
from .ledger import (DEMAND_TYPES, FUNDING_TYPES, load_backlog, load_edges,
                     status_weight, tcv, validate, weighted_amount)
from .util import ROOT, ensure_dirs, get_logger, load_config

LOG = get_logger("site")
SITE_DATA = ROOT / "site" / "data"
OUTPUTS = ROOT / "outputs"

# Three colour families, not nine. A network graph is an all-pairs form, and the
# validated categorical palette only clears the all-pairs CVD and normal-vision
# floors for its first three slots, so edge types fold into three meaningful
# families and conditionality is carried by a dash pattern instead of a 4th hue.
FAMILY = {
    "equity_investment": "ownership",
    "warrants": "ownership",
    "convertible_or_debt": "credit",
    "loan_or_guarantee": "credit",
    "vendor_financing": "credit",
    "purchase_commitment": "demand",
    "cloud_capacity_contract": "demand",
    "lease": "demand",
    "offtake_or_rpo": "demand",
}
FAMILY_LABEL = {
    "ownership": "Equity and warrants",
    "credit": "Debt, guarantees and vendor financing",
    "demand": "Committed purchases and capacity",
}
FAMILY_SHORT = {"ownership": "Equity", "credit": "Credit", "demand": "Demand"}


def build() -> dict:
    cfg = load_config()
    ensure_dirs(SITE_DATA)
    edges = load_edges()
    backlog = load_backlog()
    nodes_meta = {n["node"]: n for n in load_nodes()}
    non_filers = {n for n, v in SEED.items() if not v[2]}

    e = tcv(edges, cfg)
    e["w_central"] = status_weight(e, "central", cfg)
    e["amt_central"] = weighted_amount(e, "central", cfg)

    edge_rows = []
    for _, r in e.iterrows():
        fam = FAMILY.get(r.edge_type, "demand")
        edge_rows.append({
            "edge_id": r.edge_id, "as_of": r.as_of_date,
            "source": r.source_node, "target": r.target_node,
            "edge_type": r.edge_type, "family": fam,
            "family_label": FAMILY_LABEL[fam],
            "direction": "funding" if r.edge_type in FUNDING_TYPES else "demand",
            "low": float(r.amount_usd_low), "high": float(r.amount_usd_high),
            "tcv_low": float(r.tcv_low), "tcv_high": float(r.tcv_high),
            "weighted_central": float(r.amt_central),
            "basis": r.amount_basis, "status": r.status,
            "conditional": r.status in ("conditional", "LOI_nonbinding"),
            "conditions": r.conditions_text,
            "tier": r.evidence_tier, "url": r.source_url,
            "accession": r.accession_no, "quote": r.quote_snippet,
            "notes": r.notes, "term_start": r.term_start, "term_end": r.term_end,
            "term_assumed": bool(r.term_assumed),
            "amount_undisclosed": float(r.amount_usd_high) == 0.0,
            "extraction": {k: r.get(k, "") for k in (
                "deal_type", "consideration_type", "amount_usd", "amount_text",
                "term_or_duration", "announced_date", "evidence_quote", "confidence",
                "extraction_rationale", "agent_candidate_id", "document_sha256")},
        })

    node_rows = []
    present = sorted(set(e.source_node) | set(e.target_node)
                     | (set(backlog.node) if len(backlog) else set()))
    for n in present:
        meta = nodes_meta.get(n, {})
        out_f = e[(e.source_node == n) & e.edge_type.isin(FUNDING_TYPES)]
        in_f = e[(e.target_node == n) & e.edge_type.isin(FUNDING_TYPES)]
        out_d = e[(e.source_node == n) & e.edge_type.isin(DEMAND_TYPES)]
        in_d = e[(e.target_node == n) & e.edge_type.isin(DEMAND_TYPES)]
        node_rows.append({
            "node": n,
            "cik": meta.get("cik", ""), "ticker": meta.get("ticker", ""),
            "is_filer": str(meta.get("is_filer", "")).lower() == "true",
            "is_private": n in non_filers or str(meta.get("is_filer", "")).lower() == "false",
            "role": meta.get("role", ""),
            "discovered_via": meta.get("discovered_via", ""),
            "funding_out": float(out_f.amt_central.sum()),
            "funding_in": float(in_f.amt_central.sum()),
            "demand_out": float(out_d.amt_central.sum()),
            "demand_in": float(in_d.amt_central.sum()),
            "degree": int(len(out_f) + len(in_f) + len(out_d) + len(in_d)),
        })

    backlog_rows = [{k: (float(v) if k.startswith("amount") else v)
                     for k, v in r.items()} for r in backlog.to_dict("records")]

    payload = {
        "as_of": cfg["project"]["as_of"],
        "title": cfg["project"]["title"],
        "edges": edge_rows,
        "nodes": node_rows,
        "backlog_rows": backlog_rows,
        "families": FAMILY_LABEL,
        "families_short": FAMILY_SHORT,
        "status_weights": cfg["status_weights"],
        "config": {"multihop": cfg["multihop"], "amounts": cfg["amounts"],
                   "stress": cfg["stress"], "tiers": cfg["tiers"]},
        "validation": validate(edges),
        "counts": {
            "edges": int(len(edges)),
            "by_tier": edges.evidence_tier.value_counts().to_dict() if len(edges) else {},
            "by_status": edges.status.value_counts().to_dict() if len(edges) else {},
            "by_type": edges.edge_type.value_counts().to_dict() if len(edges) else {},
            "undisclosed_amount": int((edges.amount_usd_high == 0).sum()) if len(edges) else 0,
        },
        "cannot_see": cannot_see(),
    }
    p = SITE_DATA / "ledger.json"
    p.write_text(json.dumps(payload, default=str))
    LOG.info("wrote %s (%d edges, %d nodes)", p, len(edge_rows), len(node_rows))
    from deal_agent.pending import export as export_pending
    export_pending({**cfg, "_root": ROOT}, SITE_DATA)
    return payload


def cannot_see() -> list[dict]:
    """The blind spots, written down. Each is a specific, checkable gap."""
    return [
        {"gap": "Oracle names no customer, anywhere",
         "detail": ("Oracle discloses $664 billion of remaining performance "
                    "obligations and the words OpenAI appear in none of its filings "
                    "retrieved here. Its round-trip exposure is unmeasurable, not low."),
         "size_usd": 664e9, "affects": ["Oracle"]},
        {"gap": "Broadcom gives no customer split",
         "detail": ("$179.2 billion of RPO including a long-term custom AI "
                    "accelerator contract, with no customer named and no split. Its "
                    "8-K confirms Anthropic will access about 3.5 gigawatts through "
                    "Broadcom, with no dollar figure attached."),
         "size_usd": 179.2e9, "affects": ["Broadcom"]},
        {"gap": "CoreWeave's largest customer is anonymous",
         "detail": ("Customer A was 36% of revenue in Q2 2026 and 67% of 2025 "
                    "revenue. CoreWeave labels customers A to D and never names "
                    "them, and no counterparty filing names CoreWeave as a buyer of "
                    "that size."),
         "size_usd": None, "affects": ["CoreWeave"]},
        {"gap": "Private labs file nothing",
         "detail": ("OpenAI, Anthropic and xAI file no periodic reports. Every "
                    "figure about them here comes from a counterparty's filing or "
                    "their own release, so their total funding is a documented "
                    "subset, never a complete picture, and every number touching "
                    "them is a range."),
         "size_usd": None, "affects": ["OpenAI", "Anthropic", "xAI"]},
        {"gap": "Alphabet's Anthropic stake is unquantified here",
         "detail": ("Alphabet names Anthropic in no filing retrieved, and no "
                    "Alphabet or Anthropic release found states an Alphabet "
                    "investment amount. Alphabet's non-marketable securities rose "
                    "from $68.7 billion to $131.5 billion in the first half of 2026 "
                    "with no attribution. No edge was recorded, which means "
                    "Alphabet's measured exposure is zero and almost certainly "
                    "understated."),
         "size_usd": None, "affects": ["Alphabet", "Anthropic"]},
        {"gap": "Share-denominated warrants carry no dollar value",
         "detail": ("AMD's warrants to OpenAI and Meta are 160 million shares each "
                    "at $0.01, and AMD states they had no impact on its financial "
                    "statements. They are recorded at zero dollars, so they move the "
                    "UPPER bound through the funding-link test but contribute "
                    "nothing to LOWER or CENTRAL."),
         "size_usd": None, "affects": ["AMD", "OpenAI", "Meta"]},
        {"gap": "Nvidia and AMD disclose no product backlog",
         "detail": ("Both sell data centre systems on purchase orders. Their tagged "
                    "RPO covers software and services only ($3.2 billion and $222 "
                    "million). The two companies most associated with vendor "
                    "financing therefore have no measurable backlog denominator at "
                    "all, which is why they carry no headline number here."),
         "size_usd": None, "affects": ["Nvidia", "AMD"]},
        {"gap": "Backlog dates lag deal dates",
         "detail": ("Nebius's RPO is dated 31 December 2025 but its Meta agreement "
                    "is from March 2026; Nscale's RPO is dated 30 June 2026 but its "
                    "Anthropic agreement is from August 2026. Both show dependency "
                    "row sums above 1, flagged rather than rescaled."),
         "size_usd": None, "affects": ["Nebius", "Nscale"]},
        {"gap": "Unnamed counterparties in real disclosures",
         "detail": ("Nvidia discloses $36 billion of multi-year cloud service "
                    "commitments to AI cloud partners and $3.5 billion of lease "
                    "guarantees for them without naming which. Oracle discloses "
                    "$288 billion of lease commitments not yet commenced. None of "
                    "it can be attached to a counterparty."),
         "size_usd": 327.5e9, "affects": ["Nvidia", "Oracle"]},
    ]


def main() -> None:
    build()


if __name__ == "__main__":
    main()
