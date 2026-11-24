"""Account for development scoring errors and verifier failures by document.
The shared edge matcher ties each entry back to its recorded predictions.
Confidence bins are descriptive and never read frozen test source text.
"""
from collections import Counter, defaultdict
import json

from .config import ROOT, load, path_for
from .entities import Resolver
from .evaluate import align_edges, edge_key
from .io import atomic_write
from .reporting import display_name, rate


def category(key, others, row, prediction=None):
    src, dst, kind = key
    if any((src,dst) == k[:2] and kind != k[2] for k in others):
        return "confusable deal_type"
    if any((dst,src) == k[:2] for k in others):
        return "wrong direction"
    if prediction and any("entity" in e for e in prediction["verification"]["errors"]):
        return "missed or spurious alias"
    if key in others:
        return "duplicate proposal"
    if not row["triaged_in"] or not row["gold_relevant"]:
        return "triage miss"
    if row["label_uncertain"]:
        return "label dispute"
    return "unsupported or omitted relationship"


def verification_category(error):
    if "amount" in error:
        return "amount misread"
    if "verbatim" in error:
        return "non-verbatim quote"
    if "entity" in error or "node" in error:
        return "missed or spurious alias"
    if "identity" in error or "deal_type" in error:
        return "repair changed identity"
    return "source or schema mismatch"


def audit(report, resolver, source_urls):
    if report["split"] != "dev":
        raise ValueError("Error analysis accepts development partitions only")
    findings, bins = [], defaultdict(list)
    for row in report["records"]:
        expected = [edge_key(g,resolver) for g in row["expected"]]
        predicted = [edge_key(p["deal"],resolver) for p in row["predicted"]]
        def add(event, kind, detail):
            findings.append((row["id"],event,kind,detail))
        for gold, pred in align_edges(row["expected"],row["predicted"],resolver):
            if pred:
                deal = pred["deal"]
                key = edge_key(deal,resolver)
                if report["extractor"] == "llm":
                    c = deal["confidence"]
                    bin_name = "below 0.70" if c < .7 else "0.70 to <0.90" if c < .9 else "0.90 to 1.00"
                    bins[bin_name].append((bool(gold),source_urls[row["id"]]))
                if not gold:
                    add("FP",category(key,expected,row,pred)," → ".join(key))
                elif (deal["amount_usd"] != gold["amount_usd"] and
                      (deal["amount_usd"] is None or gold["amount_usd"] is None or
                       abs(deal["amount_usd"]-gold["amount_usd"]) > max(1, abs(gold["amount_usd"])*.001))):
                    add("Matched amount","amount misread",f"Expected {gold['amount_usd']}; proposed {deal['amount_usd']}")
                first = pred.get("original_failure",pred)
                attempts = [("first check",first["verification"])]
                retry = first.get("retry") or {}
                if retry.get("verification"):
                    attempts.append(("repair check",retry["verification"]))
                for stage, checked in attempts:
                    for error in checked["errors"]:
                        add(stage,verification_category(error),error)
            else:
                key = edge_key(gold,resolver)
                add("FN",category(key,predicted,row)," → ".join(key))
    c=report["metrics"]["counts"]
    if sum(f[1]=="FP" for f in findings)!=c["edge_fp"] or sum(f[1]=="FN" for f in findings)!=c["edge_fn"]:
        raise ValueError("Error counts differ from recorded scorer")
    return findings,bins


def write():
    cfg=load()
    resolver=Resolver.from_csv(path_for(cfg,"nodes_file"),cfg["deal_agent"]["aliases"])
    manifest=json.loads((ROOT/"eval/gold/manifest.json").read_text())["documents"]
    urls={r["id"]:r["source_url"] for r in manifest}
    lines=["# Development error analysis","",
           "Each FP is an extra directed pair/type. Each FN is a missing one. A reversed proposal can produce both. Each failed verifier check is listed at its actual attempt, including a failure later repaired. Counts are diagnostic events, so the same document can contribute several. Categories describe observed differences, not a hidden reason for the model's decision.",""]
    for path in sorted((ROOT/"eval/evidence/dev").glob("*.json")):
        r=json.loads(path.read_text())
        findings,bins=audit(r,resolver,urls)
        tally=Counter(e[2] for e in findings)
        lines += [f"## {display_name(r)}", "", f"{r['scored_documents']} passages. [Run `{r['run_id']}`](evidence/dev/{path.name}).", "",
                  "Most frequent categories: "+", ".join(f"{name} ({count})" for name,count in tally.most_common(3))+".", "",
                  "| Document | Event | Category | Evidence |","|---|---|---|---|"]
        lines += ["| "+" | ".join(str(cell).replace("|","\\|").replace("\n"," ") for cell in f)+" |" for f in findings]
        if not findings: lines.append("| All | None | None | No recorded scoring or verification errors |")
        if bins:
            lines += ["","| Model confidence | Correct / proposed | Distinct source URLs |","|---|---:|---:|"]
            for label in ("below 0.70","0.70 to <0.90","0.90 to 1.00"):
                values=bins.get(label,[])
                lines.append(f"| {label} | {rate(sum(x[0] for x in values),len(values))} | {len(set(x[1] for x in values))} |")
        lines.append("")
    lines += ["## What to investigate","",
              "The rules adapter guesses financial direction. It also matches Meta inside the editorial word `metadata` and Intel inside `intelligence`; the exact-node verifier catches those proposals. A missing positive on which rules proposed nothing is a triage miss at the rules stage. The short excerpts provide little evidence about full-document chunk boundaries. Use the model-specific rows above to choose a prompt or verifier experiment.",""]
    atomic_write(ROOT/"eval/ERROR_ANALYSIS.md","\n".join(lines))


if __name__ == "__main__":
    write()
