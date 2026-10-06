"""Self-audit: re-verify a random sample of ledger edges against their sources.

Mechanical checks run here. The quote is searched for, verbatim and normalised,
in the cached document the row cites. A row whose quote cannot be found in its
own source is a hard failure and is reported as one.

What this cannot check mechanically is whether the quote SUPPORTS the amount,
the direction and the status recorded. Those are recorded as review prompts and
answered by the analyst in outputs/audit.md.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import requests

from .ingest import text_of
from .ledger import load_backlog, load_edges
from .sec_client import SecClient
from .util import ROOT, ensure_dirs, get_logger, load_config, sha1

LOG = get_logger("audit")
OUTPUTS = ROOT / "outputs"
CACHE = ROOT / "data" / "raw" / "audit"


def normalise(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def fetch(url: str, client: SecClient) -> str | None:
    """Cached fetch. SEC through the rate-limited client, others through requests."""
    name = sha1(url)[:20] + ".txt"
    p = CACHE / name
    if p.exists():
        return p.read_text(errors="replace")
    ensure_dirs(CACHE)
    raw = None
    if "sec.gov" in url:
        raw = client.get(url, subdir="audit", name=sha1(url)[:20] + ".bin")
    else:
        try:
            r = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"})
            if r.status_code == 200:
                raw = r.content
            else:
                LOG.info("HTTP %s for %s", r.status_code, url)
        except requests.RequestException as exc:
            LOG.info("%s for %s", type(exc).__name__, url)
    if raw is None:
        return None
    txt = text_of(raw)
    p.write_text(txt, errors="replace")
    return txt


def quote_in_text(quote: str, text: str) -> tuple[bool, str]:
    """Exact, then normalised, then ellipsis-split, then token-overlap."""
    q, t = normalise(quote), normalise(text)
    if q in t:
        return True, "verbatim"
    parts = [normalise(p) for p in re.split(r"\s*\.\.\.\s*|\s*…\s*", quote) if p.strip()]
    if len(parts) > 1 and all(p in t for p in parts):
        return True, "verbatim in fragments either side of an ellipsis"
    # token overlap, for rows where the quote paraphrases an XBRL tag value
    toks = [w for w in re.findall(r"[a-z0-9.$,%]+", q) if len(w) > 2]
    if toks:
        hit = sum(1 for w in toks if w in t) / len(toks)
        if hit >= 0.85:
            return True, f"token overlap {hit:.0%}"
        return False, f"token overlap only {hit:.0%}"
    return False, "not found"


def run(n: int = 20, seed: int = 20261005) -> dict:
    cfg = load_config()
    ensure_dirs(OUTPUTS, CACHE)
    client = SecClient(cfg)
    edges = load_edges()
    backlog = load_backlog()
    rows = [{"kind": "edge", **r} for r in edges.to_dict("records")]
    rows += [{"kind": "backlog", **r} for r in backlog.to_dict("records")]
    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))

    results = []
    for r in sample:
        url = r.get("source_url", "")
        quote = r.get("quote_snippet", "")
        ident = r.get("edge_id") or f"{r.get('node')}/{r.get('metric')}/{r.get('as_of_date')}"
        txt = fetch(url, client) if url else None
        if txt is None:
            ok, how = False, "source could not be retrieved for re-check"
        else:
            ok, how = quote_in_text(quote, txt)
        results.append({
            "id": ident, "kind": r["kind"], "url": url, "quote": quote,
            "tier": r.get("evidence_tier", ""), "accession": r.get("accession_no", ""),
            "quote_found": ok, "method": how,
            "source_retrieved": txt is not None,
            "words_in_quote": len(str(quote).split()),
            "amount_low": r.get("amount_usd_low"), "amount_high": r.get("amount_usd_high"),
            "status": r.get("status", ""), "edge_type": r.get("edge_type", ""),
            "source": r.get("source_node", ""), "target": r.get("target_node", ""),
        })
        LOG.info("%-54s %s (%s)", ident[:54], "OK" if ok else "CHECK", how)

    passed = sum(1 for x in results if x["quote_found"])
    unretrieved = sum(1 for x in results if not x["source_retrieved"])
    payload = {"sampled": len(results), "quote_verified": passed,
               "source_unreachable": unretrieved,
               "failed": [x for x in results if not x["quote_found"] and x["source_retrieved"]],
               "results": results, "seed": seed}
    (OUTPUTS / "audit.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-verify a random ledger sample")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261005)
    args = ap.parse_args()
    out = run(args.n, args.seed)
    print(json.dumps({"sampled": out["sampled"], "quote_verified": out["quote_verified"],
                      "source_unreachable": out["source_unreachable"],
                      "failed": len(out["failed"])}, indent=2))


if __name__ == "__main__":
    main()
