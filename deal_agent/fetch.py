"""Incremental SEC submissions + EX-99.1 discovery, and configured RSS/Atom.

Persist discovery jobs BEFORE advancing cursors. A failed download remains queued
regardless of the next scan date; no latest-run watermark can hide a failure.
"""

from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.sec_client import RateLimiter
from src.util import load_env

from .config import path_for
from .trace import digest


def text_of(raw: bytes) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for bad in soup(["script", "style", "noscript", "ix:header"]):
        bad.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


class HTTP:
    def __init__(self, cfg, trace):
        self.cfg, self.trace = cfg, trace
        self.limiter = RateLimiter(
            min(
                float(cfg["sec"]["max_requests_per_second"]),
                1 / cfg["deal_agent"]["polite_delay_seconds"],
            )
        )
        self.session = requests.Session()
        self.timeout = cfg["sec"]["timeout_seconds"]

    def get(self, url: str) -> bytes:
        original = url
        for redirect in range(6):
            parsed = urlparse(url)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                raise ValueError(f"Not an HTTP document: {url}")
            sec = parsed.hostname == "sec.gov" or parsed.hostname.endswith(".sec.gov")
            headers = {"User-Agent": "RoundTripAI-LocalDealExtractor/0.1"}
            if sec:
                load_env(self.cfg["_root"] / ".env")
                ua = os.getenv("SEC_USER_AGENT", "").strip()
                if not re.search(r"\S+\s+[^\s@]+@[^\s@]+\.[^\s@]+", ua) or any(
                    word in ua.lower()
                    for word in ("example.com", "your.email", "changeme")
                ):
                    raise ValueError(
                        "Set SEC_USER_AGENT to a descriptive name and real contact email"
                    )
                headers["User-Agent"] = ua
            for attempt in range(int(self.cfg["sec"]["retries"])):
                if sec:
                    self.limiter.acquire()
                else:
                    time.sleep(self.cfg["deal_agent"]["polite_delay_seconds"])
                response = self.trace.call(
                    "fetch.http",
                    {
                        "url": url,
                        "method": "GET",
                        "attempt": attempt,
                        "redirect": redirect,
                    },
                    lambda: self.session.get(
                        url,
                        headers=headers,
                        timeout=self.timeout,
                        allow_redirects=False,
                    ),
                    summarize=lambda r: {
                        "status": r.status_code,
                        "bytes": len(r.content),
                        "sha256": digest(r.content),
                    },
                )
                if response.status_code in {403, 429, 500, 502, 503, 504}:
                    wait = min(30, self.cfg["sec"]["backoff_base_seconds"] * 2**attempt)
                    try:
                        wait = min(
                            30, max(wait, float(response.headers.get("Retry-After", 0)))
                        )
                    except ValueError:
                        pass
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                break
            else:
                raise RuntimeError(f"HTTP retries exhausted for {url}")
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue  # SEC redirects receive the contact UA and limiter too
            return response.content
        raise RuntimeError(f"Too many redirects for {original}")


def filing_rows(data: dict, since: str):
    recent = data.get("filings", {}).get("recent", data)
    for index, accession in enumerate(recent.get("accessionNumber", [])):

        def get(key):
            values = recent.get(key, [])
            return values[index] if index < len(values) else ""

        if get("filingDate") >= since and get("form") in {
            "8-K",
            "8-K/A",
            "10-Q",
            "10-K",
        }:
            yield {
                "accession_no": accession,
                "published_date": get("filingDate"),
                "doc_type": get("form"),
                "filename": get("primaryDocument"),
            }


def exhibit_urls(raw: bytes, index_url: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    result = []
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if len(cells) >= 4 and cells[3].get_text(strip=True).upper() == "EX-99.1":
            link = cells[2].find("a", href=True)
            if link:
                result.append(urljoin(index_url, link["href"]))
    return result


def feed_entries(raw: bytes, feed_url: str) -> list[dict]:
    root = ET.fromstring(raw)
    # Namespace-insensitive RSS/Atom parsing, no executing external entities.
    result = []
    for element in root.iter():
        if element.tag.split("}")[-1] not in {"item", "entry"}:
            continue
        values = {}
        link = ""
        for child in element:
            tag = child.tag.split("}")[-1]
            values[tag] = "".join(child.itertext()).strip()
            if tag == "link" and child.get("rel", "alternate") == "alternate":
                link = child.get("href") or values[tag]
        published = (
            values.get("published")
            or values.get("pubDate")
            or values.get("updated", "")
        )
        try:
            day = date.fromisoformat(published[:10]).isoformat()
        except ValueError:
            try:
                day = parsedate_to_datetime(published).date().isoformat()
            except (ValueError, TypeError, OverflowError):
                day = ""  # Keep undated entries; reviewer must establish date.
        if link:
            result.append(
                {
                    "source_url": urljoin(feed_url, link),
                    "published_date": day,
                    "title": values.get("title", ""),
                    "doc_type": "company_release",
                }
            )
    return result


def fetch(cfg, store, trace, resolver, *, no_sec=False, http=None) -> dict:
    http = http or HTTP(cfg, trace)
    stats = {
        "docs_fetched": 0,
        "content_duplicates": 0,
        "fetch_errors": 0,
        "fetch_error_details": [],
    }
    agent = cfg["deal_agent"]

    def failed(document, stage, exc):
        stats["fetch_errors"] += 1
        stats["fetch_error_details"].append(
            {"source": document, "stage": stage, "error": str(exc)}
        )
        store.issue(trace.run_id, document, stage, exc)
        trace.event(stage, {"source": document}, {"error": str(exc)})

    if not no_sec:
        for company in agent["watchlist"]:
            try:
                node = resolver.nodes[company]
                if not node.get("cik"):
                    continue
                cik = str(int(node["cik"]))
                url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
                cursor = store.rows("SELECT since FROM cursors WHERE source=?", (url,))
                since = agent["initial_since"]
                if cursor:
                    since = max(
                        since,
                        (
                            date.fromisoformat(cursor[0]["since"])
                            - timedelta(days=agent["overlap_days"])
                        ).isoformat(),
                    )
                data = json.loads(http.get(url))
                batches = [data]
                for history in data.get("filings", {}).get("files", []):
                    if history.get("filingTo", "") >= since:
                        batches.append(
                            json.loads(http.get(urljoin(url, history["name"])))
                        )
                for batch in batches:
                    for row in filing_rows(batch, since):
                        base = (
                            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                            f"{row['accession_no'].replace('-', '')}/"
                        )
                        meta = {**row, "company": company, "evidence_tier": "T1"}
                        if row["filename"]:
                            store.job(
                                base + row["filename"],
                                "document",
                                {**meta, "source_url": base + row["filename"]},
                            )
                        if row["doc_type"].startswith("8-K"):
                            index = base + row["accession_no"] + "-index.html"
                            store.job(index, "index", meta)
                store.db.execute(
                    "INSERT OR REPLACE INTO cursors VALUES(?,?)",
                    (url, date.today().isoformat()),
                )
            except Exception as exc:
                failed(company, "fetch.sec_discovery", exc)

    for feed in agent["feeds"]:
        try:
            for entry in feed_entries(http.get(feed["url"]), feed["url"]):
                if (
                    entry["published_date"]
                    and entry["published_date"] < agent["initial_since"]
                ):
                    continue
                store.job(
                    entry["source_url"],
                    "document",
                    {
                        **entry,
                        "company": feed["company"],
                        "evidence_tier": "T2",
                        "accession_no": "",
                    },
                )
        except Exception as exc:
            failed(feed["url"], "fetch.feed", exc)

    # Cached job identities survive failed requests, process crashes and cursors.
    for job in store.rows(
        "SELECT * FROM jobs WHERE kind='index' AND done=0 ORDER BY url"
    ):
        try:
            if no_sec:
                continue
            raw = http.get(job["url"])
            meta = json.loads(job["meta"])
            for url in exhibit_urls(raw, job["url"]):
                store.job(
                    url, "document", {**meta, "source_url": url, "doc_type": "EX-99.1"}
                )
            store.db.execute("UPDATE jobs SET done=1 WHERE url=?", (job["url"],))
        except Exception as exc:
            failed(job["url"], "fetch.exhibits", exc)

    jobs = store.rows(
        "SELECT * FROM jobs WHERE kind='document' AND done=0 ORDER BY url"
    )
    limit = agent.get("max_documents_per_run")
    if no_sec:
        jobs = [j for j in jobs if json.loads(j["meta"])["evidence_tier"] != "T1"]
    for job in jobs[:limit] if limit else jobs:
        try:
            raw = http.get(job["url"])
            text = text_of(raw)
            if not text:
                raise ValueError("Empty document; retryable fetch error")
            ident, new = trace.call(
                "fetch.store_document",
                {"url": job["url"], "raw_sha256": digest(raw)},
                lambda: store.save_document(
                    json.loads(job["meta"]), raw, text, path_for(cfg, "raw_dir")
                ),
            )
            stats["docs_fetched"] += int(new)
            stats["content_duplicates"] += int(not new)
        except Exception as exc:
            failed(job["url"], "fetch.document", exc)
    return stats
