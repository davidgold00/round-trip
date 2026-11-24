"""Publish compact, reproducible evidence for a development or final run.
The evaluator supplies scored records and a matching real inference cassette.
Tables retain the event denominators and link to both artifacts for each row.
"""
import argparse
import gzip
import json
from pathlib import Path

from .config import ROOT
from .io import atomic_write
from .trace import digest


def archive(report_path, name, cassette=None):
    report = json.loads(report_path.read_text())
    if not report.get("split") or report["synthetic"] or report["status"] != "complete":
        raise ValueError("Publish only complete, genuine, explicitly partitioned runs")
    directory = ROOT / "eval/evidence" / report["split"]
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"{name}.json"
    if dest.exists():
        if json.loads(dest.read_text())["run_id"] != report["run_id"]:
            raise ValueError(f"Existing run for {name}; choose a new evidence name")
        return dest
    if report["extractor"] == "llm":
        raw = cassette.read_bytes()
        raw = gzip.decompress(raw) if cassette.suffix == ".gz" else raw
        data = json.loads(raw)
        if data["synthetic"] or data.get("run_id") != report["run_id"] or digest(raw) != report["cassette_sha256"]:
            raise ValueError("Report and live recording do not agree")
    else:
        data = {"version": 1, "extractor": "original-rules", "run_id": report["run_id"],
                "calls": [{"id": r["id"], "source_sha256": r["input_sha256"], "relevant": r["triaged_in"],
                           "proposals": r["predicted"]} for r in report["records"]]}
        raw = (json.dumps(data, ensure_ascii=False, indent=2)+"\n").encode()
    recording = directory / f"{name}.cassette.json.gz"
    recording.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    report["cassette_file"] = recording.name
    report["cassette_sha256"] = digest(raw)
    atomic_write(dest, json.dumps(report, indent=2, ensure_ascii=False)+"\n")
    return dest


def display_name(report):
    return "Original rules" if report["extractor"] == "rules" else f"{report['model']} / {report['prompt_version']}"


def rate(a, b):
    return f"{a/b:.1%} ({a}/{b})" if b else "Not measured (0/0)"


def counts(report):
    c = report["metrics"]["counts"]
    passed = sum(e["verification"]["passed"] for r in report["records"] for e in r["predicted"])
    return c["edge_tp"], c["edge_fp"], c["edge_fn"], int(passed)


def table(paths, prefix=""):
    rows = ["| Configuration | Edge precision | Edge recall | Verification pass | Parse failures / calls | Seconds / passage | Passages | Evidence |",
            "|---|---:|---:|---:|---:|---:|---:|---|"]
    for path in paths:
        r = json.loads(path.read_text())
        tp, fp, fn, passed = counts(r)
        base = path.relative_to(ROOT / "eval").as_posix()
        cassette = path.with_name(r["cassette_file"]).relative_to(ROOT/"eval").as_posix()
        parse = f"{r['parse_failures']}/{r['parse_calls']}" if r['extractor']=='llm' else "n/a (rules)"
        rows.append(f"| {display_name(r)} | {rate(tp,tp+fp)} | {rate(tp,tp+fn)} | {rate(passed,tp+fp)}"
                    f" | {parse} | {r['seconds_per_document']:.3f} | {r['scored_documents']}"
                    f" | [`{r['run_id']}`]({prefix}{base}) · [cassette]({prefix}{cassette}) |")
    return "\n".join(rows)


def dev_report():
    paths = sorted((ROOT/"eval/evidence/dev").glob("*.json"))
    content = "# Development runs\n\n"+table(paths)+"\n\nAll scores include failed verification and uncertain labels. Time is local extraction and checking per saved passage. For a resumed prefix, it includes recorded inference time. Raw model responses and deterministic rules observations have different cassette formats.\n"
    atomic_write(ROOT/"eval/RESULTS-dev.md", content)


if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report",type=Path)
    ap.add_argument("--name",required=True)
    ap.add_argument("--cassette",type=Path)
    args=ap.parse_args()
    archive(args.report,args.name,args.cassette)
    dev_report()
