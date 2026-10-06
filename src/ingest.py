"""Phase 1 ingestion: SEC submissions, XBRL companyfacts, and filing text.

SEC EDGAR only. Rate limited, cached, retried. Writes:
  data/interim/xbrl_facts.csv     tidy XBRL observations for the concepts we need
  data/interim/filings_index.csv  one row per retrieved filing document
  data/raw/filings/*              cached raw documents
  outputs/coverage.md             what was found and what is missing
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path

from .entities import SEED, filer_nodes, resolve_ciks, write_nodes
from .sec_client import SecClient
from .util import ROOT, ensure_dirs, get_logger, load_config

LOG = get_logger("ingest")

INTERIM = ROOT / "data" / "interim"
OUTPUTS = ROOT / "outputs"

# Forms we care about and how deep to go.
PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "S-1", "S-1/A", "DEF 14A", "424B4", "424B5"}
EVENT_FORMS = {"8-K", "8-K/A", "6-K"}
# 8-K items that signal financing or material agreements.
ITEM_PATTERNS = {
    "1.01": re.compile(r"Item\s*1\.01", re.I),
    "2.03": re.compile(r"Item\s*2\.03", re.I),
    "3.02": re.compile(r"Item\s*3\.02", re.I),
    "1.02": re.compile(r"Item\s*1\.02", re.I),
    "7.01": re.compile(r"Item\s*7\.01", re.I),
    "8.01": re.compile(r"Item\s*8\.01", re.I),
}

FILING_FIELDS = ["node", "cik", "form", "filing_date", "accession_no", "primary_document",
                 "doc_url", "items_reported", "items_matched", "local_path", "bytes",
                 "report_date", "primary_doc_description"]


def iter_recent_filings(subs: dict, since: str) -> list[dict]:
    """Flatten submissions 'recent' plus any older quarterly files already cached."""
    out = []
    recent = subs.get("filings", {}).get("recent", {})
    n = len(recent.get("accessionNumber", []))
    for i in range(n):
        fdate = recent["filingDate"][i]
        if fdate < since:
            continue
        out.append({
            "form": recent["form"][i],
            "filing_date": fdate,
            "accession_no": recent["accessionNumber"][i],
            "primary_document": recent.get("primaryDocument", [""] * n)[i],
            "items": recent.get("items", [""] * n)[i],
            "report_date": recent.get("reportDate", [""] * n)[i],
            "primary_doc_description": recent.get("primaryDocDescription", [""] * n)[i],
        })
    return out


def text_of(raw: bytes) -> str:
    """Strip HTML to text cheaply. lxml if available, regex fallback."""
    try:
        from lxml import html as lxml_html
        doc = lxml_html.fromstring(raw)
        for bad in doc.xpath("//script|//style"):
            bad.getparent().remove(bad)
        txt = doc.text_content()
    except Exception:
        txt = re.sub(rb"<[^>]+>", b" ", raw).decode("utf-8", "replace")
    txt = txt.replace("\xa0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", txt)


def ingest(limit_per_node: int | None = None, force: bool = False) -> dict:
    cfg = load_config()
    since = cfg["sec"]["since"]
    ensure_dirs(INTERIM, OUTPUTS)
    client = SecClient(cfg)

    LOG.info("resolving CIKs from SEC company_tickers.json")
    write_nodes(resolve_ciks(client))
    nodes = filer_nodes()
    LOG.info("%d filer nodes: %s", len(nodes), ", ".join(n["node"] for n in nodes))

    from .xbrl import extract_facts

    fact_rows: list[dict] = []
    filing_rows: list[dict] = []
    per_node_summary: dict[str, dict] = {}

    for node in nodes:
        name, cik = node["node"], node["cik"]
        summary = {"submissions": False, "companyfacts": False, "facts": 0,
                   "filings_listed": 0, "docs_fetched": 0, "docs_failed": 0,
                   "forms": {}}

        subs = client.submissions(cik, force=force)
        if subs:
            summary["submissions"] = True
            summary["sec_name"] = subs.get("name", "")
            summary["sic"] = subs.get("sicDescription", "")
            summary["fiscal_year_end"] = subs.get("fiscalYearEnd", "")
        else:
            LOG.error("no submissions for %s (CIK %s)", name, cik)
            per_node_summary[name] = summary
            continue

        cf = client.companyfacts(cik, force=force)
        if cf:
            summary["companyfacts"] = True
            rows = extract_facts(cf, name)
            fact_rows.extend(rows)
            summary["facts"] = len(rows)
            LOG.info("%-10s %5d XBRL observations of interest", name, len(rows))
        else:
            LOG.warning("no companyfacts for %s", name)

        filings = iter_recent_filings(subs, since)
        wanted = [f for f in filings
                  if f["form"] in PERIODIC_FORMS or f["form"] in EVENT_FORMS]
        summary["filings_listed"] = len(wanted)
        if limit_per_node:
            # Keep the newest periodic filings and all events, then truncate.
            wanted = sorted(wanted, key=lambda f: f["filing_date"], reverse=True)[:limit_per_node]

        for f in wanted:
            summary["forms"][f["form"]] = summary["forms"].get(f["form"], 0) + 1
            pdoc = f["primary_document"]
            if not pdoc:
                continue
            raw = client.filing_document(cik, f["accession_no"], pdoc, force=False)
            if raw is None:
                summary["docs_failed"] += 1
                continue
            summary["docs_fetched"] += 1
            matched = ""
            if f["form"].startswith("8-K") or f["form"] == "6-K":
                txt_head = text_of(raw[:400_000])
                hits = [k for k, rx in ITEM_PATTERNS.items() if rx.search(txt_head)]
                matched = ";".join(sorted(hits))
            local = (client.cache_root / "filings" /
                     f"{f['accession_no'].replace('-', '')}_{pdoc.replace('/', '_')}")
            filing_rows.append({
                "node": name, "cik": cik, "form": f["form"],
                "filing_date": f["filing_date"], "accession_no": f["accession_no"],
                "primary_document": pdoc,
                "doc_url": client.document_url(cik, f["accession_no"], pdoc),
                "items_reported": f["items"], "items_matched": matched,
                "local_path": str(local.relative_to(ROOT)) if local.exists() else "",
                "bytes": len(raw), "report_date": f["report_date"],
                "primary_doc_description": f["primary_doc_description"],
            })
        LOG.info("%-10s %3d filings listed, %3d docs fetched, %d failed",
                 name, summary["filings_listed"], summary["docs_fetched"],
                 summary["docs_failed"])
        per_node_summary[name] = summary

    # ---- write interim tables ----
    facts_path = INTERIM / "xbrl_facts.csv"
    if fact_rows:
        cols = list(fact_rows[0].keys())
        with open(facts_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(fact_rows)
    LOG.info("wrote %d XBRL rows -> %s", len(fact_rows), facts_path)

    idx_path = INTERIM / "filings_index.csv"
    with open(idx_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FILING_FIELDS)
        w.writeheader()
        w.writerows(filing_rows)
    LOG.info("wrote %d filing rows -> %s", len(filing_rows), idx_path)

    stats = {"as_of": dt.date.today().isoformat(), "http": client.stats,
             "requests": client.limiter.calls, "nodes": per_node_summary,
             "xbrl_rows": len(fact_rows), "filing_docs": len(filing_rows)}
    (INTERIM / "ingest_stats.json").write_text(json.dumps(stats, indent=2))
    write_coverage(stats, fact_rows)
    return stats


def write_coverage(stats: dict, fact_rows: list[dict]) -> Path:
    from .xbrl import CONCEPTS, coverage
    nodes = list(stats["nodes"].keys())
    cov = coverage(fact_rows, nodes)
    groups = list(CONCEPTS.keys())
    lines = [
        "# Coverage report",
        "",
        f"Generated {stats['as_of']}. Source: SEC EDGAR only.",
        f"HTTP cache hits {stats['http']['hits']}, fetches {stats['http']['misses']}, "
        f"errors {stats['http']['errors']}, total requests {stats['requests']}.",
        "",
        "## Filer coverage",
        "",
        "| node | SEC name | submissions | companyfacts | XBRL rows | filings listed | docs fetched | docs failed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, s in stats["nodes"].items():
        lines.append(
            f"| {n} | {s.get('sec_name','')} | {'yes' if s['submissions'] else 'NO'} | "
            f"{'yes' if s['companyfacts'] else 'NO'} | {s['facts']} | "
            f"{s['filings_listed']} | {s['docs_fetched']} | {s['docs_failed']} |")
    lines += ["", "## XBRL concept-group coverage (observation counts)", "",
              "| node | " + " | ".join(groups) + " |",
              "|---|" + "---|" * len(groups)]
    for n in nodes:
        lines.append("| " + n + " | " + " | ".join(
            str(cov[n].get(g, 0)) or "0" for g in groups) + " |")

    nonfilers = [k for k, v in SEED.items() if not v[2]]
    lines += [
        "", "## Non-filers (no SEC data exists for these)", "",
        "These entities do not file periodic reports with the SEC. Every figure",
        "touching them in this project comes from a counterparty's filing or a",
        "company press release, and is reported as a range:",
        "",
    ] + [f"* {n}" for n in nonfilers]

    missing = []
    for n in nodes:
        for g in ("rpo", "purchase_obligations", "related_party", "concentration",
                  "leases_not_commenced"):
            if cov[n].get(g, 0) == 0:
                missing.append(f"* {n}: no `{g}` XBRL observations found")
    lines += ["", "## Known gaps", ""]
    lines += missing or ["* none at the concept-group level"]
    lines += [
        "",
        "Gaps are expected and meaningful. Not every filer tags remaining",
        "performance obligations in XBRL, and customer concentration is often",
        "narrative text rather than a tagged fact. Narrative disclosures are",
        "picked up by the candidate extractor instead.",
        "",
    ]
    p = OUTPUTS / "coverage.md"
    p.write_text("\n".join(lines))
    LOG.info("wrote %s", p)
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest SEC EDGAR data")
    ap.add_argument("--limit-per-node", type=int, default=None,
                    help="cap filings fetched per node (smoke tests)")
    ap.add_argument("--force", action="store_true", help="bypass cache for JSON endpoints")
    args = ap.parse_args()
    stats = ingest(limit_per_node=args.limit_per_node, force=args.force)
    print(json.dumps({"xbrl_rows": stats["xbrl_rows"],
                      "filing_docs": stats["filing_docs"],
                      "http": stats["http"]}, indent=2))


if __name__ == "__main__":
    main()
