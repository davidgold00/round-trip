import json
import os
from pathlib import Path
import subprocess
import sys

from deal_agent.config import ROOT


def test_demo_and_explanation_offline(tmp_path):
    guard = tmp_path / "sitecustomize.py"
    guard.write_text("import socket\ndef refuse(*args, **kwargs):\n raise AssertionError('Network in demo')\nsocket.socket.connect=refuse\nsocket.getaddrinfo=refuse\n")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT)])}
    example = json.loads((ROOT/"eval/example/document.json").read_text())
    paths = [ROOT/"ledger/edges.csv", ROOT/"site/data/pending_agent.json", ROOT/"data/deal_agent/queue.sqlite3"]
    before = [p.read_bytes() if p.exists() else None for p in paths]
    def make(*args):
        return subprocess.run(["make",*args,f"PY={sys.executable}"],cwd=ROOT,env=env,check=True,
                              capture_output=True,text=True,timeout=120).stdout
    output = make("demo")
    assert example["candidate_id"] in output and "Published ledger changes: 0" in output
    story = make("explain", "ID="+example["candidate_id"])
    assert f"Raw {example['model']} extract response:" in story
    assert "Human review: pending" in story and "USD_amount:" in story
    assert [p.read_bytes() if p.exists() else None for p in paths] == before


def test_written_trace_matches_explain():
    from deal_agent.config import load
    from deal_agent.explain import load_story, render
    sample = json.loads((ROOT/"eval/example/document.json").read_text())
    text = (ROOT/"docs/TRACE_EXAMPLE.md").read_text()
    assert "```text\n"+render(load_story(load(),sample["candidate_id"]))+"\n```" in text
    real_lines = set((ROOT/"eval/example/trace.jsonl").read_text().splitlines())
    for block in text.split("```jsonl\n")[1:]:
        assert set(block.split("\n```",1)[0].splitlines()) <= real_lines


def test_live_playback_renders_the_documented_decision():
    from deal_agent.config import load
    from deal_agent.demo import demo
    from deal_agent.explain import load_story, render

    replay = demo()
    assert render(replay) == render(load_story(load(), replay["id"]))
