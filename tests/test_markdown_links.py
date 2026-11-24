"""Verify relative Markdown links, images and section anchors in versioned docs."""
from functools import lru_cache
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PARSER = MarkdownIt("commonmark")


@lru_cache(maxsize=None)
def parsed(path):
    return PARSER.parse(path.read_text(encoding="utf-8"))


def anchors(path):
    ids, counts = set(), {}
    tokens = parsed(path)
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            words = "".join(t.content for t in tokens[i+1].children if t.type in {"text", "code_inline"})
            slug = re.sub(r"[^\w -]", "", words.lower()).replace(" ", "-")
            number = counts.get(slug, 0)
            ids.add(slug if not number else f"{slug}-{number}")
            counts[slug] = number+1
    ids.update(re.findall(r'<a\s+(?:name|id)=["\']([^"\']+)', path.read_text()))
    return ids


def links(tokens):
    for token in tokens:
        if token.type in {"link_open", "image"}:
            yield token.attrGet("href" if token.type == "link_open" else "src")
        if token.children:
            yield from links(token.children)


def test_relative_markdown_links_resolve():
    paths = subprocess.check_output(["git", "ls-files", "-z", "--", "*.md"], cwd=ROOT).decode().split("\0")
    errors = []
    for name in filter(None, paths):
        source = ROOT / name
        for link in links(parsed(source)):
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            dest = (source.parent / unquote(url.path)).resolve() if url.path else source
            if not dest.exists() or (url.fragment and dest.suffix.lower() == ".md"
                                     and unquote(url.fragment) not in anchors(dest)):
                errors.append(f"{name}: {link}")
    assert not errors, "\n".join(errors)
