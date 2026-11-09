"""Rule and regex candidate-edge extractor.

Reads cached filing text, finds dollar amounts sitting near counterparty names
and financing verbs, and writes CANDIDATES ONLY to ledger/candidates.csv.

Nothing here ever writes to ledger/edges.csv. Promotion is a separate, manual
step via `python -m src.review`, which requires a quote. Enforced by
tests/test_no_autopromote.py.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from .entities import alias_map
from .ingest import text_of
from .util import ROOT, ensure_dirs, get_logger, load_config, sha1, slug

LOG = get_logger("extract")

INTERIM = ROOT / "data" / "interim"
LEDGER = ROOT / "ledger"

MONEY = re.compile(
    r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(trillion|billion|million|thousand|bn|mm|m\b|b\b)?",
    re.I)

SCALE = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "b": 1e9,
         "million": 1e6, "mm": 1e6, "m": 1e6, "thousand": 1e3, None: 1.0, "": 1.0}

# verb cue -> candidate edge_type. Order matters: first hit wins.
VERB_RULES: list[tuple[str, re.Pattern]] = [
    ("warrants", re.compile(r"\bwarrant(s|ts)?\b|\bwarrant to purchase\b", re.I)),
    ("loan_or_guarantee", re.compile(
        r"\bguarantee(d|s|ing)?\b|\bresidual value guarantee\b|\bletter of credit\b"
        r"|\bcredit support\b|\bsurety\b", re.I)),
    ("convertible_or_debt", re.compile(
        r"\bconvertible\b|\bnotes? (due|offering|issued)\b|\bterm loan\b|\bdelayed draw\b"
        r"|\bcredit facility\b|\brevolving\b|\bdebt financing\b|\bsenior notes\b", re.I)),
    ("vendor_financing", re.compile(
        r"\bvendor financing\b|\bsupplier financing\b|\bprepayment(s)? to\b"
        r"|\bdeposit(s)? with (our )?suppl", re.I)),
    ("equity_investment", re.compile(
        r"\binvest(ed|ment|ing|s)?\b|\bpreferred (stock|shares|units)\b"
        r"|\bequity (stake|interest|round)\b|\bsubscription agreement\b"
        r"|\bpurchase(d)? .{0,30}shares\b", re.I)),
    ("cloud_capacity_contract", re.compile(
        r"\bcloud (services|capacity|computing) (agreement|arrangement|commitment)\b"
        r"|\bcapacity (agreement|commitment|contract)\b|\bcompute (capacity|agreement)\b"
        r"|\bAI infrastructure agreement\b|\bgigawatt", re.I)),
    ("offtake_or_rpo", re.compile(
        r"\bremaining performance obligation", re.I)),
    ("lease", re.compile(
        r"\bleases? (that have )?not yet commenced\b|\boperating lease(s)? (signed|entered)\b"
        r"|\bbuild-to-suit\b", re.I)),
    ("purchase_commitment", re.compile(
        r"\bpurchase (commitment|obligation|order|agreement)s?\b|\bcommit(ted|ment|s)?\b"
        r"|\bunconditional purchase\b|\bsupply agreement\b|\bnon-?cancell?able\b", re.I)),
]

STATUS_RULES: list[tuple[str, re.Pattern]] = [
    ("LOI_nonbinding", re.compile(
        r"\bletter of intent\b|\bnon-?binding\b|\bmemorandum of understanding\b|\bLOI\b")),
    ("conditional", re.compile(
        r"\bsubject to\b|\bcontingent (up)?on\b|\bmilestone(s)?\b|\btranche(s)?\b"
        r"|\bupon (the )?(closing|satisfaction|achievement|deployment)\b"
        r"|\bconditions? precedent\b", re.I)),
    ("definitive", re.compile(
        r"\bdefinitive agreement\b|\bentered into\b|\bexecuted\b|\bconsummated\b"
        r"|\bclosed\b", re.I)),
]

# Narrative concentration language that XBRL usually misses.
CONCENTRATION = re.compile(
    r"((?:one|two|three|four|a single|our largest|the largest)\s+(?:direct\s+)?"
    r"customers?[^.]{0,220}?\b\d{1,3}(?:\.\d)?\s?%[^.]{0,120}\.)"
    r"|(\b\d{1,3}(?:\.\d)?\s?%\s+of\s+(?:total\s+)?(?:revenue|net revenue|revenues)"
    r"[^.]{0,200}\.)"
    r"|((?:customer|Customer)\s+[A-Z]\b[^.]{0,200}\b\d{1,3}(?:\.\d)?\s?%[^.]{0,80}\.)",
    re.I)

BACKLOG_TEXT = re.compile(
    r"([^.]{0,180}\b(?:remaining performance obligations?|contracted backlog|"
    r"total backlog|revenue backlog|non-?cancell?able contract backlog)\b[^.]{0,260}\.)",
    re.I)

CAND_FIELDS = [
    "candidate_id", "as_of_date", "source_node", "target_node", "edge_type",
    "amount_usd_low", "amount_usd_high", "amount_basis", "term_start", "term_end",
    "status", "conditions_text", "evidence_tier", "source_url", "accession_no",
    "quote_snippet", "notes", "extracted_amount_text", "context_window",
    "rule_hit", "review_status", "review_reason", "filer_node", "form", "doc_sha",
]

WINDOW = 420


def parse_money(text: str) -> float | None:
    m = MONEY.search(text)
    if not m:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    scale = SCALE.get((m.group(2) or "").lower().strip(), 1.0)
    return num * scale


def classify_type(window: str) -> tuple[str, str]:
    for etype, rx in VERB_RULES:
        m = rx.search(window)
        if m:
            return etype, m.group(0)[:48]
    return "", ""


def classify_status(window: str) -> str:
    for status, rx in STATUS_RULES:
        if rx.search(window):
            return status
    return "announced"


def find_aliases(text: str, amap: dict[str, str], self_node: str) -> list[tuple[int, int, str]]:
    """Return (start, end, canonical) hits for counterparties other than the filer."""
    hits: list[tuple[int, int, str]] = []
    for alias in sorted(amap, key=len, reverse=True):
        canon = amap[alias]
        if canon == self_node:
            continue
        if len(alias) <= 3:
            rx = re.compile(r"\b" + re.escape(alias) + r"\b")
        else:
            rx = re.compile(re.escape(alias), re.I)
        for m in rx.finditer(text):
            hits.append((m.start(), m.end(), canon))
    hits.sort()
    # drop overlaps, keep the longest / first
    kept: list[tuple[int, int, str]] = []
    last_end = -1
    for s, e, c in hits:
        if s < last_end:
            continue
        kept.append((s, e, c))
        last_end = e
    return kept


def extract_from_doc(row: dict, amap: dict[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    path = ROOT / row["local_path"] if row.get("local_path") else None
    if not path or not path.exists():
        return [], [], []
    raw = path.read_bytes()
    text = text_of(raw)
    return extract_from_text(text, row, amap)


def extract_from_text(text: str, row: dict, amap: dict[str, str]):
    """Run the unchanged candidate rules on already cached plain text."""
    doc_sha = sha1(text)[:12]
    filer = row["node"]
    cands: list[dict] = []
    seen: set[str] = set()

    for s, e, canon in find_aliases(text, amap, filer):
        lo, hi = max(0, s - WINDOW), min(len(text), e + WINDOW)
        window = text[lo:hi]
        amount = parse_money(window)
        if amount is None or amount < 50_000_000:
            continue  # below $50M is noise at ecosystem scale
        etype, rule_hit = classify_type(window)
        if not etype:
            continue
        status = classify_status(window)
        mm = MONEY.search(window)
        amt_text = mm.group(0) if mm else ""
        # Direction: funding edges flow filer -> counterparty if the filer is the
        # one investing; demand edges flow buyer -> seller. The extractor cannot
        # settle direction reliably, so it proposes BOTH orientations' best guess
        # and the reviewer fixes it. Default guess below is documented in notes.
        funding_family = etype in {"equity_investment", "convertible_or_debt",
                                   "loan_or_guarantee", "warrants", "vendor_financing"}
        src, tgt = (filer, canon) if funding_family else (canon, filer)
        key = f"{src}|{tgt}|{etype}|{int(amount)}|{row['accession_no']}"
        if key in seen:
            continue
        seen.add(key)
        cands.append({
            "candidate_id": f"c_{sha1(key)[:14]}",
            "as_of_date": row["filing_date"],
            "source_node": src, "target_node": tgt, "edge_type": etype,
            "amount_usd_low": amount, "amount_usd_high": amount,
            "amount_basis": "notional", "term_start": "", "term_end": "",
            "status": status, "conditions_text": "",
            "evidence_tier": "T1", "source_url": row["doc_url"],
            "accession_no": row["accession_no"], "quote_snippet": "",
            "notes": "direction guessed by family rule; verify before promoting",
            "extracted_amount_text": amt_text,
            "context_window": re.sub(r"\s+", " ", window)[:900],
            "rule_hit": rule_hit, "review_status": "pending", "review_reason": "",
            "filer_node": filer, "form": row["form"], "doc_sha": doc_sha,
        })

    conc: list[dict] = []
    for m in CONCENTRATION.finditer(text):
        sent = re.sub(r"\s+", " ", next(g for g in m.groups() if g)).strip()
        if len(sent) < 40:
            continue
        conc.append({"node": filer, "form": row["form"],
                     "filing_date": row["filing_date"],
                     "accession_no": row["accession_no"], "url": row["doc_url"],
                     "sentence": sent[:600]})
    back: list[dict] = []
    for m in BACKLOG_TEXT.finditer(text):
        sent = re.sub(r"\s+", " ", m.group(1)).strip()
        back.append({"node": filer, "form": row["form"],
                     "filing_date": row["filing_date"],
                     "accession_no": row["accession_no"], "url": row["doc_url"],
                     "sentence": sent[:700]})
    return cands, conc, back


def run(max_docs: int | None = None) -> dict:
    cfg = load_config()
    ensure_dirs(LEDGER, INTERIM)
    idx_path = INTERIM / "filings_index.csv"
    if not idx_path.exists():
        raise SystemExit("run `make ingest` first: no data/interim/filings_index.csv")
    with open(idx_path) as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("local_path")]
    if max_docs:
        rows = rows[:max_docs]
    amap = alias_map()

    all_c: list[dict] = []
    all_conc: list[dict] = []
    all_back: list[dict] = []
    for i, row in enumerate(rows, 1):
        try:
            c, k, b = extract_from_doc(row, amap)
        except Exception as exc:  # a malformed doc must not kill the run
            LOG.warning("extract failed on %s %s: %s", row["node"], row["accession_no"], exc)
            continue
        all_c.extend(c)
        all_conc.extend(k)
        all_back.extend(b)
        if i % 100 == 0:
            LOG.info("%d/%d docs, %d candidates so far", i, len(rows), len(all_c))

    # Preserve prior review decisions across re-runs.
    cpath = LEDGER / "candidates.csv"
    prior: dict[str, dict] = {}
    if cpath.exists():
        with open(cpath) as fh:
            for r in csv.DictReader(fh):
                prior[r["candidate_id"]] = r
    merged: dict[str, dict] = {}
    for c in all_c:
        p = prior.get(c["candidate_id"])
        if p and p.get("review_status") in ("promoted", "rejected"):
            c["review_status"] = p["review_status"]
            c["review_reason"] = p.get("review_reason", "")
            c["quote_snippet"] = p.get("quote_snippet", "")
        merged[c["candidate_id"]] = c
    for cid, p in prior.items():
        if cid not in merged and p.get("review_status") in ("promoted", "rejected"):
            merged[cid] = {k: p.get(k, "") for k in CAND_FIELDS}

    out = sorted(merged.values(), key=lambda r: (-float(r["amount_usd_high"] or 0),
                                                 str(r["source_node"])))
    with open(cpath, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAND_FIELDS)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in CAND_FIELDS})
    LOG.info("wrote %d candidates -> %s", len(out), cpath)

    def dump(path: Path, rows_: list[dict]) -> None:
        if not rows_:
            path.write_text("")
            return
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_[0].keys()))
            w.writeheader()
            w.writerows(rows_)

    # Dedupe narrative hits by (node, sentence)
    seen_c, uc = set(), []
    for r in all_conc:
        k = (r["node"], r["sentence"][:200])
        if k not in seen_c:
            seen_c.add(k); uc.append(r)
    seen_b, ub = set(), []
    for r in all_back:
        k = (r["node"], r["sentence"][:200])
        if k not in seen_b:
            seen_b.add(k); ub.append(r)
    dump(INTERIM / "concentration_sentences.csv", uc)
    dump(INTERIM / "backlog_sentences.csv", ub)
    LOG.info("wrote %d concentration sentences, %d backlog sentences", len(uc), len(ub))
    return {"candidates": len(out), "docs": len(rows),
            "concentration": len(uc), "backlog": len(ub)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract candidate edges from cached filings")
    ap.add_argument("--max-docs", type=int, default=None)
    args = ap.parse_args()
    print(run(max_docs=args.max_docs))


if __name__ == "__main__":
    main()
