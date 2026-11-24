"""Score proposed relationships against the selected source-backed gold passages.
The real extraction path supplies predictions without receiving expected labels.
Write per-document evidence and aggregate metrics for comparison.
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

from .config import prompt_templates
from .io import atomic_write
from .models import Deal, parse_json
from .trace import digest, stamp
from .verify import verify


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def edge_key(edge, resolver):
    return (
        resolver.resolve(edge["source_entity"]) or edge["source_entity"],
        resolver.resolve(edge["target_entity"]) or edge["target_entity"],
        edge["deal_type"],
    )


def align_edges(expected, predicted, resolver):
    """Pair predictions with distinct gold edges, preferring the nearest amount."""
    available = defaultdict(list)
    for prediction in predicted:
        available[edge_key(prediction["deal"], resolver)].append(prediction)
    for gold in expected:
        choices = available[edge_key(gold, resolver)]
        if not choices:
            yield gold, None
            continue

        def distance(prediction):
            a, b = prediction["deal"]["amount_usd"], gold["amount_usd"]
            if a is None or b is None:
                return 0 if a is b else math.inf
            return abs(a - b)

        best = min(range(len(choices)), key=lambda i: distance(choices[i]))
        yield gold, choices.pop(best)
    for remaining in available.values():
        for prediction in remaining:
            yield None, prediction


def score(records: list[dict], resolver, tolerance=0.001) -> dict:
    triage_tp = triage_fp = triage_fn = edge_tp = edge_fp = edge_fn = 0
    matched = amount_correct = numeric_count = numeric_correct = passes = predictions = 0
    for row in records:
        triage_tp += bool(row["gold_relevant"] and row["triaged_in"])
        triage_fp += bool(not row["gold_relevant"] and row["triaged_in"])
        triage_fn += bool(row["gold_relevant"] and not row["triaged_in"])
        for gold, prediction in align_edges(row["expected"], row["predicted"], resolver):
            if prediction:
                predictions += 1
                passes += prediction["verification"]["passed"]
            if gold is None:
                edge_fp += 1
                continue
            if prediction is None:
                edge_fn += 1
                continue
            edge_tp += 1
            matched += 1
            a, b = prediction["deal"]["amount_usd"], gold["amount_usd"]
            correct = (a is None and b is None) or (
                a is not None and b is not None and abs(a - b) <= max(1, abs(b) * tolerance))
            amount_correct += correct
            if b is not None:
                numeric_count += 1
                numeric_correct += correct
    return {
        "triage_precision": ratio(triage_tp, triage_tp + triage_fp),
        "triage_recall": ratio(triage_tp, triage_tp + triage_fn),
        "edge_precision": ratio(edge_tp, edge_tp + edge_fp),
        "edge_recall": ratio(edge_tp, edge_tp + edge_fn),
        "amount_accuracy": ratio(amount_correct, matched),
        "numeric_amount_accuracy": ratio(numeric_correct, numeric_count),
        "verification_pass_rate": ratio(passes, predictions),
        "counts": {
            "edge_tp": edge_tp,
            "edge_fp": edge_fp,
            "edge_fn": edge_fn,
            "amounts_scored": matched,
            "numeric_amounts_scored": numeric_count,
            "predictions": predictions,
        },
    }


def evaluate(
    pipeline,
    directory: Path,
    output: Path,
    *,
    validate_only=False,
    exclude_uncertain=False,
    extractor="llm",
    split=None,
):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if split:
        from .splits import partitions
        members = set(partitions(directory, manifest["documents"])[split])
        manifest["documents"] = [d for d in manifest["documents"] if d["id"] in members]
    from .gold_ledger import check_gold_ledger
    ledger_check = check_gold_ledger(manifest["documents"], pipeline.cfg, pipeline.resolver)
    records, errors, label_failures = [], [], []
    elapsed = 0.0
    for item in manifest["documents"]:
        text = (directory / item["text_file"]).read_text()
        if digest(text) != item["sha256"]:
            raise ValueError(f"Gold source hash mismatch: {item['id']}")
        meta = {
            key: item[key]
            for key in ("source_url", "company", "published_date", "doc_type")
        }
        expected = item["expected_edges"]
        for label in expected:
            edge = parse_json(json.dumps(label), Deal)
            checked = verify(
                edge, text, pipeline.resolver, item["source_url"], item["company"]
            )
            if not checked["passed"]:
                label_failures.append({"id": item["id"], "errors": checked["errors"]})
        if validate_only:
            continue
        if exclude_uncertain and item.get("label_uncertain"):
            continue
        # No labels, ids or expected entity pairs are sent to the model.
        cached_seconds = getattr(pipeline.provider, "replayed_seconds", 0.0)
        started = time.perf_counter()
        result = pipeline.process_text(text, meta)
        seconds = (time.perf_counter() - started
                   + getattr(pipeline.provider, "replayed_seconds", 0.0) - cached_seconds)
        elapsed += seconds
        records.append(
            {
                "id": item["id"],
                "input_sha256": item["sha256"],
                "seconds": seconds,
                "verification_attempts": result.get("verification_attempts", []),
                "label_uncertain": item["label_uncertain"],
                "gold_relevant": item["relevant"],
                "triaged_in": result["relevant"],
                "expected": expected,
                "predicted": result["edges"],
            }
        )
        errors.extend({"id": item["id"], "error": error} for error in result["errors"])
    status = (
        "labels_only" if validate_only else ("incomplete" if errors else "complete")
    )
    synthetic = getattr(pipeline.provider, "synthetic", False)
    if synthetic and not validate_only and not errors:
        status = "synthetic_test_only"
    metrics = score(records, pipeline.resolver) if records and not errors and not synthetic else None
    parse_events = [json.loads(line) for line in pipeline.trace.path.read_text().splitlines()
                    if '.parse"' in line]
    parse_events = [e for e in parse_events if e["stage"].endswith(".parse")]
    report = {
        "split": split,
        "seconds_per_document": elapsed / len(records) if records else None,
        "parse_calls": len(parse_events),
        "parse_failures": sum("error_type" in e["outputs"] for e in parse_events),
        "synthetic": synthetic,
        "provider_mode": getattr(pipeline.provider, "mode", "ollama"),
        "cassette_sha256": getattr(pipeline.provider, "cassette_sha256", None),
        "extractor": extractor,
        "status": status,
        "generated": stamp(),
        "run_id": pipeline.trace.run_id,
        "model": pipeline.provider.model,
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "prompt_version": pipeline.agent.get("prompt_version", "v1") if extractor == "llm" else None,
        "prompt_hashes": ({f"{stage}.txt": digest(template) for stage, template in
                           prompt_templates(pipeline.agent.get("prompt_version", "v1")).items()}
                          if extractor == "llm" else {}),
        "settings": {
            k: pipeline.agent[k]
            for k in (
                "chunk_chars",
                "chunk_overlap",
                "num_ctx",
                "keywords",
                "min_entities",
                "confidence_warning_threshold",
            )
        },
        "scored_documents": len(records),
        "scored_positives": sum(row["gold_relevant"] for row in records),
        "scored_negatives": sum(not row["gold_relevant"] for row in records),
        "documents": len(manifest["documents"]),
        "positives": sum(d["relevant"] for d in manifest["documents"]),
        "negatives": sum(not d["relevant"] for d in manifest["documents"]),
        "uncertain": sum(d["label_uncertain"] for d in manifest["documents"]),
        "exclude_uncertain": exclude_uncertain,
        "metrics": metrics,
        "ledger_check": ledger_check,
        "label_failures": label_failures,
        "errors": errors,
        "records": records,
    }
    lines = [
        "# Deal extraction evaluation",
        "",
        f"Status: **{status}**. Model: `{report['model']}`.",
        f"Run: `{report['run_id']}`. Generated: {report['generated']}.",
        "",
        f"Gold corpus: {report['positives']} positive and {report['negatives']} negative documents; "
        f"{report['uncertain']} uncertain labels. {len(label_failures)} structural label failures.",
        "",
        f"Scored inputs after uncertainty policy: {len(records)} documents. Validate-only does not run an extractor.",
        "",
        "The corpus contains short, attributed excerpts, not full filings. It is a small smoke benchmark; "
        "scores do not establish full-document or out-of-time accuracy. Uncertain labels remain identified in manifest.json.",
        "",
        "## Rules baseline" if extractor == "rules" else "## Local LLM",
        "",
        "| Metric | Rules baseline | Local LLM |",
        "|---|---:|---:|",
    ]
    for metric in (
        "triage_precision",
        "triage_recall",
        "edge_precision",
        "edge_recall",
        "amount_accuracy",
        "numeric_amount_accuracy",
        "verification_pass_rate",
    ):
        value = (metrics or {}).get(metric)
        shown = f"{value:.1%}" if value is not None else "Not measured"
        cells = [shown, "Not measured"] if extractor == "rules" else ["Not measured", shown]
        lines.append(f"| {metric} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        "Edge matching is directed entity pair + deal_type, one-to-one per document. "
        "All predictions are scored, including failed verification; failures are never filtered to improve precision. "
        "Amount accuracy scores matched pairs, including correct nulls; numeric accuracy excludes null gold amounts. "
        "Numeric tolerance: max($1, 0.1%). Final verification rate includes repaired candidates.",
        "",
        f"Excluded uncertain labels: {exclude_uncertain}. A failed model call makes the run incomplete; "
        "metrics are withheld rather than treating an unavailable model as zero recall.",
        "",
    ]
    if errors:
        lines += ["## Execution errors", ""] + [
            f"- {e['id']}: {e['error']}" for e in errors
        ]
    if label_failures:
        lines += ["## Label validation failures", ""] + [
            f"- {e}" for e in label_failures
        ]
    lines += ["## Reviewed ledger agreement", "",
              f"{len(ledger_check['matched'])} matched, {len(ledger_check['mismatches'])} mismatches, "
              f"{len(ledger_check['ambiguous'])} ambiguous, {len(ledger_check['unlinked'])} unlinked gold edges.",
              "Mismatches are read-only advisories; use --strict-ledger to make them fatal. Neither side is changed.", ""]
    lines += [f"- {entry}" for entry in ledger_check["mismatches"] + ledger_check["ambiguous"]]
    atomic_write(output, "\n".join(lines).rstrip() + "\n")
    atomic_write(output.with_suffix(".json"), json.dumps(report, indent=2))
    pipeline.trace.event(
        "eval.report", {"manifest_sha256": report["manifest_sha256"]}, report
    )
    return report
