"""Build the static interview pages from the public walkthrough, scorecard and example."""
from __future__ import annotations

import json
from html import escape
from markdown_it import MarkdownIt

from .config import ROOT
from .explain import render
from .pending import review_item


def assets():
    guide = (ROOT / "docs/WALKTHROUGH.md").read_text()
    five_minutes = guide.split("## Five minutes\n", 1)[1].split("\n## ", 1)[0]
    example = ROOT / "eval/example"
    story = json.loads((example / "story.json").read_text())
    story["events"] = [json.loads(line) for line in (example / "trace.jsonl").read_text().splitlines()]
    item = review_item(story["id"], story["deal"], story["verification"], story["reconcile"])
    parser = MarkdownIt("commonmark").enable("table")

    def page(title, content):
        return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Round-Trip AI</title><link rel="stylesheet" href="../styles.css">
<main class="reading"><a href="../index.html">← Research dashboard</a><h1>{escape(title)}</h1>
{content}</main></html>
"""

    # The static mirror serves the same five-minute text. Relative references in
    # this section resolve locally even when the dashboard is served without Git.
    five_minutes = five_minutes.replace("(TRACE_EXAMPLE.md)", "(trace.txt)").replace(
        "(../eval/RESULTS-dev.md)", "(development.html)")
    scores = (ROOT / "eval/RESULTS-dev.md").read_text()
    # The detailed records and runnable commands live in the checkout. Preserve
    # their paths as text here so site-only deployments never link outside site/.
    tokens = parser.parse(scores.partition("\n")[2])
    for block in tokens:
        for token in block.children or []:
            if token.type in {"link_open", "link_close"} and token.tag == "a":
                token.tag = "span"
                token.attrs.clear()
    score_html = parser.renderer.render(tokens, parser.options, {})
    result = page("Development evaluation", score_html)
    return {
        "site/guide/walkthrough.html": page("Five-minute walkthrough", parser.render(five_minutes)),
        "site/guide/development.html": result,
        "site/guide/trace.txt": render(story) + "\n",
        "site/data/recorded_example.json": json.dumps(item, indent=2) + "\n",
    }


if __name__ == "__main__":
    for name, body in assets().items():
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
