"""Phase 4: news and funding monitor. All free sources, terms-compliant.

Sources
  * SEC EDGAR 8-K Atom feeds, one per seed CIK.
  * Company IR / newsroom RSS where the publisher offers one.
  * GDELT DOC 2.0 API (free, no key).

Storage policy: headline, link, date, publisher and a short snippet only. Full
article text is never fetched or stored.

Tagging: keyword rules plus semantic similarity. Similarity uses a LOCAL
sentence-transformers model if one is installed, otherwise TF-IDF cosine. No
LLM API is called anywhere.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from .entities import SEED, alias_map, filer_nodes
from .sec_client import SecClient
from .util import (ROOT, ensure_dirs, get_logger, load_config, sha1, slug, today)

LOG = get_logger("news")

INTERIM = ROOT / "data" / "interim"
RAW_NEWS = ROOT / "data" / "raw" / "news"
SITE_DATA = ROOT / "site" / "data"
FEED_CSV = INTERIM / "news_items.csv"

NEWS_FIELDS = ["item_id", "date", "publisher", "source_kind", "title", "url",
               "snippet", "entities", "tags", "score", "financing_relevant",
               "cluster_id", "first_seen", "accession_no", "items_reported",
               "financing_item"]

# Company IR / newsroom feeds that publish an RSS or Atom document.
IR_FEEDS = {
    "Nvidia": "https://nvidianews.nvidia.com/releases.xml",
    "AMD": "https://ir.amd.com/rss/news-releases.xml",
    "Microsoft": "https://news.microsoft.com/feed/",
    "Amazon": "https://press.aboutamazon.com/rss/news-releases.xml",
    "Anthropic": "https://www.anthropic.com/rss.xml",
    "Alphabet": "https://blog.google/rss/",
    "Meta": "https://about.fb.com/news/feed/",
}

# Financing-relevant concept phrases. These seed both the keyword rules and the
# semantic reference set.
CONCEPTS = [
    "equity investment in an artificial intelligence company",
    "letter of intent to invest",
    "convertible notes offering",
    "loan guarantee or credit support for a data center lease",
    "warrant to purchase shares tied to purchase milestones",
    "vendor financing provided to a customer",
    "multi-year cloud capacity commitment",
    "purchase commitment for AI accelerators",
    "remaining performance obligations or backlog update",
    "funding round at a new valuation",
    "data center lease not yet commenced",
    "capital expenditure guidance for AI infrastructure",
    "strategic partnership to deploy gigawatts of compute",
    "offtake agreement for unsold compute capacity",
]

KEYWORD_RULES: list[tuple[str, re.Pattern]] = [
    ("investment", re.compile(r"\binvest(s|ed|ing|ment)?\b|\bstake\b|\bequity\b", re.I)),
    ("commitment", re.compile(r"\bcommit(s|ted|ment|ments)?\b|\bpurchase agreement\b", re.I)),
    ("warrant", re.compile(r"\bwarrant(s)?\b", re.I)),
    ("loan_guarantee", re.compile(r"\bguarantee(s|d)?\b|\bcredit support\b|\bloan\b"
                                 r"|\bterm loan\b|\bfacility\b", re.I)),
    ("debt", re.compile(r"\bnotes\b|\bbond(s)?\b|\bconvertible\b|\bdebt\b"
                        r"|\boffering\b", re.I)),
    ("capacity_deal", re.compile(r"\bgigawatt(s)?\b|\bGW\b|\bcapacity\b|\bcompute deal\b"
                                r"|\bcloud agreement\b|\bdata cent(er|re)\b", re.I)),
    ("backlog", re.compile(r"\bbacklog\b|\bremaining performance obligation", re.I)),
    ("funding_round", re.compile(r"\bSeries [A-K]\b|\bvaluation\b|\braise(s|d)?\b"
                                r"|\bfunding round\b", re.I)),
    ("ipo", re.compile(r"\bIPO\b|\binitial public offering\b|\bS-1\b|\bdirect listing\b", re.I)),
]

MONEY_HINT = re.compile(r"\$\s?[0-9][0-9,.]*\s*(trillion|billion|million|bn|m\b|b\b)?", re.I)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------
def _session(ua: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept": "application/rss+xml, application/xml, */*"})
    return s


ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def _text(el, *paths: str) -> str:
    """Find the first non-empty match, trying plain and Atom-namespaced tags.

    ElementTree cannot resolve an `a:` prefix without being handed the namespace
    map, so every lookup is tried both ways. Getting this wrong silently empties
    every Atom title, which is how the EDGAR feed came back with zero items.
    """
    for p in paths:
        for found in (el.find(p), el.find(p, ATOM_NS) if ":" in p else None):
            if found is None:
                continue
            if (found.text or "").strip():
                return found.text.strip()
            if found.get("href"):
                return found.get("href").strip()
    return ""


def parse_feed(raw: bytes, publisher: str, source_kind: str) -> list[dict]:
    """Parse RSS 2.0 or Atom. Headline, link, date, publisher, short snippet only."""
    items: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return items
    ns = ATOM_NS
    entries = root.findall(".//item") or root.findall(".//a:entry", ns)
    for e in entries:
        title = _text(e, "title", "a:title")
        link = _text(e, "link", "a:link")
        if not link:
            lk = e.find("a:link", ns)
            link = lk.get("href", "") if lk is not None else ""
        date = (_text(e, "pubDate", "a:updated", "a:published", "{http://purl.org/dc/elements/1.1/}date")
                or "")
        desc = _text(e, "description", "a:summary", "a:content")
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        if not title or not link:
            continue
        items.append({
            "title": title[:300], "url": link, "raw_date": date,
            "publisher": publisher, "source_kind": source_kind,
            "snippet": desc[:280],          # short snippet only, never full text
        })
    return items


def normalise_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%a, %d %b %Y %H:%M %z"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return m.group(0)
    return ""


ITEM_LABELS = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "2.03": "Creation of a Direct Financial Obligation",
    "3.02": "Unregistered Sales of Equity Securities",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
}
FINANCING_ITEMS = {"1.01", "1.02", "2.03", "3.02"}


def fetch_edgar_8k(client: SecClient, cfg: dict) -> list[dict]:
    """Recent 8-K and 6-K filings, from the submissions API.

    The browse-edgar Atom feed titles every entry "8-K - Current report", which
    is useless for a financing monitor. The submissions API carries the Item
    codes, so Item 1.01 material agreements and Item 2.03 and 3.02 financings can
    be surfaced by name. The Atom feed is still fetched as a freshness check.
    """
    out: list[dict] = []
    since = (dt.date.today()
             - dt.timedelta(days=int(cfg["news"].get("lookback_days", 45)) * 6)).isoformat()
    for node in filer_nodes():
        subs = client.submissions(node["cik"], force=True)
        client.atom_8k(node["cik"], count=40, force=True)  # freshness probe, cached
        if not subs:
            LOG.warning("no submissions for %s", node["node"])
            continue
        rec = subs.get("filings", {}).get("recent", {})
        n = len(rec.get("accessionNumber", []))
        for i in range(n):
            form = rec["form"][i]
            if not (form.startswith("8-K") or form == "6-K"):
                continue
            fdate = rec["filingDate"][i]
            if fdate < since:
                continue
            acc = rec["accessionNumber"][i]
            items = [x.strip() for x in str(rec.get("items", [""] * n)[i]).split(",") if x.strip()]
            labels = [f"Item {x} {ITEM_LABELS.get(x, '')}".strip() for x in items]
            desc = str(rec.get("primaryDocDescription", [""] * n)[i])
            title = (f"{node['node']} files {form}"
                     + (": " + "; ".join(labels) if labels else ""))
            out.append({
                "title": title[:300],
                "url": (f"https://www.sec.gov/Archives/edgar/data/{int(node['cik'])}/"
                        f"{acc.replace('-', '')}/{acc}-index.htm"),
                "raw_date": fdate,
                "publisher": "SEC EDGAR",
                "source_kind": "edgar_8k",
                "snippet": (desc + (" | items: " + ",".join(items) if items else ""))[:280],
                "entities": node["node"],
                "accession_no": acc,
                "items_reported": ",".join(items),
                "financing_item": str(bool(set(items) & FINANCING_ITEMS)).lower(),
            })
    LOG.info("EDGAR 8-K/6-K from submissions: %d items", len(out))
    return out


def fetch_ir_feeds(ua: str) -> list[dict]:
    s = _session(ua)
    out: list[dict] = []
    for name, url in IR_FEEDS.items():
        try:
            r = s.get(url, timeout=20)
            if r.status_code != 200:
                LOG.info("IR feed %s -> HTTP %s", name, r.status_code)
                continue
            items = parse_feed(r.content, publisher=f"{name} IR", source_kind="ir_rss")
            for it in items:
                it["entities"] = name
            out.extend(items)
            LOG.info("IR feed %-10s %3d items", name, len(items))
        except requests.RequestException as exc:
            LOG.info("IR feed %s failed: %s", name, type(exc).__name__)
    return out


def fetch_gdelt(cfg: dict, ua: str) -> list[dict]:
    """GDELT DOC 2.0. Free, no key, no paid tier. Headlines and links only."""
    if not cfg["news"].get("gdelt_enabled", True):
        return []
    import time
    s = _session(ua)
    names = [n for n in SEED] + ["Nscale"]
    # GDELT throttles aggressively (HTTP 429 on back-to-back calls), so the
    # entity list is batched into a handful of OR-grouped queries and each call
    # is spaced out. Fifteen one-per-entity queries got rate limited.
    verbs = ("invest OR commitment OR warrant OR guarantee OR backlog "
             "OR gigawatt OR funding OR valuation")
    batch = 4
    groups = [names[i:i + batch] for i in range(0, len(names), batch)]
    queries = [f'({" OR ".join(chr(34) + g + chr(34) for g in grp)}) ({verbs})'
               for grp in groups]
    gap = 6.0
    out: list[dict] = []
    span = int(cfg["news"].get("lookback_days", 45))
    maxrec = int(cfg["news"].get("gdelt_max_records", 75))
    for qi, q in enumerate(queries):
        if qi:
            time.sleep(gap)
        params = {"query": q, "mode": "ArtList", "format": "json",
                  "maxrecords": str(maxrec), "timespan": f"{span}d",
                  "sort": "DateDesc"}
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 429:
                LOG.info("GDELT rate limited, backing off %.0fs", gap * 2)
                time.sleep(gap * 2)
                r = s.get(url, timeout=30)
            if r.status_code != 200:
                LOG.info("GDELT HTTP %s for %s", r.status_code, q[:50])
                continue
            data = r.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            LOG.info("GDELT failed for %s: %s", q[:40], type(exc).__name__)
            continue
        for art in data.get("articles", []):
            out.append({
                "title": (art.get("title") or "")[:300],
                "url": art.get("url", ""),
                "raw_date": art.get("seendate", ""),
                "publisher": art.get("domain", "unknown"),
                "source_kind": "gdelt",
                "snippet": "",        # GDELT gives no body text and we store none
                "entities": "",
            })
    LOG.info("GDELT: %d items", len(out))
    return out


# ---------------------------------------------------------------------------
# Tagging: keyword rules + local semantic similarity, TF-IDF fallback
# ---------------------------------------------------------------------------
class Tagger:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.threshold = float(cfg["news"]["similarity_threshold"])
        self.mode = "tfidf"
        self.model = None
        self.ref = None
        self._try_embeddings()
        if self.model is None:
            self._build_tfidf()

    def _try_embeddings(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa
        except Exception:
            LOG.info("sentence-transformers not installed, using TF-IDF similarity")
            return
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.cfg["news"]["embed_model"])
            self.ref = self.model.encode(CONCEPTS, normalize_embeddings=True)
            self.mode = "sentence-transformers (local)"
            LOG.info("using local embedding model %s", self.cfg["news"]["embed_model"])
        except Exception as exc:
            LOG.info("local model unavailable (%s), using TF-IDF similarity",
                     type(exc).__name__)
            self.model = None

    def _build_tfidf(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(stop_words="english", sublinear_tf=True,
                                   ngram_range=(1, 2), min_df=1)
        self.ref = self.vec.fit_transform(CONCEPTS)
        self.mode = "tfidf (fallback)"

    def similarity(self, texts: list[str]):
        import numpy as np
        if not texts:
            return np.zeros(0)
        if self.model is not None:
            emb = self.model.encode(texts, normalize_embeddings=True)
            return (emb @ self.ref.T).max(axis=1)
        from sklearn.metrics.pairwise import cosine_similarity
        X = self.vec.transform(texts)
        return cosine_similarity(X, self.ref).max(axis=1)

    def keyword_tags(self, text: str) -> list[str]:
        return [name for name, rx in KEYWORD_RULES if rx.search(text)]


def detect_entities(text: str, amap: dict[str, str]) -> list[str]:
    found = set()
    low = text.lower()
    for alias, canon in amap.items():
        if len(alias) <= 3:
            if re.search(r"\b" + re.escape(alias) + r"\b", text):
                found.add(canon)
        elif alias in low:
            found.add(canon)
    return sorted(found)


def dedupe(items: list[dict], threshold: float) -> list[dict]:
    """Cluster near-identical headlines, keep one representative per cluster."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    if len(items) < 2:
        for i, it in enumerate(items):
            it["cluster_id"] = f"c{i}"
        return items
    titles = [re.sub(r"[^a-z0-9 ]", " ", it["title"].lower()) for it in items]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
    X = vec.fit_transform(titles)
    S = cosine_similarity(X)
    n = len(items)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if S[i, j] >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    for i, it in enumerate(items):
        it["cluster_id"] = f"c{find(i)}"
    kept: dict[str, dict] = {}
    for it in items:
        cid = it["cluster_id"]
        if cid not in kept:
            kept[cid] = it
        else:
            # prefer a filing or an IR release over a media aggregate
            rank = {"edgar_8k": 0, "ir_rss": 1, "gdelt": 2}
            if rank.get(it["source_kind"], 3) < rank.get(kept[cid]["source_kind"], 3):
                it["cluster_id"] = cid
                kept[cid] = it
    LOG.info("deduped %d items into %d clusters", len(items), len(kept))
    return list(kept.values())


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------
def news_candidates(items: list[dict]) -> list[dict]:
    """Flagged items become UNVERIFIED candidate edges in the review queue.

    They are written to a separate file from the filing-derived candidates and
    carry evidence_tier T3 (media) or T2 (company IR release). Nothing here is
    ever counted; the dashboard shows them labelled unverified until a human
    promotes them with a quote through `python -m src.review`.
    """
    out = []
    for it in items:
        if not it.get("financing_relevant"):
            continue
        ents = [e for e in (it.get("entities") or "").split(";") if e]
        if len(ents) < 2:
            continue
        tier = {"ir_rss": "T2", "edgar_8k": "T1"}.get(it["source_kind"], "T3")
        out.append({
            "candidate_id": "n_" + sha1(it["url"])[:14],
            "as_of_date": it["date"], "source_node": ents[0], "target_node": ents[1],
            "edge_type": "", "amount_usd_low": "", "amount_usd_high": "",
            "amount_basis": "notional", "term_start": "", "term_end": "",
            "status": "reported", "conditions_text": "",
            "evidence_tier": tier, "source_url": it["url"], "accession_no": "",
            "quote_snippet": "", "notes": "news monitor flag, UNVERIFIED",
            "extracted_amount_text": (MONEY_HINT.search(it["title"] + " " + it["snippet"]).group(0)
                                      if MONEY_HINT.search(it["title"] + " " + it["snippet"])
                                      else ""),
            "context_window": (it["title"] + " || " + it["snippet"])[:500],
            "rule_hit": it["tags"], "review_status": "pending", "review_reason": "",
            "filer_node": "", "form": it["source_kind"], "doc_sha": "",
            "publisher": it["publisher"], "title": it["title"],
        })
    return out


def run(skip_network: bool = False) -> dict:
    cfg = load_config()
    ensure_dirs(INTERIM, RAW_NEWS, SITE_DATA)
    client = SecClient(cfg)
    ua = client.ua

    items: list[dict] = []
    if not skip_network:
        items += fetch_edgar_8k(client, cfg)
        items += fetch_ir_feeds(ua)
        items += fetch_gdelt(cfg, ua)
    else:
        LOG.info("skip_network set, using whatever is already cached")

    amap = alias_map()
    tagger = Tagger(cfg)
    cleaned: list[dict] = []
    seen_urls: set[str] = set()
    for it in items:
        if not it.get("url") or it["url"] in seen_urls:
            continue
        seen_urls.add(it["url"])
        it["date"] = normalise_date(it.get("raw_date", "")) or today()
        blob = f"{it['title']} {it.get('snippet','')}"
        ents = set(detect_entities(blob, amap))
        for e in (it.get("entities") or "").split(";"):
            if e:
                ents.add(e)
        it["entities"] = ";".join(sorted(ents))
        it["tags"] = ";".join(tagger.keyword_tags(blob))
        it["item_id"] = sha1(it["url"])[:16]
        it["first_seen"] = today()
        cleaned.append(it)

    scores = tagger.similarity([f"{i['title']} {i.get('snippet','')}" for i in cleaned])
    for it, sc in zip(cleaned, scores):
        it["score"] = float(sc)
        # A filing or a release is relevant if either signal fires; a media item
        # needs the keyword rule AND a dollar hint or an entity pair, because
        # GDELT headlines are noisy.
        kw = bool(it["tags"])
        sem = float(sc) >= tagger.threshold
        n_ent = len([e for e in it["entities"].split(";") if e])
        if it["source_kind"] == "edgar_8k":
            # An Item 1.01, 1.02, 2.03 or 3.02 8-K is financing-relevant by
            # definition, whatever the headline text looks like.
            it["financing_relevant"] = bool(
                str(it.get("financing_item", "")).lower() == "true" or kw or sem)
        elif it["source_kind"] == "ir_rss":
            it["financing_relevant"] = bool(kw or sem)
        else:
            it["financing_relevant"] = bool(kw and (sem or n_ent >= 2))

    cleaned = dedupe(cleaned, float(cfg["news"]["dedupe_threshold"]))
    cleaned.sort(key=lambda i: (i["date"], i["source_kind"]), reverse=True)

    # Preserve first_seen across refreshes.
    prior: dict[str, dict] = {}
    if FEED_CSV.exists():
        with open(FEED_CSV) as fh:
            prior = {r["item_id"]: r for r in csv.DictReader(fh)}
    for it in cleaned:
        if it["item_id"] in prior:
            it["first_seen"] = prior[it["item_id"]].get("first_seen", it["first_seen"])
    merged = {it["item_id"]: it for it in cleaned}
    for iid, r in prior.items():
        merged.setdefault(iid, r)
    allitems = sorted(merged.values(), key=lambda i: str(i.get("date", "")), reverse=True)

    with open(FEED_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=NEWS_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(allitems)
    LOG.info("wrote %d news items -> %s", len(allitems), FEED_CSV)

    flagged = [i for i in allitems if str(i.get("financing_relevant")).lower() in ("true", "1")]
    cands = news_candidates(flagged)
    cpath = ROOT / "ledger" / "news_candidates.csv"
    prior_c: dict[str, dict] = {}
    if cpath.exists():
        with open(cpath) as fh:
            prior_c = {r["candidate_id"]: r for r in csv.DictReader(fh)}
    for c in cands:
        if c["candidate_id"] in prior_c:
            p = prior_c[c["candidate_id"]]
            c["review_status"] = p.get("review_status", "pending")
            c["review_reason"] = p.get("review_reason", "")
    merged_c = {c["candidate_id"]: c for c in cands}
    for cid, p in prior_c.items():
        merged_c.setdefault(cid, p)
    if merged_c:
        fields = list(next(iter(merged_c.values())).keys())
        with open(cpath, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(merged_c.values())
    LOG.info("news review queue: %d candidates -> %s", len(merged_c), cpath)

    payload = {
        "as_of": today(),
        "tagger_mode": tagger.mode,
        "similarity_threshold": tagger.threshold,
        "counts": {
            "total": len(allitems),
            "flagged": len(flagged),
            "by_source": {k: sum(1 for i in allitems if i.get("source_kind") == k)
                          for k in ("edgar_8k", "ir_rss", "gdelt")},
        },
        "items": [{k: i.get(k, "") for k in NEWS_FIELDS} for i in allitems[:400]],
        "review_queue": [
            {"candidate_id": c["candidate_id"], "date": c["as_of_date"],
             "source_node": c["source_node"], "target_node": c["target_node"],
             "evidence_tier": c["evidence_tier"], "status": c["review_status"],
             "title": c.get("title", ""), "publisher": c.get("publisher", ""),
             "url": c["source_url"], "tags": c["rule_hit"],
             "amount_hint": c.get("extracted_amount_text", "")}
            for c in sorted(merged_c.values(), key=lambda c: str(c.get("as_of_date","")),
                            reverse=True)[:120]],
        "sources_note": (
            "Only headline, link, date, publisher and a short snippet are stored. "
            "Full article text is never fetched. GDELT DOC 2.0 is free and needs no "
            "key. Flagged items are UNVERIFIED candidate edges and are never counted "
            "in any metric until promoted with a source quote."),
    }
    (ROOT / "outputs" / "news.json").write_text(json.dumps(payload, indent=2, default=str))
    (SITE_DATA / "news.json").write_text(json.dumps(payload, default=str))
    LOG.info("tagger=%s  total=%d flagged=%d", tagger.mode, len(allitems), len(flagged))
    return payload["counts"] | {"tagger": tagger.mode}


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull and tag financing news")
    ap.add_argument("--skip-network", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(skip_network=args.skip_network), indent=2))


if __name__ == "__main__":
    main()
