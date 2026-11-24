"""Reconstruct a candidate's evidence trail from its source, trace and audit.
The offline demo and the live explain command use the same story renderer.
Pending findings and already-applied promotions are distinguished explicitly.
"""
import json
import sqlite3
from pathlib import Path

from .config import ROOT, path_for
from .models import LEGACY_TYPE


def document_events(directory, document_id):
    events = []
    for path in sorted(directory.glob("*.jsonl")):
        active = False
        for line in path.read_text().splitlines():
            e = json.loads(line)
            if e["stage"] == "document.read":
                active = e["outputs"].get("sha256") == document_id
            if active:
                events.append(e)
    return events


def load_story(cfg, ident):
    db = path_for(cfg, "state_db")
    if db.is_file():
        with sqlite3.connect(db.resolve().as_uri()+"?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("""SELECT c.*,d.meta FROM candidates c JOIN documents d
                ON d.id=c.document_id WHERE c.id=?""", (ident,)).fetchone()
            if row:
                story = {key: json.loads(row[key]) for key in ("deal","verification","reconcile","meta")}
                story.update(id=ident, document_id=row["document_id"], status=row["status"],
                    events=document_events(path_for(cfg, "trace_dir"), row["document_id"]),
                    reviews=[dict(r) for r in con.execute("SELECT actor,action,created,payload FROM audit WHERE candidate_id=? AND state='applied' ORDER BY id",(ident,))])
                audit = path_for(cfg, "graph_file").parent / "promotion_audit.jsonl"
                story["applied"] = [e for e in (json.loads(l) for l in audit.read_text().splitlines() if l.strip())
                                    if e.get("candidate_id") == ident and e.get("event", "applied") == "applied"] if audit.exists() else []
                return story
    sample = ROOT / "eval/example/story.json"
    if sample.is_file():
        story = json.loads(sample.read_text())
        if story["id"] == ident:
            story["events"] = [json.loads(l) for l in (sample.parent/"trace.jsonl").read_text().splitlines()]
            return story
    raise ValueError(f"No candidate {ident} in the local queue or committed example")


def render(story):
    d, meta, events = story["deal"], story["meta"], story["events"]
    lines = [f"Candidate {story['id']}", f"Source: {meta['company']} | {meta['published_date']} | {meta['source_url']}",
             f"Source text SHA-256: {story['document_id']}", f"Evidence: {d['evidence_quote']}"]
    if story.get("origin_run_id"):
        lines.append("Recorded local inference run: "+story["origin_run_id"])
    seen = set()
    for e in events:
        stage, result = e["stage"], e["outputs"]
        if stage == "triage.keyword":
            lines.append("Keyword triage: " + ("admitted" if result["relevant"] else "screened out")
                         + f"; companies {', '.join(result['entities'])}; terms {', '.join(result['hits']) or 'none'}.")
        elif stage == "triage.decision":
            lines.append("Model triage: "+result["reason"])
        elif stage == "prompt":
            lines.append(f"{e['inputs']['name']} prompt {e['inputs']['version']} | template {result['sha256']}")
        elif stage in {"triage.parse", "extract.parse", "retry.parse"}:
            name = stage.split(".")[0]
            model = story.get("model") or next((ev.get("model") or ev["inputs"].get("model")
                for ev in events if ev["stage"] == name and ev["kind"] in {"llm", "replay"}), "model")
            lines.append(f"Raw {model} {name} response:\n{e['inputs']['response']}")
        elif stage in {"verify", "verify.retry", "verify.retry_identity"}:
            if stage != "verify.retry_identity" and not any(e["inputs"] == candidate for candidate in [d,
                    story["verification"].get("history", {}).get("original_failure", {}).get("deal"),
                    (story["verification"].get("history", {}).get("retry") or {}).get("deal")]):
                continue
            lines.append(f"{stage}: "+("passed" if result["passed"] else "failed"))
            lines.extend(f"  {key}: {v['result']}"+(" | "+"; ".join(v["errors"]) if v["errors"] else "")
                         for key,v in result.get("details",{}).items())
            if not result.get("details"):
                lines.extend("  "+s for s in result["errors"])
            seen.add("verify")
    if "verify" not in seen:
        checked=story["verification"]
        lines.append("Stored verification: "+("passed" if checked["passed"] else "failed"))
        lines.extend("  "+message for message in checked["errors"])
        if not events:
            lines.append("Original stage trace unavailable for this candidate.")
    from .verify import instrument_advisory
    advisory = instrument_advisory(d)
    if advisory:
        lines.append("Instrument review: " + advisory)
    rec=story["reconcile"]
    lines.append(f"Reconcile: {rec['classification']} | {rec['reason']}"+(f" | {rec['match_id']}" if rec.get("match_id") else ""))
    lines.append("Human review: "+story["status"])
    for event in story["reviews"]:
        lines.append(f"  {event['actor']} | {event['action']} | "+json.loads(event["payload"]).get("reason",""))
    family=LEGACY_TYPE.get(d["deal_type"])
    if family in {"purchase_commitment","cloud_capacity_contract"}:
        effect=f"Eligible purchases enter the buyer-to-seller demand numerator for {d['target_entity']} and its stress network."
    elif family:
        effect=f"Eligible funding enters {d['target_entity']}'s documented funding denominator and the funding network used by stress."
    else:
        effect="Metric treatment depends on the legacy edge type selected in review."
    if story["applied"]:
        lines.append("Applied ledger rows: "+", ".join(story["applied"][-1]["edge_ids"])+". "+effect)
    else:
        lines.append("Ledger and dashboard effect: no applied promotion. "+effect+" A duplicate adds no new dollars.")
    return "\n".join(lines)
