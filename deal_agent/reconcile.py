"""Conservative, explainable relationship matching; no fuzzy automatic updates."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .models import LEGACY_TYPE


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normal_row(row: dict, resolver) -> dict:
    if "deal" in row:
        deal = row["deal"]
        return {
            **deal,
            "source_node": resolver.resolve(deal["source_entity"]),
            "target_node": resolver.resolve(deal["target_entity"]),
            "edge_type": LEGACY_TYPE.get(deal["deal_type"]),
            "match_id": row["id"],
            "queue": "agent",
        }
    return {
        **row,
        "source_node": resolver.resolve(row.get("source_node", "")),
        "target_node": resolver.resolve(row.get("target_node", "")),
        "announced_date": row.get("as_of_date", ""),
        "match_id": row.get("edge_id") or row.get("candidate_id"),
        "queue": "legacy" if row.get("candidate_id") else "graph",
    }


def reconcile(
    deal: dict, graph: list[dict], pending: list[dict], resolver, update_days: int = 365
) -> dict:
    source, target = (
        resolver.resolve(deal["source_entity"]),
        resolver.resolve(deal["target_entity"]),
    )
    kind = LEGACY_TYPE.get(deal["deal_type"])
    if not source or not target:
        return {
            "classification": "NEW",
            "match_id": None,
            "reason": "Unresolved entities; review required",
        }
    matches = []
    related = []
    for raw in [*graph, *pending]:
        row = normal_row(raw, resolver)
        if (row["source_node"], row["target_node"]) != (source, target):
            continue
        # A specific extracted subtype is more precise than the legacy family.
        # Legacy-only rows can still match through the documented type mapping.
        if row.get("deal_type"):
            if row["deal_type"] != deal["deal_type"]:
                continue
        elif kind is None or row.get("edge_type") != kind:
            continue
        related.append(row)
        same_url = deal["source_url"] == row.get("source_url")
        same_date = str(deal["announced_date"]) == str(row.get("announced_date"))
        if same_date or (same_url and not row.get("announced_date")):
            matches.append(row)
    if not matches and any(
        word in deal["evidence_quote"].casefold()
        for word in ("expanded", "expands", "amended", "increased")
    ):
        # Expansion is an UPDATE only with a unique plausible antecedent. A new
        # order form may instead be incremental: the reviewer decides, never sum.
        for row in related:
            try:
                gap = (
                    date.fromisoformat(str(deal["announced_date"]))
                    - date.fromisoformat(str(row["announced_date"]))
                ).days
                if 0 < gap <= update_days:
                    matches.append(row)
            except ValueError:
                continue
    if len(matches) != 1:
        return {
            "classification": "NEW",
            "match_id": None,
            "reason": (
                f"{len(matches)} plausible matches; identity is ambiguous"
                if matches
                else "No same-direction, same-type deal with shared source/date or unique expansion antecedent"
            ),
            "related_ids": [r["match_id"] for r in related],
        }
    row = matches[0]
    amount = deal["amount_usd"]
    prior_amount = row.get("amount_usd")
    if prior_amount in (None, "") and row.get("amount_usd_high") not in (None, ""):
        prior_amount = float(row["amount_usd_high"])
    prior_amount = None if prior_amount == "" else prior_amount
    same_amount = (amount is None and prior_amount in (None, 0)) or (
        amount is not None
        and prior_amount is not None
        and float(amount) == float(prior_amount)
    )
    classification = "DUPLICATE" if same_amount else "UPDATE"
    return {
        "classification": classification,
        "match_id": row["match_id"],
        "match_queue": row["queue"],
        "reason": f"Same directed pair/type and shared source/date or explicit expansion; "
        f"{'same' if same_amount else 'changed'} disclosed amount. Verify contract identity and incremental vs total value.",
    }
