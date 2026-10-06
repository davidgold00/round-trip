"""Candidate review CLI. The ONLY path from candidate to ledger.

    python -m src.review list                 show pending candidates
    python -m src.review show <candidate_id>  print the full context window
    python -m src.review promote <id> --quote "..." [overrides]
    python -m src.review reject  <id> --reason "..."
    python -m src.review batch ledger/promotions.yaml
    python -m src.review verify               re-run ledger validation

Every promotion requires a quote of fewer than 25 words. A T1 promotion
requires an accession number. Nothing is ever promoted automatically:
`src/extract.py` cannot write to edges.csv, and this module refuses a promotion
without a quote.
"""
from __future__ import annotations

import argparse
import csv
import sys
import textwrap
from pathlib import Path

import yaml

from .ledger import (BACKLOG_FIELDS, EDGE_FIELDS, EDGE_TYPES, STATUSES, TIERS,
                     BASES, load_edges, validate, write_edges)
from .util import ROOT, edge_id, get_logger

LOG = get_logger("review")

LEDGER = ROOT / "ledger"
CAND = LEDGER / "candidates.csv"
NEWS_CAND = LEDGER / "news_candidates.csv"
EDGES = LEDGER / "edges.csv"
BACKLOG = LEDGER / "backlog.csv"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def read_candidates() -> list[dict]:
    """Both queues: filing-derived candidates and news-monitor candidates.

    A candidate id beginning with `n_` comes from the news monitor and lives in
    ledger/news_candidates.csv; `c_` ids come from the filing extractor. The
    review commands accept either, so a reviewer never has to know which file a
    candidate is in.
    """
    rows = _read(CAND)
    for r in _read(NEWS_CAND):
        r.setdefault("queue", "news")
        rows.append(r)
    return rows


def write_candidates(rows: list[dict]) -> None:
    """Write each row back to the queue it came from, keyed by id prefix."""
    for path, subset in ((CAND, [r for r in rows if not r["candidate_id"].startswith("n_")]),
                         (NEWS_CAND, [r for r in rows if r["candidate_id"].startswith("n_")])):
        if not subset:
            continue
        existing = _read(path)
        fields = list(existing[0].keys()) if existing else list(subset[0].keys())
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(subset)


def check_quote(quote: str) -> None:
    q = (quote or "").strip()
    if not q:
        raise SystemExit("refused: a promotion needs a verbatim quote from the source")
    if len(q.split()) >= 25:
        raise SystemExit(f"refused: quote is {len(q.split())} words, limit is 24")


def check_row(row: dict) -> None:
    if row["edge_type"] not in EDGE_TYPES:
        raise SystemExit(f"refused: bad edge_type {row['edge_type']!r}")
    if row["status"] not in STATUSES:
        raise SystemExit(f"refused: bad status {row['status']!r}")
    if row["evidence_tier"] not in TIERS:
        raise SystemExit(f"refused: bad evidence_tier {row['evidence_tier']!r}")
    if row["amount_basis"] not in BASES:
        raise SystemExit(f"refused: bad amount_basis {row['amount_basis']!r}")
    if row["evidence_tier"] == "T4":
        raise SystemExit("refused: T4 evidence is never admitted to the ledger")
    if row["evidence_tier"] == "T1" and not str(row.get("accession_no", "")).strip():
        raise SystemExit("refused: T1 rows require an accession_no")
    if not str(row.get("source_url", "")).startswith("http"):
        raise SystemExit("refused: source_url must be an http(s) link")
    if row["source_node"] == row["target_node"]:
        raise SystemExit("refused: self-edges are not meaningful here")
    check_quote(row.get("quote_snippet", ""))


def append_edge(row: dict) -> None:
    for k in EDGE_FIELDS:
        row.setdefault(k, "")
    if not row.get("edge_id"):
        row["edge_id"] = edge_id(row["source_node"], row["target_node"],
                                 row["edge_type"], row["as_of_date"])
    check_row(row)
    df = load_edges()
    existing = set(df["edge_id"]) if len(df) else set()
    if row["edge_id"] in existing:
        LOG.info("edge %s already present, updating in place", row["edge_id"])
        for k in EDGE_FIELDS:
            df.loc[df.edge_id == row["edge_id"], k] = row[k]
    else:
        import pandas as pd
        df = pd.concat([df, pd.DataFrame([{k: row[k] for k in EDGE_FIELDS}])],
                       ignore_index=True)
    write_edges(df)
    LOG.info("ledger now holds %d edges (added/updated %s)", len(df), row["edge_id"])


def append_backlog(row: dict) -> None:
    for k in BACKLOG_FIELDS:
        row.setdefault(k, "")
    check_quote(row.get("quote_snippet", ""))
    rows: list[dict] = []
    if BACKLOG.exists():
        with open(BACKLOG) as fh:
            rows = list(csv.DictReader(fh))
    key = (row["node"], row["as_of_date"], row["metric"])
    rows = [r for r in rows if (r["node"], r["as_of_date"], r["metric"]) != key]
    rows.append({k: row.get(k, "") for k in BACKLOG_FIELDS})
    rows.sort(key=lambda r: (r["node"], r["as_of_date"], r["metric"]))
    with open(BACKLOG, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=BACKLOG_FIELDS)
        w.writeheader()
        w.writerows(rows)
    LOG.info("backlog table now holds %d rows", len(rows))


def cmd_list(args) -> None:
    rows = read_candidates()
    pending = [r for r in rows if r.get("review_status") == "pending"]
    pending.sort(key=lambda r: -float(r.get("amount_usd_high") or 0))
    print(f"{len(pending)} pending of {len(rows)} candidates "
          f"({sum(1 for r in rows if r.get('review_status')=='promoted')} promoted, "
          f"{sum(1 for r in rows if r.get('review_status')=='rejected')} rejected)\n")
    for r in pending[: args.limit]:
        amt = float(r.get("amount_usd_high") or 0)
        print(f"{r['candidate_id']}  {r['source_node']:>10} -> {r['target_node']:<10} "
              f"{r['edge_type']:<24} ${amt/1e9:8.2f}B  {r['status']:<15} "
              f"{r['filer_node']} {r['form']} {r['as_of_date']}")


def cmd_show(args) -> None:
    for r in read_candidates():
        if r["candidate_id"] == args.candidate_id:
            print(f"{r['source_node']} -> {r['target_node']}  [{r['edge_type']}]")
            print(f"amount ${float(r['amount_usd_high'] or 0):,.0f}  status {r['status']}")
            print(f"filer {r['filer_node']} {r['form']} {r['as_of_date']} {r['accession_no']}")
            print(r["source_url"])
            print(f"rule hit: {r['rule_hit']}\n")
            print(textwrap.fill(r["context_window"], 100))
            return
    raise SystemExit(f"no candidate {args.candidate_id}")


def _mark(cid: str, status: str, reason: str, quote: str = "") -> dict | None:
    rows = read_candidates()
    hit = None
    for r in rows:
        if r["candidate_id"] == cid:
            r["review_status"] = status
            r["review_reason"] = reason
            if quote:
                r["quote_snippet"] = quote
            hit = dict(r)
    if hit is None:
        raise SystemExit(f"no candidate {cid}")
    write_candidates(rows)
    return hit


def cmd_promote(args) -> None:
    check_quote(args.quote)
    row = _mark(args.candidate_id, "promoted", args.reason or "verified against source text",
                args.quote)
    for field in ("source_node", "target_node", "edge_type", "status", "amount_basis",
                  "evidence_tier", "term_start", "term_end", "conditions_text", "notes"):
        val = getattr(args, field, None)
        if val:
            row[field] = val
    if args.amount_low is not None:
        row["amount_usd_low"] = args.amount_low
    if args.amount_high is not None:
        row["amount_usd_high"] = args.amount_high
    row["quote_snippet"] = args.quote
    append_edge(row)


def cmd_reject(args) -> None:
    _mark(args.candidate_id, "rejected", args.reason)
    LOG.info("rejected %s: %s", args.candidate_id, args.reason)


def cmd_batch(args) -> None:
    """Apply a reviewed promotions file.

    Each entry is a row the reviewer has personally checked against the source.
    `from_candidate` links an entry back to an extractor candidate and marks it
    promoted; entries without it are manual additions, which still require a
    source_url, a quote and (for T1) an accession number.
    """
    doc = yaml.safe_load(Path(args.path).read_text()) or {}
    n_edges = n_back = n_rej = 0
    for entry in doc.get("edges", []):
        cid = entry.pop("from_candidate", None)
        if cid:
            _mark(cid, "promoted", entry.get("notes", "verified against source text"),
                  entry.get("quote_snippet", ""))
        append_edge(dict(entry))
        n_edges += 1
    for entry in doc.get("backlog", []):
        append_backlog(dict(entry))
        n_back += 1
    for entry in doc.get("rejections", []):
        _mark(entry["candidate_id"], "rejected", entry["reason"])
        n_rej += 1
    LOG.info("batch applied: %d edges, %d backlog rows, %d rejections",
             n_edges, n_back, n_rej)
    cmd_verify(args)


def cmd_verify(args) -> None:
    problems = validate(load_edges())
    if problems:
        print(f"{len(problems)} validation problems:")
        for p in problems:
            print("  -", p)
        sys.exit(1 if getattr(args, "strict", False) else 0)
    print("ledger validates clean")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m src.review", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show"); p.add_argument("candidate_id"); p.set_defaults(func=cmd_show)

    p = sub.add_parser("promote")
    p.add_argument("candidate_id")
    p.add_argument("--quote", required=True, help="verbatim source quote, under 25 words")
    p.add_argument("--reason", default="")
    for field in ("source_node", "target_node", "edge_type", "status", "amount_basis",
                  "evidence_tier", "term_start", "term_end", "conditions_text", "notes"):
        p.add_argument(f"--{field.replace('_', '-')}", dest=field, default=None)
    p.add_argument("--amount-low", type=float, default=None)
    p.add_argument("--amount-high", type=float, default=None)
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("reject"); p.add_argument("candidate_id")
    p.add_argument("--reason", required=True); p.set_defaults(func=cmd_reject)

    p = sub.add_parser("batch"); p.add_argument("path"); p.set_defaults(func=cmd_batch)

    p = sub.add_parser("verify"); p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
