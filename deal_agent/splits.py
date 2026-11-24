"""Select a named benchmark partition before evaluation opens any source text.
The frozen manifest binds test membership, source identities and adjudications.
The benchmark and the review-feedback exporter share these identities.
"""
import json

from .trace import digest

SPLIT_SHA256 = "6779a7bea0aea20beb9988d04a82e726e25dc2768690501f0b9e0b540482a6f5"


def partitions(directory, documents):
    raw = (directory / "splits.json").read_bytes()
    if digest(raw) != SPLIT_SHA256:
        raise ValueError("Frozen split hash mismatch")
    split = json.loads(raw)
    dev, test = set(split["dev"]), set(split["test"])
    by_id = {d["id"]: d for d in documents}
    if dev & test or set(by_id) != dev | test or len(by_id) != len(documents):
        raise ValueError("Split membership differs from the gold manifest")
    locked = [by_id[key] for key in sorted(test)]
    if digest(json.dumps(locked, sort_keys=True, separators=(",", ":"))) != split["test_records_sha256"]:
        raise ValueError("Frozen test labels or source identities changed")
    return split
