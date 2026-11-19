"""Export eligible human decisions from the immutable review audit.
Review actions stay in SQLite; a recoverable JSONL copy supplies future examples.
Source and text identities shared with the frozen test set are excluded.
"""
import json
from urllib.parse import urlsplit

from .config import ROOT, path_for
from .io import atomic_write
from .splits import partitions
from .store import encode
from .verify import whitespace


def source_key(url):
    parts = urlsplit(url)
    return (parts.hostname or "").removeprefix("www.").lower(), parts.path.rstrip("/").lower()


def sync_examples(cfg, store):
    gold = ROOT / "eval/gold"
    docs = json.loads((gold / "manifest.json").read_text())["documents"]
    ids = set(partitions(gold, docs)["test"])
    held = [d for d in docs if d["id"] in ids]
    urls = {source_key(d["source_url"]) for d in held}
    fingerprints = {d["sha256"] for d in held}
    quotes = {whitespace(e["evidence_quote"]).casefold() for d in held for e in d["expected_edges"]}
    path = path_for(cfg, "state_db").parent / "reviewed-examples.jsonl"
    # Serialize the audit read and file projection with other decision writers.
    # Atomic replacement preserves the old complete log on interruption.
    store.db.execute("BEGIN IMMEDIATE")
    try:
        originals, lines = {}, []
        events = store.rows("""SELECT a.*, c.document_id, d.meta FROM audit a
            JOIN candidates c ON c.id=a.candidate_id JOIN documents d ON d.id=c.document_id
            WHERE a.state='applied' ORDER BY a.id""")
        for event in events:
            payload = json.loads(event["payload"])
            action, key = event["action"], event["candidate_id"]
            if action == "edit":
                originals.setdefault(key, payload["before"]["deal"])
                continue
            if action not in {"approve", "update", "reject", "reopen"}:
                continue
            row = payload.get("candidate") or payload.get("before") or {}
            deal = row.get("deal")
            if not isinstance(deal, dict):
                continue  # Historical audit without a reconstructible candidate.
            source = json.loads(event["meta"])["source_url"]
            original = originals.get(key, deal)
            if event["document_id"] in fingerprints or any(source_key(u) in urls for u in
                    [source, deal["source_url"], original["source_url"]]):
                continue
            if any(whitespace(d["evidence_quote"]).casefold() in quotes for d in [original, deal]):
                continue
            lines.append(encode({"audit_id": event["id"], "candidate_id": key,
                "decision": action, "actor": event["actor"], "source_url": source,
                "document_sha256": event["document_id"], "proposal": original,
                "evidence_quote": deal["evidence_quote"], "correction": deal if deal != original else None,
                "reviewed_terms": payload.get("after"), "reason": payload.get("reason", "")}) + "\n")
        content = "".join(lines)
        if content or path.exists():
            if not path.exists() or path.read_text() != content:
                atomic_write(path, content)
        store.db.execute("COMMIT")
    except Exception:
        store.db.execute("ROLLBACK")
        raise
    return path


def current_examples(path):
    """A reopened decision invalidates its older example until a new decision."""
    latest = {}
    for line in path.read_text().splitlines() if path.exists() else ():
        entry = json.loads(line)
        latest[entry["candidate_id"]] = entry
    return [e for e in latest.values() if e["decision"] != "reopen"]
