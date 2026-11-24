import json
import shutil

import pytest

from deal_agent.config import ROOT
from deal_agent.splits import partitions


def test_frozen_membership_labels_and_group_isolation(tmp_path):
    gold = ROOT / "eval/gold"
    docs = json.loads((gold / "manifest.json").read_text())["documents"]
    split = partitions(gold, docs)
    assert len(split["test"]) >= 0.4 * len(docs)
    urls = [{d["source_url"] for d in docs if d["id"] in split[s]} for s in ("dev", "test")]
    assert urls[0].isdisjoint(urls[1])
    for side, n, positives, uncertain in [("dev", 15, 10, 3), ("test", 10, 7, 2)]:
        rows = [d for d in docs if d["id"] in split[side]]
        assert (len(rows), sum(d["relevant"] for d in rows), sum(d["label_uncertain"] for d in rows)) == (n, positives, uncertain)
    victim = next(d for d in docs if d["id"] in split["test"])
    victim["label_notes"] += " changed"
    with pytest.raises(ValueError, match="test labels"):
        partitions(gold, docs)
    shutil.copy(gold / "splits.json", tmp_path)
    with (tmp_path / "splits.json").open("a") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="split hash"):
        partitions(tmp_path, docs)
