"""CLI entry point; run `python -m deal_agent --help`."""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import load, path_for
from .fetch import fetch, text_of
from .io import lock
from .pipeline import Pipeline
from .provider import Ollama
from .store import Store, encode
from .trace import Trace, digest


def publish(cfg, trace):
    """Rebuild through the original, network-free analysis/publication path."""
    root = cfg["_root"].resolve()
    if (
        path_for(cfg, "graph_file").resolve() != root / "ledger/edges.csv"
        or not (root / "src/refresh.py").is_file()
    ):
        raise RuntimeError(
            "Publication uses the existing project layout: config in the "
            "repository root and graph_file=ledger/edges.csv. "
            "The approved queue/CSV are saved; correct publication configuration "
            "and run `python -m deal_agent publish`."
        )
    command = [
        sys.executable,
        "-m",
        "src.refresh",
        "--skip-ingest",
        "--skip-news",
        "--skip-extract",
    ]
    result = trace.call(
        "publish",
        {"command": command},
        lambda: subprocess.run(
            command, cwd=cfg["_root"], capture_output=True, text=True
        ),
        summarize=lambda p: {
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(
            "Ledger approval is saved; dashboard rebuild failed. "
            "Run `python -m deal_agent publish` to retry. " + result.stderr[-2000:]
        )
    print("Rebuilt approved ledger, metrics, stress, snapshots and dashboard JSON.")


def interactive(review):
    applied = 0
    for row in review.store.candidates():
        review.show(row)
        while True:
            action = (
                input("[a]pprove, [e]dit JSON file, [r]eject, [s]kip, [q]uit: ")
                .strip()
                .lower()
            )
            try:
                if action == "q":
                    return applied
                if action == "s":
                    break
                if action == "e":
                    review.edit(
                        row["id"],
                        Path(input("Edited deal JSON path: ")),
                        input("Edit reason: "),
                    )
                    row = review.candidate(row["id"])
                    review.show(row)
                elif action == "r":
                    review.reject(row["id"], input("Rejection reason: "))
                    break
                elif action == "a":
                    review.approve(
                        row["id"],
                        quote=input("Verbatim publication quote (1-24 words): "),
                        status=input(
                            "Status [definitive/conditional/LOI_nonbinding/announced/reported]: "
                        ),
                        basis=input(
                            "Amount basis [notional/per-year/cumulative/RPO]: "
                        ),
                        low=float(input("USD lower bound (0 for unknown): ")),
                        high=float(input("USD upper bound (0 for unknown): ")),
                        reason=input("Review reason (conditions/uncertainties): "),
                        target_edge=input(
                            "Update graph edge id (blank for a new edge): "
                        ).strip()
                        or None,
                        new_edge=input(
                            "Explicitly treat as a separate new deal? [y/N]: "
                        ).lower()
                        == "y",
                        legacy_type=input(
                            "Legacy edge type override (blank for mapped default): "
                        ).strip()
                        or None,
                    )
                    applied += 1
                    break
            except (ValueError, RuntimeError, SystemExit) as exc:
                print(f"Review refused: {exc}")
    return applied


def parser():
    ap = argparse.ArgumentParser(
        description="Local, human-reviewed AI infrastructure deal extractor"
    )
    ap.add_argument(
        "--config", type=Path, default=None, help="Single project YAML file"
    )
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser(
        "run", help="Fetch, triage, extract, verify, reconcile and propose ONLY"
    )
    run.add_argument(
        "--no-fetch", action="store_true", help="Process already stored documents only"
    )
    run.add_argument(
        "--no-sec", action="store_true", help="Configured public feeds only"
    )
    sub.add_parser("runs", help="Summarise the most recent extraction run")
    evaluate = sub.add_parser(
        "eval", help="Benchmark saved sources offline; only loopback Ollama is used"
    )
    evaluate.add_argument("--gold", type=Path, default=None)
    evaluate.add_argument("--output", type=Path, default=None)
    evaluate.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate labels without a model; no accuracy claim",
    )
    evaluate.add_argument("--exclude-uncertain", action="store_true")
    imp = sub.add_parser(
        "import-file", help="Cache an already downloaded source for an offline run"
    )
    imp.add_argument("path", type=Path)
    imp.add_argument("--company", required=True)
    imp.add_argument("--date", required=True)
    imp.add_argument("--source-url", required=True)
    imp.add_argument("--doc-type", default="company_release")
    imp.add_argument("--accession", default="")
    sub.add_parser(
        "publish", help="Rebuild the dashboard from human-approved ledger rows, offline"
    )
    review = sub.add_parser(
        "review", help="Interactive review, or an explicit review action"
    )
    review.add_argument(
        "action",
        choices=["list", "show", "approve", "edit", "reject", "audit"],
        nargs="?",
    )
    review.add_argument("candidate_id", nargs="?")
    review.add_argument(
        "--actor",
        default=getpass.getuser(),
        help="Reviewer identity recorded in immutable audit",
    )
    review.add_argument(
        "--json", type=Path, help="Replacement deal JSON for edit (deal fields only)"
    )
    review.add_argument("--quote")
    review.add_argument("--status")
    review.add_argument("--basis", default="notional")
    review.add_argument("--amount-low", type=float)
    review.add_argument("--amount-high", type=float)
    review.add_argument("--term-start", default="")
    review.add_argument("--term-end", default="")
    review.add_argument("--edge-type")
    review.add_argument("--target-edge")
    review.add_argument("--new-edge", action="store_true")
    review.add_argument("--reason", default="")
    review.add_argument(
        "--no-publish",
        action="store_true",
        help="Batch approvals; run publish once afterwards",
    )
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    cfg = load(args.config)
    if args.command == "eval":
        # Eval cannot enqueue to production state, even accidentally.
        from .evaluate import evaluate

        output = args.output or cfg["_root"] / "eval/results/latest.md"
        trace = Trace(output.parent / "traces", cfg["deal_agent"]["model"])
        with tempfile.TemporaryDirectory(prefix="roundtrip-eval-") as temporary:
            store = Store(Path(temporary) / "eval.sqlite3")
            try:
                pipeline = Pipeline(cfg, store, trace, Ollama(cfg["deal_agent"], trace))
                report = evaluate(
                    pipeline,
                    args.gold or cfg["_root"] / "eval/gold",
                    output,
                    validate_only=args.validate_only,
                    exclude_uncertain=args.exclude_uncertain,
                )
                print(
                    encode(
                        {
                            "status": report["status"],
                            "metrics": report["metrics"],
                            "label_failures": report["label_failures"],
                            "report": str(output),
                        }
                    )
                )
                return (
                    1
                    if report["status"] == "incomplete" or report["label_failures"]
                    else 0
                )
            finally:
                store.close()
    store = Store(path_for(cfg, "state_db"))
    try:
        if args.command == "runs":
            rows = store.rows("SELECT * FROM runs ORDER BY started DESC LIMIT 1")
            if not rows:
                print("No extraction runs recorded.")
            else:
                row = rows[0]
                row["stats"] = json.loads(row["stats"]) if row["stats"] else None
                print(json.dumps(row, indent=2))
            return 0
        trace = Trace(path_for(cfg, "trace_dir"), cfg["deal_agent"]["model"])
        if args.command == "publish":
            publish(cfg, trace)
            return 0
        pipeline = Pipeline(cfg, store, trace, Ollama(cfg["deal_agent"], trace))
        if args.command == "import-file":
            from datetime import date
            from urllib.parse import urlparse

            date.fromisoformat(args.date)
            if not pipeline.resolver.resolve(args.company):
                raise ValueError("Import company must resolve to an existing node")
            if urlparse(args.source_url).scheme not in {"http", "https"}:
                raise ValueError("Provide the original public HTTP source URL")
            meta = {
                "company": pipeline.resolver.resolve(args.company),
                "published_date": args.date,
                "source_url": args.source_url,
                "doc_type": args.doc_type,
                "accession_no": args.accession,
                "evidence_tier": "T1" if args.accession else "T2",
            }
            raw = trace.call(
                "import.read",
                {"path": str(args.path)},
                args.path.read_bytes,
                summarize=lambda b: {"bytes": len(b), "sha256": digest(b)},
            )
            # Plain text fixtures should not be interpreted as HTML.
            text = raw.decode("utf-8") if args.path.suffix == ".txt" else text_of(raw)
            store.job(args.source_url, "document", meta)
            print(
                trace.call(
                    "import.store",
                    meta,
                    lambda: store.save_document(
                        meta, raw, text, path_for(cfg, "raw_dir")
                    ),
                )
            )
            return 0
        if args.command == "review":
            from .review import Review

            review = Review(pipeline, args.actor)
            if args.action is None:
                try:
                    applied = interactive(review)
                except (EOFError, KeyboardInterrupt):
                    applied = (
                        1
                        if store.rows(
                            "SELECT id FROM audit WHERE action IN ('approve','update') AND state='applied'"
                        )
                        else 0
                    )
                if applied and not args.no_publish:
                    publish(cfg, trace)
            elif args.action == "list":
                for row in store.candidates():
                    print(
                        encode(
                            {
                                k: row[k]
                                for k in ("id", "deal", "verification", "reconcile")
                            }
                        )
                    )
            elif args.action == "audit":
                for row in store.rows("SELECT * FROM audit ORDER BY id"):
                    row["payload"] = json.loads(row["payload"])
                    print(encode(row))
            else:
                if not args.candidate_id:
                    raise ValueError("candidate_id is required")
                if args.action == "show":
                    candidate = review.candidate(args.candidate_id)
                    review.show(candidate)
                    if args.json:
                        from .io import atomic_write

                        atomic_write(args.json, json.dumps(candidate["deal"], indent=2))
                        print(f"Editable deal JSON saved to {args.json}")
                elif args.action == "reject":
                    if not args.reason:
                        raise ValueError("--reason is required")
                    review.reject(args.candidate_id, args.reason)
                elif args.action == "edit":
                    if not args.json or not args.reason:
                        raise ValueError("--json and --reason are required")
                    review.edit(args.candidate_id, args.json, args.reason)
                elif args.action == "approve":
                    if (
                        not args.quote
                        or not args.status
                        or args.amount_low is None
                        or args.amount_high is None
                    ):
                        raise ValueError(
                            "Approval requires --quote, --status, --amount-low and --amount-high"
                        )
                    review.approve(
                        args.candidate_id,
                        quote=args.quote,
                        status=args.status,
                        basis=args.basis,
                        low=args.amount_low,
                        high=args.amount_high,
                        reason=args.reason,
                        target_edge=args.target_edge,
                        new_edge=args.new_edge,
                        legacy_type=args.edge_type,
                        term_start=args.term_start,
                        term_end=args.term_end,
                    )
                    if not args.no_publish:
                        publish(cfg, trace)
            return 0
        if args.command == "run":
            with lock(path_for(cfg, "state_db").with_suffix(".run.lock")):
                store.start(trace.run_id)
                stats = {}
                try:
                    if not args.no_fetch:
                        stats.update(
                            fetch(
                                cfg, store, trace, pipeline.resolver, no_sec=args.no_sec
                            )
                        )
                    else:
                        stats["docs_fetched"] = 0
                    stats.update(pipeline.run_documents())
                    status = (
                        "partial"
                        if stats.get("fetch_errors", 0) or stats["document_errors"]
                        else "complete"
                    )
                    store.finish(trace.run_id, stats, status)
                    print(
                        json.dumps(
                            {"run_id": trace.run_id, "status": status, **stats},
                            indent=2,
                        )
                    )
                    return 1 if status != "complete" else 0
                except Exception as exc:
                    store.finish(trace.run_id, {**stats, "error": str(exc)}, "failed")
                    raise
    finally:
        store.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
