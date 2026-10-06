"""Seed entities and programmatic CIK/ticker resolution from SEC data.

The seed list is a set of HYPOTHESES about where round-trip structures might
exist. Nothing here is evidence. Additional nodes are discovered from filings
during ingestion and appended to ledger/nodes.csv with a reason.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .sec_client import SecClient
from .util import ROOT, get_logger

LOG = get_logger("entities")

# name -> (ticker hint, role, is_filer)
# ticker hint is used only to look the company up in SEC's own company_tickers
# file; the CIK is always taken from SEC data, never hardcoded.
SEED = {
    "Nvidia":     ("NVDA",  "supplier", True),
    "AMD":        ("AMD",   "supplier", True),
    "Broadcom":   ("AVGO",  "supplier", True),
    "Oracle":     ("ORCL",  "both",     True),
    "CoreWeave":  ("CRWV",  "both",     True),
    "Nebius":     ("NBIS",  "both",     True),
    "Microsoft":  ("MSFT",  "both",     True),
    "Amazon":     ("AMZN",  "both",     True),
    "Alphabet":   ("GOOGL", "both",     True),
    "Meta":       ("META",  "buyer",    True),
    # Non-filers. They do not file with the SEC, so every number touching them
    # comes from a counterparty's filing or release, and is reported as a range.
    "OpenAI":     (None,    "buyer",    False),
    "Anthropic":  (None,    "buyer",    False),
    "xAI":        (None,    "buyer",    False),
    "SoftBank":   (None,    "investor", False),  # files 13D/G sometimes, not periodic
}

# Nodes discovered during ingestion rather than seeded. CIK comes from SEC data
# (the EDGAR archive path of a filing actually fetched), never from memory.
# Companies that have filed but are not yet listed are absent from
# company_tickers.json, so they cannot be resolved by ticker.
DISCOVERED = {
    "Nscale": {
        "cik": "0002110365",
        "ticker": "",
        "is_filer": True,
        "role": "supplier",
        "discovered_via": (
            "S-1 filed 2026-09-18 (acc 0001193125-26-395475). Surfaced while "
            "checking for newly filed neocloud registrants. Unlike the incumbent "
            "filers it names Microsoft, Anthropic and NVIDIA as counterparties "
            "WITH dollar amounts, and discloses NVIDIA warrants, an NVIDIA lease "
            "guarantee and NVIDIA convertible notes alongside an NVIDIA cloud "
            "purchase, which is the most complete round trip in the dataset."),
    },
}

# Alias table for matching company names inside filing text.
ALIASES = {
    "Nvidia": ["NVIDIA", "Nvidia Corporation", "NVDA"],
    "AMD": ["Advanced Micro Devices", "AMD"],
    "Broadcom": ["Broadcom Inc", "Broadcom"],
    "Oracle": ["Oracle Corporation", "Oracle"],
    "CoreWeave": ["CoreWeave, Inc", "CoreWeave"],
    "Nebius": ["Nebius Group", "Nebius"],
    "Microsoft": ["Microsoft Corporation", "Microsoft"],
    "Amazon": ["Amazon.com", "Amazon Web Services", "AWS", "Amazon"],
    "Alphabet": ["Alphabet Inc", "Google Cloud", "Google LLC", "Alphabet", "Google"],
    "Meta": ["Meta Platforms", "Meta"],
    "OpenAI": ["OpenAI", "OpenAI Global", "OpenAI, L.L.C.", "OpenAI OpCo"],
    "Anthropic": ["Anthropic PBC", "Anthropic"],
    "xAI": ["xAI Corp", "xAI Holdings", "X.AI", "xAI"],
    "SoftBank": ["SoftBank Group", "SoftBank Vision Fund", "SoftBank"],
    # Discovered / adjacent nodes worth matching if they appear.
    "Lambda": ["Lambda Labs", "Lambda, Inc"],
    "Crusoe": ["Crusoe Energy", "Crusoe"],
    "Vantage": ["Vantage Data Centers"],
    "Blue Owl": ["Blue Owl Capital"],
    "MGX": ["MGX", "MGX Fund"],
    "Mistral": ["Mistral AI"],
    "Cohere": ["Cohere Inc"],
    "Scale AI": ["Scale AI"],
    "Figure AI": ["Figure AI"],
    "Wayve": ["Wayve Technologies"],
    "Applied Digital": ["Applied Digital"],
    "IREN": ["IREN Limited", "Iris Energy"],
    "Cipher Mining": ["Cipher Mining"],
    "TeraWulf": ["TeraWulf"],
    "Fluidstack": ["Fluidstack"],
    "Intel": ["Intel Corporation"],
    "Nscale": ["Nscale Limited", "Nscale Global", "Nscale"],
}

NODES_CSV = ROOT / "ledger" / "nodes.csv"
NODE_FIELDS = ["node", "cik", "ticker", "is_filer", "role", "discovered_via"]


def resolve_ciks(client: SecClient | None = None) -> dict[str, dict]:
    """Resolve seed tickers to CIKs using SEC's own company_tickers.json."""
    client = client or SecClient()
    data = client.company_tickers() or {}
    by_ticker: dict[str, dict] = {}
    for rec in data.values():
        by_ticker[str(rec["ticker"]).upper()] = {
            "cik": str(rec["cik_str"]).zfill(10),
            "title": rec["title"],
        }
    out: dict[str, dict] = {}
    for name, meta in DISCOVERED.items():
        out[name] = {"node": name, "cik": meta["cik"], "ticker": meta["ticker"],
                     "is_filer": str(bool(meta["is_filer"])).lower(),
                     "role": meta["role"], "discovered_via": meta["discovered_via"]}
    for name, (ticker, role, is_filer) in SEED.items():
        row = {"node": name, "cik": "", "ticker": ticker or "",
               "is_filer": str(bool(is_filer)).lower(), "role": role,
               "discovered_via": "seed hypothesis list"}
        if ticker:
            hit = by_ticker.get(ticker.upper())
            if hit:
                row["cik"] = hit["cik"]
                row["sec_title"] = hit["title"]
            else:
                LOG.warning("ticker %s for %s not found in SEC company_tickers", ticker, name)
        out[name] = row
    return out


def write_nodes(rows: dict[str, dict], extra: list[dict] | None = None) -> Path:
    NODES_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if NODES_CSV.exists():
        with open(NODES_CSV) as fh:
            for r in csv.DictReader(fh):
                existing[r["node"]] = r
    for name, row in rows.items():
        base = existing.get(name, {})
        merged = {k: row.get(k, base.get(k, "")) for k in NODE_FIELDS}
        if base.get("discovered_via") and base["discovered_via"] != "seed hypothesis list":
            merged["discovered_via"] = base["discovered_via"]
        existing[name] = merged
    for row in (extra or []):
        name = row["node"]
        if name in existing and existing[name].get("cik"):
            continue
        existing[name] = {k: row.get(k, "") for k in NODE_FIELDS}
    with open(NODES_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=NODE_FIELDS)
        w.writeheader()
        for name in sorted(existing):
            w.writerow({k: existing[name].get(k, "") for k in NODE_FIELDS})
    LOG.info("wrote %d nodes to %s", len(existing), NODES_CSV)
    return NODES_CSV


def load_nodes() -> list[dict]:
    if not NODES_CSV.exists():
        return []
    with open(NODES_CSV) as fh:
        return list(csv.DictReader(fh))


def filer_nodes() -> list[dict]:
    return [n for n in load_nodes() if n.get("cik")]


def alias_map() -> dict[str, str]:
    """Lowercased alias -> canonical node name, longest-first at match time."""
    out: dict[str, str] = {}
    for canon, als in ALIASES.items():
        out[canon.lower()] = canon
        for a in als:
            out[a.lower()] = canon
    return out
