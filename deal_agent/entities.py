"""Exact alias resolution to existing nodes; never create nodes automatically."""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path


def normalise(name: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name).casefold()).strip()


class Resolver:
    def __init__(self, nodes: list[dict], aliases: dict[str, list[str]]):
        self.nodes = {row["node"]: row for row in nodes}
        self.aliases = {}
        for canonical in self.nodes:
            for alias in [
                canonical,
                self.nodes[canonical].get("ticker", ""),
                *aliases.get(canonical, []),
            ]:
                if not alias:
                    continue
                key = normalise(alias)
                if key in self.aliases and self.aliases[key] != canonical:
                    raise ValueError(f"ambiguous alias {alias!r}")
                self.aliases[key] = canonical

    @classmethod
    def from_csv(cls, path: Path, aliases: dict):
        with path.open(newline="", encoding="utf-8") as handle:
            return cls(list(csv.DictReader(handle)), aliases)

    def resolve(self, name: str) -> str | None:
        return self.aliases.get(normalise(name))

    def mentioned(self, text: str) -> set[str]:
        text = normalise(text)
        return {
            canonical
            for alias, canonical in self.aliases.items()
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text)
        }
