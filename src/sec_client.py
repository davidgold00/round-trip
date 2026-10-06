"""SEC EDGAR client: declared User-Agent, <=5 req/s, disk cache, retries, logging.

No paid APIs. No LLM calls. Everything here hits sec.gov only.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .util import ROOT, ensure_dirs, get_logger, load_config, load_env, sha1

LOG = get_logger("sec")

PLACEHOLDERS = {"", "your name your@email.com", "name email", "changeme",
                "you@example.com", "your-email@example.com"}


class MissingUserAgentError(RuntimeError):
    pass


class RateLimiter:
    """Token-bucket style limiter: never more than `rps` requests per second.

    Deliberately simple and thread-safe: it serialises on a lock and sleeps
    until the oldest of the last `rps` request timestamps is a second old.
    """

    def __init__(self, rps: float):
        self.rps = float(rps)
        self.min_interval = 1.0 / self.rps
        self._lock = threading.Lock()
        self._last = 0.0
        self.calls = 0

    def acquire(self, _sleep=time.sleep, _now=time.monotonic) -> float:
        with self._lock:
            now = _now()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                _sleep(wait)
                now = _now() + wait if _now() == now else _now()
            self._last = max(now, self._last + self.min_interval)
            self.calls += 1
            return max(0.0, wait)


def resolve_user_agent() -> str:
    load_env()
    cfg = load_config()
    key = cfg["sec"]["user_agent_env"]
    ua = (os.environ.get(key) or "").strip().strip('"').strip("'")
    if ua.lower() in PLACEHOLDERS or "@" not in ua:
        raise MissingUserAgentError(
            f"{key} is unset or not a usable contact string. SEC requires a "
            f"declared User-Agent of the form 'Name email@domain'. Set it in "
            f".env or the environment and re-run."
        )
    return ua


class SecClient:
    def __init__(self, cfg: dict | None = None, offline: bool = False):
        self.cfg = cfg or load_config()
        s = self.cfg["sec"]
        self.offline = offline or os.environ.get("RT_OFFLINE") == "1"
        self.ua = "unset-offline" if self.offline else resolve_user_agent()
        self.limiter = RateLimiter(s["max_requests_per_second"])
        self.retries = int(s["retries"])
        self.backoff = float(s["backoff_base_seconds"])
        self.timeout = int(s["timeout_seconds"])
        self.cache_root = ROOT / s["cache_dir"]
        ensure_dirs(self.cache_root)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Encoding": "gzip, deflate",
            "Host": None,  # set per request below
        })
        self.session.headers.pop("Host", None)
        self.stats = {"hits": 0, "misses": 0, "errors": 0, "bytes": 0}

    # ---------- cache ----------
    def _cache_path(self, url: str, subdir: str, name: str | None = None) -> Path:
        d = self.cache_root / subdir
        ensure_dirs(d)
        if name:
            return d / name
        return d / f"{sha1(url)}.cache"

    def get(self, url: str, subdir: str = "misc", name: str | None = None,
            force: bool = False, binary: bool = False) -> bytes | None:
        """Fetch with cache. Returns bytes, or None on permanent failure."""
        path = self._cache_path(url, subdir, name)
        if path.exists() and not force:
            self.stats["hits"] += 1
            return path.read_bytes()
        if self.offline:
            LOG.debug("offline, cache miss for %s", url)
            return None
        last_err: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.acquire()
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    path.write_bytes(r.content)
                    self.stats["misses"] += 1
                    self.stats["bytes"] += len(r.content)
                    return r.content
                if r.status_code in (403, 429, 500, 502, 503, 504):
                    sleep_for = self.backoff * (2 ** attempt)
                    LOG.warning("HTTP %s on %s, backing off %.1fs (attempt %d/%d)",
                                r.status_code, url, sleep_for, attempt + 1, self.retries)
                    time.sleep(sleep_for)
                    continue
                if r.status_code == 404:
                    LOG.info("404 %s", url)
                    self.stats["errors"] += 1
                    return None
                LOG.warning("HTTP %s on %s", r.status_code, url)
                self.stats["errors"] += 1
                return None
            except requests.RequestException as exc:  # network flake
                last_err = exc
                sleep_for = self.backoff * (2 ** attempt)
                LOG.warning("%s on %s, retry in %.1fs", type(exc).__name__, url, sleep_for)
                time.sleep(sleep_for)
        self.stats["errors"] += 1
        LOG.error("gave up on %s (%s)", url, last_err)
        return None

    def get_json(self, url: str, subdir: str = "misc", name: str | None = None,
                 force: bool = False) -> Any | None:
        raw = self.get(url, subdir=subdir, name=name, force=force)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            LOG.error("bad JSON from %s", url)
            return None

    # ---------- EDGAR endpoints ----------
    def company_tickers(self, force: bool = False) -> dict | None:
        return self.get_json("https://www.sec.gov/files/company_tickers.json",
                             subdir=".", name="company_tickers.json", force=force)

    def submissions(self, cik: str, force: bool = False) -> dict | None:
        cik10 = str(cik).zfill(10)
        return self.get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json",
                             subdir="submissions", name=f"CIK{cik10}.json", force=force)

    def companyfacts(self, cik: str, force: bool = False) -> dict | None:
        cik10 = str(cik).zfill(10)
        return self.get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
            subdir="companyfacts", name=f"CIK{cik10}.json", force=force)

    def filing_index(self, cik: str, accession: str, force: bool = False) -> dict | None:
        acc = accession.replace("-", "")
        cikn = str(int(cik))
        return self.get_json(
            f"https://www.sec.gov/Archives/edgar/data/{cikn}/{acc}/index.json",
            subdir="filings", name=f"{acc}_index.json", force=force)

    def filing_document(self, cik: str, accession: str, filename: str,
                        force: bool = False) -> bytes | None:
        acc = accession.replace("-", "")
        cikn = str(int(cik))
        url = f"https://www.sec.gov/Archives/edgar/data/{cikn}/{acc}/{filename}"
        safe = f"{acc}_{filename.replace('/', '_')}"
        return self.get(url, subdir="filings", name=safe, force=force)

    def document_url(self, cik: str, accession: str, filename: str) -> str:
        return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession.replace('-', '')}/{filename}")

    def atom_8k(self, cik: str, count: int = 40, force: bool = True) -> bytes | None:
        """8-K Atom feed for a CIK. Used by the news monitor."""
        cik10 = str(cik).zfill(10)
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
               f"&CIK={cik10}&type=8-K&dateb=&owner=include&count={count}"
               "&output=atom")
        return self.get(url, subdir="news", name=f"atom_8k_{cik10}.xml", force=force)
