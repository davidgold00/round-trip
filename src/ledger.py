"""Ledger I/O, validation, and the TCV normalisation used by every metric."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pandas as pd

from .util import ROOT, get_logger, load_config, term_years

LOG = get_logger("ledger")

LEDGER = ROOT / "ledger"
EDGES = LEDGER / "edges.csv"
BACKLOG = LEDGER / "backlog.csv"
SNAPSHOTS = LEDGER / "snapshots"

EDGE_FIELDS = [
    "edge_id", "as_of_date", "source_node", "target_node", "edge_type",
    "amount_usd_low", "amount_usd_high", "amount_basis", "term_start", "term_end",
    "status", "conditions_text", "evidence_tier", "source_url", "accession_no",
    "quote_snippet", "notes",
]
BACKLOG_FIELDS = [
    "node", "as_of_date", "metric", "amount_usd_low", "amount_usd_high",
    "evidence_tier", "source_url", "accession_no", "quote_snippet", "notes",
]

FUNDING_TYPES = {"equity_investment", "convertible_or_debt", "loan_or_guarantee",
                 "warrants", "vendor_financing"}
DEMAND_TYPES = {"purchase_commitment", "cloud_capacity_contract", "lease",
                "offtake_or_rpo"}
EDGE_TYPES = FUNDING_TYPES | DEMAND_TYPES
STATUSES = {"definitive", "conditional", "LOI_nonbinding", "announced", "reported"}
TIERS = {"T1", "T2", "T3", "T4"}
BASES = {"notional", "per-year", "cumulative", "RPO"}


def empty_edges() -> pd.DataFrame:
    return pd.DataFrame(columns=EDGE_FIELDS)


def load_edges(path: Path | None = None) -> pd.DataFrame:
    path = path or EDGES
    if not path.exists():
        return empty_edges()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in EDGE_FIELDS:
        if c not in df.columns:
            df[c] = ""
    for c in ("amount_usd_low", "amount_usd_high"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df[EDGE_FIELDS]


def load_backlog(path: Path | None = None) -> pd.DataFrame:
    path = path or BACKLOG
    if not path.exists():
        return pd.DataFrame(columns=BACKLOG_FIELDS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in BACKLOG_FIELDS:
        if c not in df.columns:
            df[c] = ""
    for c in ("amount_usd_low", "amount_usd_high"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df[BACKLOG_FIELDS]


def write_edges(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or EDGES
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for c in EDGE_FIELDS:
        if c not in out.columns:
            out[c] = ""
    out = out[EDGE_FIELDS].sort_values(["as_of_date", "source_node", "target_node"])
    out.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return path


def validate(df: pd.DataFrame) -> list[str]:
    """Structural validation. Returns a list of human-readable problems."""
    problems: list[str] = []
    if df.empty:
        return ["ledger is empty"]
    if df["edge_id"].duplicated().any():
        dups = df.loc[df["edge_id"].duplicated(), "edge_id"].tolist()
        problems.append(f"duplicate edge_id: {dups}")
    for col, allowed in (("edge_type", EDGE_TYPES), ("status", STATUSES),
                         ("evidence_tier", TIERS), ("amount_basis", BASES)):
        bad = sorted(set(df[col]) - allowed)
        if bad:
            problems.append(f"invalid {col} values: {bad}")
    neg = df[(df.amount_usd_low < 0) | (df.amount_usd_high < 0)]
    if len(neg):
        problems.append(f"{len(neg)} rows with negative amounts")
    inv = df[df.amount_usd_low > df.amount_usd_high]
    if len(inv):
        problems.append(f"{len(inv)} rows where low > high: {inv.edge_id.tolist()}")
    self_edges = df[df.source_node == df.target_node]
    if len(self_edges):
        problems.append(f"{len(self_edges)} self-edges: {self_edges.edge_id.tolist()}")
    for _, r in df.iterrows():
        if not str(r["source_url"]).startswith("http"):
            problems.append(f"{r['edge_id']}: missing or bad source_url")
        q = str(r["quote_snippet"]).strip()
        if not q:
            problems.append(f"{r['edge_id']}: missing quote_snippet")
        elif len(q.split()) >= 25:
            problems.append(f"{r['edge_id']}: quote_snippet is {len(q.split())} words (limit 25)")
        if r["evidence_tier"] == "T1" and not str(r["accession_no"]).strip():
            problems.append(f"{r['edge_id']}: T1 row without accession_no")
    return problems


def tcv(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """Add tcv_low / tcv_high on the total-contract-value basis (DECISIONS A.3)."""
    cfg = cfg or load_config()
    default_term = float(cfg["amounts"]["assumed_term_years"])
    out = df.copy()
    lows, highs, assumed = [], [], []
    for _, r in out.iterrows():
        mult, was_assumed = 1.0, False
        if r["amount_basis"] == "per-year":
            mult, was_assumed = term_years(r["term_start"], r["term_end"], default_term)
        lows.append(float(r["amount_usd_low"]) * mult)
        highs.append(float(r["amount_usd_high"]) * mult)
        assumed.append(was_assumed)
    out["tcv_low"] = lows
    out["tcv_high"] = highs
    out["term_assumed"] = assumed
    return out


def status_weight(df: pd.DataFrame, bound: str, cfg: dict | None = None) -> pd.Series:
    """Per-row status weight for a bound in {low, central, high}."""
    cfg = cfg or load_config()
    table = cfg["status_weights"]
    return df["status"].map(lambda s: float(table.get(s, {}).get(bound, 0.0)))


def filter_tiers(df: pd.DataFrame, allowed: list[str]) -> pd.DataFrame:
    """Tier gate. T4 is dropped unconditionally, even if passed in `allowed`."""
    allowed = [t for t in allowed if t != "T4"]
    return df[df["evidence_tier"].isin(allowed)].copy()


def weighted_amount(df: pd.DataFrame, bound: str, cfg: dict | None = None) -> pd.Series:
    """Status-weighted TCV for a bound. LOWER uses tcv_low, UPPER uses tcv_high."""
    cfg = cfg or load_config()
    w = status_weight(df, bound, cfg)
    col = {"low": "tcv_low", "central": "tcv_low", "high": "tcv_high"}[bound]
    if bound == "central":
        base = (df["tcv_low"] + df["tcv_high"]) / 2.0
    else:
        base = df[col]
    return base * w


def snapshot(df: pd.DataFrame, as_of: str | None = None) -> Path:
    as_of = as_of or dt.date.today().isoformat()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    p = SNAPSHOTS / f"edges_{as_of.replace('-', '')}.csv"
    write_edges(df, p)
    LOG.info("snapshot -> %s", p)
    return p
