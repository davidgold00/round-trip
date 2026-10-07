"""`make refresh`: pull, extract, tag, rebuild, snapshot, and diff.

Order matters. Ingestion and news come first so the extractor and the metrics
see the newest data; snapshots and the changelog come last so they describe what
actually shipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import pandas as pd

from .ledger import SNAPSHOTS, load_edges, snapshot, tcv, weighted_amount
from .util import ROOT, ensure_dirs, fmt_usd, get_logger, load_config, today

LOG = get_logger("refresh")
OUTPUTS = ROOT / "outputs"
SITE_DATA = ROOT / "site" / "data"


def latest_snapshot(before: str | None = None) -> Path | None:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    snaps = sorted(SNAPSHOTS.glob("edges_*.csv"))
    if before:
        snaps = [s for s in snaps if s.stem.split("_")[1] < before.replace("-", "")]
    return snaps[-1] if snaps else None


def diff_edges(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    o = old.set_index("edge_id") if len(old) else old
    n = new.set_index("edge_id") if len(new) else new
    old_ids = set(o.index) if len(o) else set()
    new_ids = set(n.index) if len(n) else set()
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    changed = []
    for eid in sorted(old_ids & new_ids):
        for col in ("amount_usd_low", "amount_usd_high", "status", "evidence_tier",
                    "amount_basis", "conditions_text"):
            a, b = o.loc[eid, col], n.loc[eid, col]
            if str(a) != str(b):
                changed.append({"edge_id": eid, "field": col,
                                "from": str(a), "to": str(b)})
    return {
        "added": [{"edge_id": e, "source": n.loc[e, "source_node"],
                   "target": n.loc[e, "target_node"],
                   "edge_type": n.loc[e, "edge_type"],
                   "amount_usd_low": float(n.loc[e, "amount_usd_low"]),
                   "amount_usd_high": float(n.loc[e, "amount_usd_high"]),
                   "status": n.loc[e, "status"], "tier": n.loc[e, "evidence_tier"],
                   "as_of": n.loc[e, "as_of_date"]} for e in added],
        "removed": removed, "changed": changed,
    }


def metric_deltas(old: dict | None, new: dict) -> dict:
    if not old:
        return {"note": "no prior metrics snapshot to compare against"}
    out = {"ecosystem": {}, "suppliers": {}}
    for b in ("LOWER", "CENTRAL", "UPPER"):
        a = old.get("ecosystem", {}).get(b, {}).get("rte")
        c = new.get("ecosystem", {}).get(b, {}).get("rte")
        if a is not None and c is not None:
            out["ecosystem"][b] = {"from": a, "to": c, "delta_pp": 100 * (c - a)}
    om = {s["supplier"]: s for s in old.get("suppliers", [])}
    for s in new.get("suppliers", []):
        a = om.get(s["supplier"])
        if a:
            out["suppliers"][s["supplier"]] = {
                "rte_central_from": a["rte_central"], "rte_central_to": s["rte_central"],
                "delta_pp": 100 * (s["rte_central"] - a["rte_central"])}
        else:
            out["suppliers"][s["supplier"]] = {"new": True,
                                              "rte_central_to": s["rte_central"]}
    return out


def _queue_breakdown(news: dict) -> str:
    from collections import Counter
    c = Counter(q.get("status", "pending") for q in news.get("review_queue", []))
    return ", ".join(f"{n} {k}" for k, n in sorted(c.items())) or "empty"


def write_changelog(diff: dict, deltas: dict, news: dict | None, stamp: str) -> Path:
    lines = [f"# What changed since the last refresh", "",
             f"Refresh run {stamp}.", ""]
    lines += ["## New ledger edges", ""]
    if diff["added"]:
        for a in diff["added"]:
            lo, hi = a.get("amount_usd_low", 0.0), a["amount_usd_high"]
            if not hi:
                amt = "no disclosed amount"
            elif lo == hi:
                amt = fmt_usd(hi)
            else:
                amt = f"{fmt_usd(lo)} to {fmt_usd(hi)}"
            lines.append(f"* `{a['as_of']}` {a['source']} to {a['target']} "
                         f"[{a['edge_type']}] {amt}, {a['status']}, {a['tier']}")
    else:
        lines.append("* none")
    lines += ["", "## Changed amounts or statuses", ""]
    if diff["changed"]:
        for c in diff["changed"]:
            lines.append(f"* `{c['edge_id']}` {c['field']}: {c['from']} to {c['to']}")
    else:
        lines.append("* none")
    if diff["removed"]:
        lines += ["", "## Removed edges", ""] + [f"* `{r}`" for r in diff["removed"]]
    lines += ["", "## Metric deltas", ""]
    eco = deltas.get("ecosystem") or {}
    if eco:
        lines.append("| bound | previous | now | change |")
        lines.append("|---|---|---|---|")
        for b, v in eco.items():
            lines.append(f"| {b} | {100*v['from']:.2f}% | {100*v['to']:.2f}% | "
                         f"{v['delta_pp']:+.2f} pp |")
        moved = [(k, v) for k, v in (deltas.get("suppliers") or {}).items()
                 if abs(v.get("delta_pp", 0)) > 0.01 or v.get("new")]
        if moved:
            lines += ["", "Suppliers that moved:", ""]
            for k, v in sorted(moved, key=lambda kv: -abs(kv[1].get("delta_pp", 0))):
                if v.get("new"):
                    lines.append(f"* {k}: new, central {100*v['rte_central_to']:.2f}%")
                else:
                    lines.append(f"* {k}: {100*v['rte_central_from']:.2f}% to "
                                 f"{100*v['rte_central_to']:.2f}% ({v['delta_pp']:+.2f} pp)")
    else:
        lines.append(deltas.get("note", "no comparison available"))
    if news:
        c = news.get("counts", {})
        lines += ["", "## News monitor", "",
                  f"* {c.get('total', 0)} items held, {c.get('flagged', 0)} flagged as "
                  f"financing-relevant",
                  f"* by source: {c.get('by_source', {})}",
                  f"* tagger: {news.get('tagger_mode', 'unknown')}",
                  f"* review queue: {len(news.get('review_queue', []))} entries "
                  f"({_queue_breakdown(news)}). A flagged item counts toward "
                  f"nothing until a reviewer promotes it with a verbatim quote."]
    lines.append("")
    p = OUTPUTS / "changelog.md"
    p.write_text("\n".join(lines))
    (SITE_DATA / "changelog.json").write_text(json.dumps(
        {"generated": stamp, "diff": diff, "metric_deltas": deltas,
         "markdown": "\n".join(lines)}, default=str))
    LOG.info("wrote %s", p)
    return p


def build_vintages() -> list[dict]:
    """Reconstruct the metric as it would have read at past dates.

    This is a RECONSTRUCTION, not a record of past pipeline runs: for each
    quarter-end it recomputes the headline using only the edges and backlog rows
    whose evidence is dated on or before that date. It answers "what would this
    dashboard have shown in March 2026 from documents that existed then?" It does
    not claim the dashboard existed then, and the site labels it as reconstructed.

    Real run-to-run snapshots accumulate separately in ledger/snapshots and are
    shown alongside once there is more than one.
    """
    from .ledger import load_backlog
    from .metrics import compute
    cfg = load_config()
    edges = load_edges()
    backlog = load_backlog()
    if edges.empty:
        return []
    dates = sorted({str(d)[:10] for d in edges.as_of_date if str(d)[:4].isdigit()})
    if not dates:
        return []
    start = dt.date.fromisoformat(dates[0])
    end = dt.date.fromisoformat(max(dates[-1], today()))
    cuts: list[str] = []
    y, q = start.year, (start.month - 1) // 3
    while True:
        m = q * 3 + 3
        last = dt.date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1) - dt.timedelta(days=1)
        if last > end:
            break
        if last >= start:
            cuts.append(last.isoformat())
        q += 1
        if q == 4:
            q, y = 0, y + 1
    if not cuts or cuts[-1] != end.isoformat():
        cuts.append(end.isoformat())

    out = []
    for cut in cuts:
        e = edges[edges.as_of_date <= cut]
        b = backlog[backlog.as_of_date <= cut]
        if e.empty:
            continue
        try:
            res = compute(e, b, cfg)
        except Exception as exc:
            LOG.warning("vintage %s failed: %s", cut, exc)
            continue
        eco = res.ecosystem
        if float(eco.get("CENTRAL", {}).get("backlog_total") or 0) <= 0:
            # No disclosed backlog had been filed yet, so there is no denominator
            # and the point would plot a share of nothing.
            continue
        out.append({
            "snapshot": cut, "kind": "reconstructed",
            "lower": eco.get("LOWER", {}).get("rte"),
            "central": eco.get("CENTRAL", {}).get("rte"),
            "upper": eco.get("UPPER", {}).get("rte"),
            "backlog_total": eco.get("CENTRAL", {}).get("backlog_total"),
            "edges": int(len(e)),
        })
    LOG.info("reconstructed %d vintages from ledger evidence dates", len(out))
    return out


def build_history() -> Path:
    """Vintage series for the dashboard trend panel, from the snapshot files."""
    rows = []
    for mp in sorted(SNAPSHOTS.glob("metrics_*.json")):
        try:
            m = json.loads(mp.read_text())
        except json.JSONDecodeError:
            continue
        stamp = mp.stem.split("_")[1]
        iso = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
        eco = m.get("ecosystem", {})
        rows.append({
            "snapshot": iso,
            "lower": eco.get("LOWER", {}).get("rte"),
            "central": eco.get("CENTRAL", {}).get("rte"),
            "upper": eco.get("UPPER", {}).get("rte"),
            "backlog_total": eco.get("CENTRAL", {}).get("backlog_total"),
            "edges": sum((m.get("edge_counts_by_tier") or {}).values()),
            "unattributable": (m.get("coverage") or {}).get("unattributable_weighted"),
        })
    for r in rows:
        r["kind"] = "pipeline_run"
    vint = build_vintages()
    p = SITE_DATA / "history.json"
    p.write_text(json.dumps({
        "snapshots": rows,
        "vintages": vint,
        "note": ("Vintages are RECONSTRUCTED: each point recomputes the headline "
                 "using only evidence dated on or before that date. They are not a "
                 "record of past pipeline runs. Actual run-to-run snapshots are "
                 "listed separately and accumulate from the first refresh onwards."),
    }, default=str))
    LOG.info("wrote %s with %d pipeline snapshots and %d reconstructed vintages",
             p, len(rows), len(vint))
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Full refresh")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--skip-news", action="store_true")
    ap.add_argument("--skip-extract", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    ensure_dirs(OUTPUTS, SITE_DATA, SNAPSHOTS)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    day = today()

    prev_snap = latest_snapshot(before=day)
    prev_edges = pd.read_csv(prev_snap, dtype=str, keep_default_na=False) if prev_snap else load_edges().head(0)
    if prev_snap:
        LOG.info("comparing against %s", prev_snap.name)
    prev_metrics_path = None
    snaps = sorted(SNAPSHOTS.glob("metrics_*.json"))
    snaps = [s for s in snaps if s.stem.split("_")[1] < day.replace("-", "")]
    if snaps:
        prev_metrics_path = snaps[-1]
    prev_metrics = json.loads(prev_metrics_path.read_text()) if prev_metrics_path else None

    if not args.skip_ingest:
        from . import ingest
        LOG.info("step 1/6 ingest")
        ingest.ingest()
    if not args.skip_extract:
        from . import extract
        LOG.info("step 2/6 extract candidates")
        extract.run()
    news_payload = None
    if not args.skip_news:
        from . import news
        LOG.info("step 3/6 news monitor")
        news.run()
        p = OUTPUTS / "news.json"
        if p.exists():
            news_payload = json.loads(p.read_text())

    LOG.info("step 4/6 metrics")
    from . import metrics as metrics_mod
    metrics_mod.main()
    LOG.info("step 5/6 stress")
    from . import stress as stress_mod
    stress_mod.main()
    LOG.info("step 6/6 site data")
    from . import site_data as site_mod
    site_mod.build()

    new_edges = load_edges()
    snapshot(new_edges, day)
    mj = OUTPUTS / "metrics.json"
    if mj.exists():
        shutil.copy(mj, SNAPSHOTS / f"metrics_{day.replace('-', '')}.json")
    sj = OUTPUTS / "stress.json"
    if sj.exists():
        shutil.copy(sj, SNAPSHOTS / f"stress_{day.replace('-', '')}.json")

    new_metrics = json.loads(mj.read_text()) if mj.exists() else {}
    diff = diff_edges(prev_edges, new_edges)
    deltas = metric_deltas(prev_metrics, new_metrics)
    write_changelog(diff, deltas, news_payload, stamp)
    build_history()

    eco = new_metrics.get("ecosystem", {})
    LOG.info("refresh complete. ecosystem RTE %.2f%% (%.2f%% to %.2f%%), %d edges, "
             "%d new, %d changed",
             100 * eco.get("CENTRAL", {}).get("rte", 0),
             100 * eco.get("LOWER", {}).get("rte", 0),
             100 * eco.get("UPPER", {}).get("rte", 0),
             len(new_edges), len(diff["added"]), len(diff["changed"]))


if __name__ == "__main__":
    main()
