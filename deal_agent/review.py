"""The only agent module allowed to publish a human-approved ledger change."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

from src.ledger import EDGE_FIELDS, EXTENDED_EDGE_FIELDS, validate
from src.review import check_row
from src.util import edge_id

from .config import path_for
from .models import Deal, LEGACY_TYPE, parse_json
from .io import atomic_write, lock
from .reconcile import read_csv, reconcile
from .store import encode
from .trace import digest, stamp
from .verify import verify, whitespace


def csv_text(rows: list[dict]) -> str:
    handle = io.StringIO(newline="")
    fields = list(
        dict.fromkeys([*EXTENDED_EDGE_FIELDS, *(key for row in rows for key in row)])
    )
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def recover(store, graph: Path):
    """Recover an interrupted approval without publishing an unreviewed change."""
    for event in store.rows("SELECT * FROM audit WHERE state='prepared' ORDER BY id"):
        payload = json.loads(event["payload"])
        current = digest(graph.read_bytes())
        if str(graph.resolve()) != payload["graph_path"]:
            raise RuntimeError("Prepared approval belongs to another graph path")
        if current == payload["after_hash"]:
            store.db.execute("BEGIN IMMEDIATE")
            try:
                store.db.execute(
                    "UPDATE candidates SET status='approved' WHERE id=?",
                    (event["candidate_id"],),
                )
                store.db.execute(
                    "UPDATE audit SET state='applied' WHERE id=?", (event["id"],)
                )
                store.db.execute("COMMIT")
            except Exception:
                store.db.execute("ROLLBACK")
                raise
        elif current == payload["before_hash"]:
            # No file write happened: leave the item pending for human review.
            store.db.execute(
                "UPDATE audit SET state='aborted' WHERE id=?", (event["id"],)
            )
        else:
            raise RuntimeError(
                "Interrupted approval conflicts with later graph edits; inspect audit before continuing"
            )


class Review:
    def __init__(self, pipeline, actor: str):
        if not actor.strip():
            raise ValueError("Reviewer identity is required")
        self.pipeline, self.store, self.trace = pipeline, pipeline.store, pipeline.trace
        self.cfg, self.resolver, self.actor = pipeline.cfg, pipeline.resolver, actor
        self.graph = path_for(self.cfg, "graph_file")
        # Reviewing after a crash first reconciles the already-approved file
        # operation with queue state. This never applies a new graph mutation.
        with lock(self.graph.with_suffix(".csv.lock")):
            recover(self.store, self.graph)

    def candidate(self, candidate_id):
        for row in self.store.candidates():
            if row["id"] == candidate_id:
                return row
        raise ValueError(f"No pending candidate {candidate_id}")

    def context(self, row):
        doc = self.store.rows(
            "SELECT * FROM documents WHERE id=?", (row["document_id"],)
        )[0]
        text = self.trace.call(
            "review.read_source",
            {"path": doc["text_path"]},
            lambda: Path(doc["text_path"]).read_text(),
            summarize=lambda value: {"sha256": digest(value), "characters": len(value)},
        )
        if digest(text) != row["document_id"]:
            raise ValueError(
                "Stored document hash mismatch; restore original source before reviewing"
            )
        return text, json.loads(doc["meta"])

    def current_check(self, row):
        text, meta = self.context(row)
        deal = Deal.model_validate_json(encode(row["deal"]))
        checked = self.trace.call(
            "review.verify",
            row["deal"],
            lambda: verify(
                deal, text, self.resolver, meta["source_url"], meta.get("company")
            ),
        )
        pending = [r for r in self.store.candidates() if r["id"] != row["id"]]
        # Published graph matches take precedence over duplicate pending copies.
        graph = self.trace.call(
            "review.read_graph", {"path": str(self.graph)}, lambda: read_csv(self.graph)
        )
        rec = reconcile(
            row["deal"],
            graph,
            [],
            self.resolver,
            self.cfg["deal_agent"]["update_match_days"],
        )
        if rec["classification"] == "NEW":
            rec = reconcile(
                row["deal"],
                graph,
                [*self.pipeline.legacy, *pending],
                self.resolver,
                self.cfg["deal_agent"]["update_match_days"],
            )
        return checked, rec

    def show(self, row):
        checked, rec = self.current_check(row)
        print(
            encode({**row, "current_verification": checked, "current_reconcile": rec})
        )
        print("Evidence:", row["deal"]["evidence_quote"])
        print("Source:", row["deal"]["source_url"])

    def audit(self, candidate_id, action, payload, state="applied"):
        return self.store.db.execute(
            "INSERT INTO audit VALUES(NULL,?,?,?,?,?,?)",
            (candidate_id, self.actor, action, stamp(), encode(payload), state),
        ).lastrowid

    def edit(self, candidate_id: str, path: Path, reason: str):
        row = self.candidate(candidate_id)
        deal = parse_json(path.read_text(), Deal).model_dump(mode="json")
        after = {**row, "deal": deal}
        checked, rec = self.current_check(after)
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            self.audit(
                candidate_id, "edit", {"before": row, "after": after, "reason": reason}
            )
            self.store.db.execute(
                "UPDATE candidates SET deal=?,verification=?,reconcile=? WHERE id=?",
                (encode(deal), encode(checked), encode(rec), candidate_id),
            )
            self.store.db.execute("COMMIT")
        except Exception:
            self.store.db.execute("ROLLBACK")
            raise
        self.trace.event(
            "review.edit",
            {"candidate": candidate_id},
            {"deal": deal, "verification": checked},
        )

    def reject(self, candidate_id: str, reason: str):
        row = self.candidate(candidate_id)
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            self.audit(candidate_id, "reject", {"before": row, "reason": reason})
            self.store.db.execute(
                "UPDATE candidates SET status='rejected' WHERE id=?", (candidate_id,)
            )
            self.store.db.execute("COMMIT")
        except Exception:
            self.store.db.execute("ROLLBACK")
            raise
        self.trace.event(
            "review.reject", {"candidate": candidate_id}, {"reason": reason}
        )

    def approve(
        self,
        candidate_id,
        *,
        quote,
        status,
        basis,
        low,
        high,
        reason,
        target_edge=None,
        new_edge=False,
        legacy_type=None,
        term_start="",
        term_end="",
    ):
        if not reason.strip():
            raise ValueError("Record a review reason")
        with lock(self.graph.with_suffix(".csv.lock")):
            recover(self.store, self.graph)
            row = self.candidate(candidate_id)
            checked, rec = self.current_check(row)
            if not checked["passed"]:
                raise ValueError(
                    "Verification failed; edit the candidate first: "
                    + "; ".join(checked["errors"])
                )
            text, meta = self.context(row)
            deal = row["deal"]
            if whitespace(quote) not in whitespace(deal["evidence_quote"]):
                raise ValueError(
                    "Publication quote must be a verbatim substring of the verified evidence"
                )
            if not quote.strip():
                raise ValueError("Publication quote cannot be empty")
            if not all(math.isfinite(v) and v >= 0 for v in (low, high)) or low > high:
                raise ValueError(
                    "Amount bounds must be finite, nonnegative and low <= high"
                )
            if deal["amount_usd"] is None and (low != 0 or high != 0):
                raise ValueError(
                    "No extracted USD amount; edit and verify the amount before assigning dollar bounds"
                )
            if deal["amount_usd"] is not None and high > deal["amount_usd"]:
                raise ValueError(
                    "Upper bound exceeds the verified disclosed amount; edit the candidate first"
                )
            if target_edge and new_edge:
                raise ValueError("Choose a target update OR a new edge")
            if rec["classification"] == "DUPLICATE" and not (target_edge or new_edge):
                raise ValueError(
                    "Duplicate: reject it, or explicitly choose --target-edge/--new-edge with a reason"
                )
            if rec["classification"] == "UPDATE" and not (target_edge or new_edge):
                raise ValueError(
                    "Potential update: choose --target-edge or --new-edge after reading the contract"
                )
            mapped = legacy_type or LEGACY_TYPE.get(deal["deal_type"])
            if not mapped:
                raise ValueError(
                    "This deal type needs an analyst-supplied --edge-type in the legacy taxonomy"
                )
            graph = read_csv(self.graph)
            previous = next((e for e in graph if e["edge_id"] == target_edge), None)
            if target_edge and not previous:
                raise ValueError(
                    f"No graph edge {target_edge}; pending candidates are not published edges"
                )
            if previous and (previous["source_node"], previous["target_node"]) != (
                checked["source_node"],
                checked["target_node"],
            ):
                raise ValueError("Update target has a different directed entity pair")
            from datetime import date

            for value in (term_start, term_end):
                if value:
                    date.fromisoformat(value)
            if basis == "per-year" and (not term_start or not term_end):
                raise ValueError(
                    "Per-year amounts need explicit term_start and term_end"
                )
            if term_start and term_end and term_end <= term_start:
                raise ValueError("term_end must follow term_start")
            exported = {key: "" for key in EDGE_FIELDS}
            exported.update(
                edge_id=(
                    target_edge
                    or edge_id(
                        checked["source_node"],
                        checked["target_node"],
                        mapped,
                        deal["announced_date"],
                    )
                ),
                as_of_date=deal["announced_date"],
                source_node=checked["source_node"],
                target_node=checked["target_node"],
                edge_type=mapped,
                amount_usd_low=low,
                amount_usd_high=high,
                amount_basis=basis,
                status=status,
                term_start=term_start,
                term_end=term_end,
                evidence_tier=meta["evidence_tier"],
                source_url=meta["source_url"],
                accession_no=meta.get("accession_no", ""),
                quote_snippet=quote,
                notes=f"Human reviewed by {self.actor}: {reason}",
                deal_type=deal["deal_type"],
                consideration_type=deal["consideration_type"],
                amount_usd=deal["amount_usd"] if deal["amount_usd"] is not None else "",
                amount_text=deal["amount_text"],
                term_or_duration=deal["term_or_duration"] or "",
                announced_date=deal["announced_date"],
                evidence_quote=deal["evidence_quote"],
                confidence=deal["confidence"],
                extraction_rationale=deal["rationale"],
                agent_candidate_id=candidate_id,
                document_sha256=row["document_id"],
            )
            check_row(exported)  # Existing short-quote, tier, accession and type gates.
            if not target_edge and any(
                e["edge_id"] == exported["edge_id"] for e in graph
            ):
                if not new_edge:
                    raise ValueError(
                        "Edge id already exists; choose an explicit update or --new-edge"
                    )
                # Distinct same-day tranches/contracts can share pair and type.
                # The reviewer explicitly chose a separate edge; preserve the
                # legacy id and use a stable candidate suffix for the new one.
                exported["edge_id"] += "__" + candidate_id[2:10]
                if any(e["edge_id"] == exported["edge_id"] for e in graph):
                    raise ValueError("This distinct edge id already exists")
            updated = [e for e in graph if e["edge_id"] != target_edge] + [exported]
            import pandas as pd

            frame = pd.DataFrame(updated)
            for key in ("amount_usd_low", "amount_usd_high"):
                frame[key] = pd.to_numeric(frame[key])
            problems = validate(frame)
            if problems:
                raise ValueError("Ledger validation failed: " + "; ".join(problems))
            before = self.graph.read_bytes()
            after = csv_text(updated)
            payload = {
                "candidate": row,
                "before": previous,
                "after": exported,
                "reason": reason,
                "reconcile": rec,
                "graph_path": str(self.graph.resolve()),
                "before_hash": digest(before),
                "after_hash": digest(after),
                "publication": "run publish after approval",
            }
            # A committed intent plus atomic replacement is recoverable even if
            # the process dies between the CSV and SQLite commits.
            event_id = self.audit(
                candidate_id,
                "update" if target_edge else "approve",
                payload,
                "prepared",
            )
            if digest(self.graph.read_bytes()) != digest(before):
                raise RuntimeError(
                    "Graph changed during review; re-review against current data"
                )
            self.trace.call(
                "review.apply_graph", payload, lambda: atomic_write(self.graph, after)
            )
            recover(self.store, self.graph)
            return event_id
