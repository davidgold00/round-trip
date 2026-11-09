"""One-command local benchmark with reusable recordings and comparable reports."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone

import requests

from .evaluate import evaluate
from .io import atomic_write
from .pipeline import Pipeline
from .provider import make_provider
from .rules import Rules
from .store import Store
from .trace import Trace

METRICS = ("triage_precision", "triage_recall", "edge_precision", "edge_recall",
           "amount_accuracy", "numeric_amount_accuracy", "verification_pass_rate")


def preflight(agent, models):
    session = requests.Session()
    session.trust_env = False
    for model in models:
        if not model or ":cloud" in model.lower() or "-cloud" in model.lower():
            raise ValueError("Benchmark accepts downloaded local Ollama models only")
    try:
        response = session.get(agent["ollama_url"].rstrip("/") + "/api/tags", timeout=5)
        response.raise_for_status()
        available = {m["name"] for m in response.json()["models"]}
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise RuntimeError("Ollama is not ready. Start the Ollama app or run `ollama serve`, "
                           f"then run `ollama pull {models[0]}` and retry `make agent-bench`.") from exc
    missing = [m for m in models if m not in available and m + ":latest" not in available]
    if missing:
        raise RuntimeError("Missing local models. Run: " + "; ".join(f"ollama pull {m}" for m in missing))


def comparison(reports, output):
    """Refuse unlike corpora or label policies; keep failed runs visibly unmeasured."""
    keys = {(r["manifest_sha256"], r["exclude_uncertain"]) for r in reports}
    if len(keys) != 1:
        raise ValueError("Cannot compare different gold corpora or uncertainty policies")
    columns = ["Rules baseline" if r["extractor"] == "rules" else
               f"Local LLM: {r['model']} ({r.get('prompt_version', 'v1')})" for r in reports]
    if not any(r["extractor"] == "llm" for r in reports):
        columns.append("Local LLM")
    lines = ["# Deal extraction evaluation", "", "## Rules baseline versus local LLM", "",
             f"Gold manifest SHA-256: `{reports[0]['manifest_sha256']}`.",
             f"Excluded uncertain documents: {reports[0]['exclude_uncertain']}.",
             f"Scored inputs: {reports[0].get('scored_documents', 'see detailed report')} documents.", "",
             "| Metric | " + " | ".join(columns) + " |",
             "|---|" + "---:|" * len(columns)]
    for metric in METRICS:
        values = []
        for report in reports:
            value = (report.get("metrics") or {}).get(metric)
            values.append(f"{value:.1%}" if value is not None else "Not measured")
        values += ["Not measured"] * (len(columns) - len(values))
        lines.append(f"| {metric} | " + " | ".join(values) + " |")
    lines += ["", "All predictions are scored, including failed verification. Directed pair/type matching is one-to-one per document.",
              "Amount accuracy is conditional on matched edges; report its sample count alongside the percentage.",
              "This is a small curated corpus, not a representative accuracy estimate. Synthetic playback never produces model metrics.", ""]
    for column, report in zip(columns, reports):
        lines += [f"### {column}", "", f"Status: {report['status']}. Counts: `{json.dumps((report.get('metrics') or {}).get('counts', {}), sort_keys=True)}`.",
                  f"Run: `{report['run_id']}`. Provider: `{report.get('provider_mode', 'ollama')}`.", ""]
    atomic_write(output, "\n".join(lines).rstrip() + "\n")
    atomic_write(output.with_suffix(".json"), json.dumps({"reports": reports}, indent=2) + "\n")


def benchmark(cfg, *, models=None, prompt_versions=None, exclude_uncertain=False, output=None):
    models = models or [cfg["deal_agent"]["model"]]
    if len(set(models)) != len(models):
        raise ValueError("Choose distinct models for comparison")
    prompt_versions = prompt_versions or [cfg["deal_agent"].get("prompt_version", "v1")]
    if len(set(prompt_versions)) != len(prompt_versions) or any(v not in {"v1", "v2"} for v in prompt_versions):
        raise ValueError("Choose distinct prompt versions from v1 and v2")
    preflight(cfg["deal_agent"], models)
    root = cfg["_root"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / "eval/results" / stamp
    reports = []
    for extractor, model, version in [("rules", models[0], "v1"), *[("llm", m, v) for m in models for v in prompt_versions]]:
        current = deepcopy(cfg)
        current["deal_agent"]["model"] = model
        current["deal_agent"]["prompt_version"] = version
        name = "rules" if extractor == "rules" else re.sub(r"[^A-Za-z0-9_.-]", "_", model) + "-" + version
        trace = Trace(directory / "traces", model)
        cassette = root / "eval/cassettes" / stamp / f"{name}.json"
        with tempfile.TemporaryDirectory(prefix="roundtrip-bench-") as td:
            store = Store(Path(td) / "queue.sqlite3")
            try:
                provider = make_provider(current["deal_agent"], trace,
                                         "record" if extractor == "llm" else "ollama",
                                         cassette if extractor == "llm" else None)
                pipeline = Pipeline(current, store, trace, provider)
                if extractor == "rules":
                    pipeline = Rules(pipeline)
                reports.append(evaluate(pipeline, root / "eval/gold", directory / f"{name}.md",
                                        extractor=extractor, exclude_uncertain=exclude_uncertain))
            finally:
                store.close()
    comparison(reports, output or root / "eval/RESULTS.md")
    for report in reports:
        metrics = report.get("metrics") or {}
        value = metrics.get("edge_precision")
        recall = metrics.get("edge_recall")
        print(f"{report['extractor']} {report['model']}: " +
              (f"edge precision {value:.1%}, recall {recall:.1%}" if value is not None else "Not measured"))
    print(f"Combined report: {output or root / 'eval/RESULTS.md'}")
    print(f"Committable live cassettes: {root / 'eval/cassettes' / stamp}")
    return 1 if any(r["status"] != "complete" or r["label_failures"] for r in reports) else 0
