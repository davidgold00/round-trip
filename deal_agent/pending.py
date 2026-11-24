"""Expose read-only views of proposals waiting for human review.
Read the local SQLite queue and the configured legacy candidate tables.
Supply the dashboard snapshot and the combined command-line inbox.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import sqlite3

from .io import atomic_write
from .trace import stamp
from .verify import MONEY, dollars, whitespace


def amount_reading(deal):
    """Display the amount and its nearby source qualifier without assigning bounds."""
    from decimal import Decimal

    amount = deal.get("amount_usd")
    if amount is None:
        return "No USD value proposed"
    quote = whitespace(deal["evidence_quote"])
    matches = [m for m in MONEY.finditer(quote) if Decimal(str(amount)) in dollars(m[0])]
    if len(matches) != 1:
        return f"Proposed USD {amount:,.0f} · check the figure against the source"
    match = matches[0]
    prefix = re.search(r"\b(?:up to|at least|more than|approximately|an additional|a new|in aggregate|a total of)\s+$",
                       quote[:match.start()], re.I)
    return quote[prefix.start() if prefix else match.start():match.end()].strip()


def review_item(candidate_id, deal, checked, rec):
    return {
        "id": candidate_id, "source_entity": deal["source_entity"], "target_entity": deal["target_entity"],
        "deal_type": deal["deal_type"], "amount_text": deal["amount_text"], "amount_reading": amount_reading(deal),
        "evidence_quote": deal["evidence_quote"], "source_url": deal["source_url"],
        "verification_status": "passed" if checked.get("passed") else "failed",
        "failed_checks": checked.get("errors", []), "classification": rec.get("classification"),
        "match_id": rec.get("match_id"), "match_queue": rec.get("match_queue"),
        "reconciliation_reason": rec.get("reason"),
    }


def snapshot(cfg, limit=5):
    root = cfg["_root"]
    path = root / cfg.get("deal_agent", {}).get("state_db", "data/deal_agent/queue.sqlite3")
    result = {"generated": stamp(), "available": True, "pending_count": 0, "items": [],
              "note": "Read-only snapshot. Unverified candidates are excluded from every published metric."}
    if not path.exists():
        result["note"] += " No local agent queue has been created."
        return result
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            result["pending_count"] = connection.execute("SELECT count(*) FROM candidates WHERE status='pending'").fetchone()[0]
            for candidate_id, deal, checked, rec, created in connection.execute(
                "SELECT id,deal,verification,reconcile,created FROM candidates WHERE status='pending' "
                "ORDER BY created DESC,id DESC LIMIT ?", (limit,)
            ):
                item = review_item(candidate_id, json.loads(deal), json.loads(checked), json.loads(rec))
                result["items"].append({**item, "created": created})
        finally:
            connection.close()
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        result.update(available=False, pending_count=None, items=[],
                      note="Pending review snapshot unavailable. Rebuild after checking the local queue.")
    return result


def export(cfg, directory=None):
    directory = Path(directory) if directory else cfg["_root"] / "site/data"
    payload = snapshot(cfg)
    atomic_write(directory / "pending_agent.json", json.dumps(payload, indent=2) + "\n")
    return payload

def inbox(cfg):
    """Read both storage formats without creating a database or exporting a file."""
    from .reconcile import read_csv

    result = []
    for name in cfg["deal_agent"]["legacy_queues"]:
        for row in read_csv(cfg["_root"] / name):
            if row.get("review_status") == "pending":
                key = row["candidate_id"]
                result.append({"id": key, "source": row["source_node"], "target": row["target_node"],
                               "inspect": f"python -m src.review show {key}"})
    pending = snapshot(cfg, limit=-1)
    if not pending["available"]:
        raise RuntimeError(pending["note"])
    for row in pending["items"]:
        key = row["id"]
        result.append({"id": key, "source": row["source_entity"], "target": row["target_entity"],
                       "inspect": f"python -m deal_agent review show {key}"})
    return result
