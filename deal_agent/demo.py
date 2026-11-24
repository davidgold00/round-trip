"""Replay a real recorded development passage through an isolated local queue.
The CLI and interview walkthrough use the same provider, checks and reconciliation.
All temporary source, SQLite, trace and dashboard files are confined to the demo.
"""
import json
import tempfile
from pathlib import Path

from .config import ROOT, load, path_for
from .explain import load_story
from .pending import export
from .pipeline import Pipeline
from .provider import Replay
from .store import Store
from .trace import Trace, digest


class DemoTrace(Trace):
    def event(self, stage, inputs, outputs, latency_ms=0, kind="stage"):
        super().event(stage, inputs, outputs, latency_ms, kind)
        if stage == "document.read":
            print("Read and hash the cached source.", flush=True)
        elif stage == "triage.decision":
            print("Triage decision:", outputs["reason"], flush=True)
        elif stage == "extract.parse":
            print(f"Extracted {len(outputs['edges'])} structured proposal(s).", flush=True)
        elif stage in {"verify", "verify.retry"}:
            print("Verification:", "passed" if outputs["passed"] else ", ".join(outputs["errors"]), flush=True)
        elif stage == "retry.parse":
            print("Read the recorded repair attempt.", flush=True)
        elif stage == "reconcile":
            print(f"Compared with prior records: {outputs['classification']}.", flush=True)


def demo():
    source = ROOT / "eval/example"
    example = json.loads((source/"document.json").read_text())
    cfg = load()
    text = (ROOT/example["source_file"]).read_text()
    if digest(text) != example["sha256"]:
        raise ValueError("Demo source hash mismatch")
    with tempfile.TemporaryDirectory(prefix="roundtrip-demo-") as temp:
        work = Path(temp)
        agent = cfg["deal_agent"]
        agent.update(model=example["model"], prompt_version=example["prompt_version"],
                     state_db=str(work/"queue.sqlite3"), raw_dir=str(work/"raw"),
                     trace_dir=str(work/"traces"))
        trace = DemoTrace(path_for(cfg,"trace_dir"), agent["model"])
        store = Store(path_for(cfg,"state_db"))
        try:
            player = Replay(agent, source/"cassette.json", trace)
            if player.synthetic:
                raise ValueError("Interview demo requires a real local model recording")
            print(f"Offline replay of {agent['model']} {agent['prompt_version']}, run {example['origin_run_id']}.", flush=True)
            pipe = Pipeline(cfg, store, trace, player)
            store.save_document(example["metadata"], text.encode(), text, work/"raw")
            stats = pipe.run_documents()
            if stats["document_errors"] or player.position != len(player.data["calls"]):
                raise ValueError("Incomplete demo playback")
            candidates = store.candidates()
            row = next((c for c in candidates if c["id"] == example["candidate_id"]), None)
            if row is None:
                raise ValueError("Recorded example did not reproduce its candidate ID")
            snapshot = export(cfg, work/"dashboard")
            if snapshot["pending_count"] != len(candidates):
                raise ValueError("Dashboard export differs from demo queue")
            story = load_story(cfg, row["id"])
            story["model"] = agent["model"]
            story["origin_run_id"] = example["origin_run_id"]
            print(f"Pending candidate {row['id']}: {row['deal']['source_entity']} to {row['deal']['target_entity']}.")
            print("Dashboard location: Review & news > Recorded example. The demo queue is temporary.")
            return story
        finally:
            store.close()
