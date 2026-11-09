"""Explicit orchestration: fetch -> chunk -> triage -> extract -> verify -> reconcile -> propose.

This module never writes the approved ledger or dashboard. It only reads those
inputs and writes SQLite candidates, raw documents and traces.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from string import Template

from .config import path_for
from .entities import Resolver
from .models import Extraction, Triage, parse_json
from .reconcile import read_csv, reconcile
from .trace import digest
from .verify import verify

PROMPTS = Path(__file__).parent / "prompts"


def chunks(text: str, size: int, overlap: int):
    """Word-boundary chunks; no prefix truncation of long filings."""
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        yield text[start:end]
        if end == len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start


class Pipeline:
    def __init__(self, cfg, store, trace, provider):
        self.cfg, self.store, self.trace, self.provider = cfg, store, trace, provider
        self.agent = cfg["deal_agent"]
        self.prompt_version = self.agent.get("prompt_version", "v1")
        if self.prompt_version not in {"v1", "v2"}:
            raise ValueError("prompt_version must be v1 or v2")
        self.prompt_dir = PROMPTS / self.prompt_version
        self.resolver = Resolver.from_csv(
            path_for(cfg, "nodes_file"), self.agent["aliases"]
        )
        self.graph = trace.call(
            "reconcile.read_graph",
            {"path": str(path_for(cfg, "graph_file"))},
            lambda: read_csv(path_for(cfg, "graph_file")),
        )
        self.legacy = []
        for name in self.agent["legacy_queues"]:
            self.legacy.extend(
                trace.call(
                    "reconcile.read_queue",
                    {"path": name},
                    lambda name=name: [
                        r
                        for r in read_csv(cfg["_root"] / name)
                        if r.get("review_status") == "pending"
                    ],
                )
            )

    def prompt(self, name, schema, text, meta, **values):
        template = (self.prompt_dir / f"{name}.txt").read_text()
        result = Template(template).substitute(
            schema=json.dumps(schema.model_json_schema()),
            text=text,
            metadata=json.dumps(meta),
            entities=json.dumps(self.agent["aliases"]),
            **values,
        )
        self.trace.event(
            "prompt", {"version": self.prompt_version, "name": name}, {"sha256": digest(template)}
        )
        return result

    def call(self, name, schema, text, meta, **values):
        prompt = self.prompt(name, schema, text, meta, **values)
        raw = self.provider.generate(prompt, schema.model_json_schema(), name)
        return self.trace.call(
            f"{name}.parse",
            {"response": raw},
            lambda: parse_json(raw, schema),
            summarize=lambda result: result.model_dump(mode="json"),
        )

    def process_text(
        self, text: str, meta: dict, document_id: str | None = None
    ) -> dict:
        """Same chunk/triage/extract/verify path for production and offline eval."""
        output = {
            "relevant": False,
            "edges": [],
            "verification_attempts": [],
            "errors": [],
        }
        for index, chunk in enumerate(
            chunks(text, self.agent["chunk_chars"], self.agent["chunk_overlap"])
        ):
            cached = self.store.chunk(document_id, index) if document_id else None
            if cached:
                self.trace.event(
                    "chunk.cache", {"document": document_id, "chunk": index}, cached
                )
                result = cached
            else:
                result = self.process_chunk(chunk, text, meta)
                if document_id and not result["errors"]:
                    self.store.save_chunk(document_id, index, result)
            output["relevant"] |= result["relevant"]
            for key in ("edges", "verification_attempts", "errors"):
                output[key].extend(result[key])
        # Merge overlap duplicates by semantic identity. Preserve EVERY failed
        # extraction attempt in the issue/trace trail, prefer a verified copy.
        merged = {}
        for edge in output["edges"]:
            deal = edge["deal"]
            key = tuple(
                str(deal[k])
                for k in (
                    "source_entity",
                    "target_entity",
                    "deal_type",
                    "amount_usd",
                    "announced_date",
                    "term_or_duration",
                )
            )
            if key not in merged or edge["verification"]["passed"]:
                merged[key] = edge
        output["edges"] = list(merged.values())
        self.trace.event("extract.merge", {"document": document_id}, output)
        return output

    def process_chunk(self, chunk, source_text, meta):
        result = {
            "relevant": False,
            "edges": [],
            "verification_attempts": [],
            "errors": [],
        }
        entities = self.resolver.mentioned(chunk)
        publisher = self.resolver.resolve(meta.get("company", ""))
        if publisher:
            entities.add(publisher)  # Resolve first-person filing/release context.
        keywords = [
            term
            for term in self.agent["keywords"]
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", chunk, re.I)
        ]
        prefilter = bool(keywords and len(entities) >= self.agent["min_entities"])
        self.trace.event(
            "triage.keyword",
            {"chunk_sha256": digest(chunk)},
            {"relevant": prefilter, "entities": sorted(entities), "hits": keywords},
        )
        if not prefilter:
            return result
        try:
            triage = self.call("triage", Triage, chunk, meta)
            self.trace.event(
                "triage.decision",
                {"chunk_sha256": digest(chunk)},
                triage.model_dump(mode="json"),
            )
            if not triage.relevant:
                return result
            result["relevant"] = True
            try:
                extraction = self.call("extract", Extraction, chunk, meta)
            except (ValueError, json.JSONDecodeError) as exc:
                # Invalid JSON is observable, and receives one bounded repair.
                self.trace.event("extract.invalid_json", {}, {"error": str(exc)})
                extraction = self.call(
                    "retry",
                    Extraction,
                    chunk,
                    meta,
                    previous="Invalid JSON/schema (see trace)",
                    failures=str(exc),
                )
            for deal in extraction.edges:
                checked = self.trace.call(
                    "verify",
                    deal.model_dump(mode="json"),
                    lambda deal=deal: verify(
                        deal,
                        source_text,
                        self.resolver,
                        meta["source_url"],
                        meta.get("company"),
                    ),
                )
                result["verification_attempts"].append(checked["passed"])
                original = {
                    "deal": deal.model_dump(mode="json"),
                    "verification": checked,
                }
                if not checked["passed"]:
                    # The original failure is retained even if the retry returns
                    # zero edges or invalid output; never silently drop it.
                    original["retry"] = None
                    try:
                        fixed = self.call(
                            "retry",
                            Extraction,
                            chunk,
                            meta,
                            previous=json.dumps(original["deal"]),
                            failures=json.dumps(checked["errors"]),
                        )
                        if len(fixed.edges) == 1:
                            replacement = fixed.edges[0]
                            verification = self.trace.call(
                                "verify.retry",
                                replacement.model_dump(mode="json"),
                                lambda: verify(
                                    replacement,
                                    source_text,
                                    self.resolver,
                                    meta["source_url"],
                                    meta.get("company"),
                                ),
                            )
                            identity_errors = []
                            if replacement.deal_type != deal.deal_type:
                                identity_errors.append(
                                    "Retry changed deal_type rather than repairing the same deal"
                                )
                            for field in ("source_entity", "target_entity"):
                                original_node = self.resolver.resolve(
                                    getattr(deal, field)
                                )
                                repaired_node = self.resolver.resolve(
                                    getattr(replacement, field)
                                )
                                if original_node and repaired_node != original_node:
                                    identity_errors.append(
                                        f"Retry changed {field} identity"
                                    )
                            if identity_errors:
                                verification["passed"] = False
                                verification["errors"].extend(identity_errors)
                                self.trace.event(
                                    "verify.retry_identity", {}, verification
                                )
                            result["verification_attempts"].append(
                                verification["passed"]
                            )
                            original["retry"] = {
                                "deal": replacement.model_dump(mode="json"),
                                "verification": verification,
                            }
                            if verification["passed"]:
                                # Failure history travels with the repaired candidate.
                                original = {
                                    **original["retry"],
                                    "original_failure": original,
                                }
                        else:
                            original["retry"] = {
                                "error": "Retry returned zero or multiple edges"
                            }
                    except Exception as exc:
                        original["retry"] = {"error": str(exc)}
                canonical = original["deal"].copy()
                for key, field in (
                    ("source_entity", "source_node"),
                    ("target_entity", "target_node"),
                ):
                    canonical[key] = (
                        original["verification"].get(field) or canonical[key]
                    )
                original["deal"] = canonical
                result["edges"].append(original)
        except Exception as exc:
            result["errors"].append(str(exc))
            self.trace.event("extract.error", {"metadata": meta}, {"error": str(exc)})
        return result

    def run_documents(self):
        stats = {
            "docs_processed": 0,
            "docs_triaged_in": 0,
            "edges_extracted": 0,
            "verification_passed": 0,
            "verification_total": 0,
            "candidates_proposed": 0,
            "document_errors": 0,
        }
        for row in self.store.rows(
            "SELECT * FROM documents WHERE state != 'processed' ORDER BY id"
        ):
            meta = json.loads(row["meta"])
            text = self.trace.call(
                "document.read",
                {"path": row["text_path"]},
                lambda: Path(row["text_path"]).read_text(),
                summarize=lambda value: {
                    "sha256": digest(value),
                    "characters": len(value),
                },
            )
            if digest(text) != row["id"]:
                raise ValueError(f"Stored source text hash mismatch: {row['id']}")
            result = self.process_text(text, meta, row["id"])
            stats["docs_processed"] += 1
            stats["docs_triaged_in"] += int(result["relevant"])
            stats["edges_extracted"] += len(result["edges"])
            stats["verification_total"] += len(result["edges"])
            stats["verification_passed"] += sum(
                e["verification"]["passed"] for e in result["edges"]
            )
            # One transaction ties proposals to the processed marker. A crash
            # repeats neither LLM chunks nor candidate insertion.
            self.store.db.execute("BEGIN IMMEDIATE")
            try:
                for edge in result["edges"]:
                    rec = self.trace.call(
                        "reconcile",
                        edge["deal"],
                        lambda: reconcile(
                            edge["deal"],
                            self.graph,
                            [*self.legacy, *self.store.candidates()],
                            self.resolver,
                            self.agent["update_match_days"],
                        ),
                    )
                    verification = {
                        **edge["verification"],
                        "history": {
                            key: value
                            for key, value in edge.items()
                            if key not in {"deal", "verification"}
                        },
                    }
                    if (
                        edge["deal"]["confidence"]
                        < self.agent["confidence_warning_threshold"]
                    ):
                        verification["warning"] = (
                            "Low model confidence; manual scrutiny required"
                        )
                    stats["candidates_proposed"] += int(
                        self.trace.call(
                            "propose",
                            edge["deal"],
                            lambda: self.store.propose(
                                row["id"], edge["deal"], verification, rec
                            ),
                        )
                    )
                for error in result["errors"]:
                    self.store.issue(self.trace.run_id, row["id"], "extract", error)
                stats["document_errors"] += bool(result["errors"])
                self.store.db.execute(
                    "UPDATE documents SET state=? WHERE id=?",
                    ("error" if result["errors"] else "processed", row["id"]),
                )
                self.store.db.execute("COMMIT")
            except Exception:
                self.store.db.execute("ROLLBACK")
                raise
        stats["verification_pass_rate"] = (
            stats["verification_passed"] / stats["verification_total"]
            if stats["verification_total"]
            else None
        )
        return stats
