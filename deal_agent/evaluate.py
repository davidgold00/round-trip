"""Offline benchmark: identical extraction path, held-out labels used only for scoring."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

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


def score(records: list[dict], resolver, tolerance=0.001) -> dict:
    triage_tp = triage_fp = triage_fn = edge_tp = edge_fp = edge_fn = 0
    matched = amount_correct = numeric_count = numeric_correct = passes = (
        predictions
    ) = 0
    for row in records:
        expected, predicted = row["expected"], row["predicted"]
        triage_tp += bool(row["gold_relevant"] and row["triaged_in"])
        triage_fp += bool(not row["gold_relevant"] and row["triaged_in"])
        triage_fn += bool(row["gold_relevant"] and not row["triaged_in"])
        gold_by, pred_by = defaultdict(list), defaultdict(list)
        for edge in expected:
            gold_by[edge_key(edge, resolver)].append(edge)
        for edge in predicted:
            pred_by[edge_key(edge["deal"], resolver)].append(edge)
            predictions += 1
            passes += edge["verification"]["passed"]
        for key in gold_by.keys() | pred_by.keys():
            gold, pred = gold_by[key], pred_by[key]
            # One-to-one matching within pair/type. Do NOT allow a single edge
            # to satisfy multiple tranches or count duplicate predictions as TP.
            # Prefer equal amounts for deterministic assignment within that key.
            available = list(pred)
            for target in gold:
                if not available:
                    edge_fn += 1
                    continue

                def error(item):
                    a, b = item["deal"]["amount_usd"], target["amount_usd"]
                    if a is None or b is None:
                        return 0 if a is b else math.inf
                    return abs(a - b)

                index = min(range(len(available)), key=lambda i: error(available[i]))
                chosen = available.pop(index)
                edge_tp += 1
                matched += 1
                a, b = chosen["deal"]["amount_usd"], target["amount_usd"]
                correct = (a is None and b is None) or (
                    a is not None
                    and b is not None
                    and abs(a - b) <= max(1, abs(b) * tolerance)
                )
                amount_correct += correct
                if b is not None:
                    numeric_count += 1
                    numeric_correct += correct
            edge_fp += len(available)
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
):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    records, errors, label_failures = [], [], []
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
        result = pipeline.process_text(text, meta)
        records.append(
            {
                "id": item["id"],
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
    report = {
        "synthetic": synthetic,
        "provider_mode": getattr(pipeline.provider, "mode", "ollama"),
        "cassette_sha256": getattr(pipeline.provider, "cassette_sha256", None),
        "extractor": extractor,
        "status": status,
        "generated": stamp(),
        "run_id": pipeline.trace.run_id,
        "model": pipeline.provider.model,
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "prompt_hashes": {
            p.name: digest(p.read_bytes())
            for p in (Path(__file__).parent / "prompts" / "v1").glob("*.txt")
        },
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
        "documents": len(manifest["documents"]),
        "positives": sum(d["relevant"] for d in manifest["documents"]),
        "negatives": sum(not d["relevant"] for d in manifest["documents"]),
        "uncertain": sum(d["label_uncertain"] for d in manifest["documents"]),
        "exclude_uncertain": exclude_uncertain,
        "metrics": metrics,
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
    atomic_write(output, "\n".join(lines).rstrip() + "\n")
    atomic_write(output.with_suffix(".json"), json.dumps(report, indent=2))
    pipeline.trace.event(
        "eval.report", {"manifest_sha256": report["manifest_sha256"]}, report
    )
    return report
