"""Reuse the original ingestion corpus without fetching another feed or article."""
from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse

from .config import path_for
from .fetch import text_of
from .trace import digest


def import_news(cfg, store, trace, resolver, path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"News corpus missing: {path}. Run make news or use run --source fetch.")
    cached = {}
    index = cfg["_root"] / "data/interim/filings_index.csv"
    if index.exists():
        with index.open(newline="", encoding="utf-8") as handle:
            cached = {r["doc_url"]: r for r in csv.DictReader(handle)}
    stats = {"news_rows": 0, "docs_imported": 0, "news_skipped": 0,
             "import_errors": 0, "docs_fetched": 0, "input_source": "news"}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not {"url", "title", "snippet", "date", "publisher"} <= set(reader.fieldnames or []):
            raise ValueError("News corpus lacks required original ingestion columns")
        for row in reader:
            stats["news_rows"] += 1
            if row.get("financing_relevant", "true").lower() not in {"true", "1", "yes"}:
                stats["news_skipped"] += 1
                continue
            if stats["docs_imported"] >= cfg["deal_agent"]["max_documents_per_run"]:
                break
            try:
                url = row["url"]
                host = urlparse(url)
                if host.scheme not in {"http", "https"} or not host.hostname:
                    raise ValueError("News source must be an original HTTP URL")
                date.fromisoformat(row["date"])
                publisher = row["publisher"].removesuffix(" IR").removesuffix(" EDGAR")
                company = resolver.resolve(publisher) or ("Alphabet" if publisher == "Alphabet DeepMind" else "")
                primary = cached.get(url, {})
                source = cfg["_root"] / primary.get("local_path", "")
                if primary.get("local_path") and source.is_file():
                    raw = source.read_bytes()
                    text = text_of(raw)
                    company = resolver.resolve(primary["node"]) or company
                    scope = "cached_primary_filing"
                    accession = primary.get("accession_no", "")
                else:
                    # Snippets are evidence only for what is present, not the
                    # unseen body behind a source URL. No article download.
                    text = (row["title"].strip() + "\n\n" + row["snippet"].strip()).strip()
                    raw = text.encode()
                    scope = "news_title_and_snippet_only"
                    accession = row.get("accession_no", "")
                if not text:
                    raise ValueError("Empty stored news evidence")
                existing = store.rows("SELECT meta FROM jobs WHERE url=? AND done=1", (url,))
                if existing and json.loads(existing[0]["meta"]).get("source_scope") != "news_title_and_snippet_only" and scope == "news_title_and_snippet_only":
                    stats["news_skipped"] += 1
                    continue
                tier = "T1" if accession and (host.hostname == "sec.gov" or host.hostname.endswith(".sec.gov")) else ("T2" if row.get("source_kind") == "ir_rss" and company else "T3")
                meta = {"source_url": url, "company": company, "published_date": row["date"],
                        "doc_type": primary.get("form") or "news_item",
                        "evidence_tier": tier, "accession_no": accession,
                        "source_scope": scope, "date_scope": "Original ingestion date may be a feed/crawl date; verify the announcement date before approval",
                        "ingestion_item_id": row.get("item_id", "")}
                store.job(url, "document", meta)
                _, new = store.save_document(meta, raw, text, path_for(cfg, "raw_dir"))
                stats["docs_imported"] += int(new)
            except (ValueError, OSError, KeyError) as exc:
                stats["import_errors"] += 1
                store.issue(trace.run_id, None, "import.news", str(exc))
    trace.event("import.news", {"path": str(path), "sha256": digest(path.read_bytes())}, stats)
    return stats
