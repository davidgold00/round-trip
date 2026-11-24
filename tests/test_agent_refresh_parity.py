"""The original make refresh pipeline must preserve main's financial headline.

Only acquisition is stubbed: both trees receive the same empty filing cache.
Extraction, metrics, all 20,000 stress draws and dashboard export run unchanged.
The pinned main commit is the branch's reviewed starting point, not a moving ref.
"""
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MAIN = "ceedd24d4d4a3d10486041996879ca2e6b2bb186"


def test_original_refresh_preserves_main_headlines(tmp_path):
    archived = subprocess.check_output(["git", "archive", MAIN], cwd=ROOT)
    base = tmp_path / "main"
    base.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archived)) as archive:
        archive.extractall(base, filter="data")
    current = tmp_path / "feature"
    shutil.copytree(base, current)
    # Include working changes, so the guard also runs before a commit.
    for directory in ("src", "deal_agent", "ledger", "site"):
        shutil.copytree(ROOT / directory, current / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "snapshots"))
    for name in ("config.yaml", "Makefile"):
        shutil.copyfile(ROOT / name, current / name)
    with (base / "ledger/edges.csv").open() as handle:
        before = list(csv.DictReader(handle))
    with (current / "ledger/edges.csv").open() as handle:
        after = list(csv.DictReader(handle))
    assert [{k: row[k] for k in before[0]} for row in after] == before
    for p in (base / "ledger").glob("promotions*.yaml"):
        assert p.read_bytes() == (current / "ledger" / p.name).read_bytes()
    for tree in (base, current):
        interim = tree / "data/interim"
        interim.mkdir(parents=True, exist_ok=True)
        (interim / "filings_index.csv").write_text("local_path,node,filing_date,doc_url,accession_no,form\n")
        runner = tree / "offline_refresh.py"
        runner.write_text('''import runpy
import sys
sys.argv = [sys.argv[0]]
import requests
from src import ingest, news
# Frozen acquisition boundary; no SEC request or hosted model is permitted.
def refuse(*args, **kwargs):
    raise AssertionError("refresh parity attempted a network request")
requests.sessions.Session.request = refuse
ingest.ingest = lambda: None
news.run = lambda: None
runpy.run_module("src.refresh", run_name="__main__")
''')
        result = subprocess.run(["make", "refresh", f"PY={sys.executable} {runner}"],
                                cwd=tree, capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(tree)}, timeout=180)
        assert result.returncode == 0, result.stderr[-4000:]
    reference = json.loads((base / "outputs/metrics.json").read_text())
    actual = json.loads((current / "outputs/metrics.json").read_text())
    assert actual["ecosystem"] == reference["ecosystem"]
    assert actual["coverage"] == reference["coverage"]
    assert actual["edge_counts_by_tier"] == reference["edge_counts_by_tier"]
