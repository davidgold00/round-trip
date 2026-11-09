"""Read-only static snapshot of the local pending queue, never ledger input."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .io import atomic_write
from .trace import stamp


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
            for deal_json, check_json, created in connection.execute(
                "SELECT deal,verification,created FROM candidates WHERE status='pending' ORDER BY created DESC,id DESC LIMIT ?", (limit,)
            ):
                deal, checked = json.loads(deal_json), json.loads(check_json)
                result["items"].append({
                    "source_entity": deal["source_entity"], "target_entity": deal["target_entity"],
                    "deal_type": deal["deal_type"], "amount_text": deal["amount_text"],
                    "evidence_quote": deal["evidence_quote"][:600], "source_url": deal["source_url"],
                    "verification_status": "passed" if checked.get("passed") else "failed",
                    "created": created,
                })
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
