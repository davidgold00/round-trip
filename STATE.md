# STATE.md

Resume file. A new session should read this first, then `DECISIONS.md`.

**Last updated:** 2026-10-07, end of Phase 6. All phases complete.

## Status: complete and running

`make refresh && make serve` produces a working dashboard from a verified
ledger. 62 tests pass.

## Headline as of the last run

* Ecosystem round-trip exposure **1.72% central, range 1.39% to 18.22%**.
  $46.7 billion of $2.72 trillion of disclosed backlog.
* **79.3%** of that backlog universe names no customer in any filing. Broadcom
  and Oracle name none at all.
* 38 ledger edges: 28 T1 (SEC filings), 10 T2 (company releases), 0 T3, 0 T4.
  By status: 19 definitive, 13 conditional, 5 announced, 1 non-binding letter of
  intent. 5 edges are recorded at zero dollars because no party disclosed one.
* Nine circular loops, every one a genuine round trip. One strongly connected
  component: AMD, Amazon, Anthropic, Microsoft, OpenAI.
* Stress: Monte Carlo median 5.65% of backlog at risk, 10th to 90th percentile
  3.35% to 8.47%. Pass-through dominates the tornado at 5.9 percentage points
  against a base of 5.7%, so the stress answer is assumption-dominated and the
  dashboard says so.
* Eisenberg-Noe no-shock baseline 11.36%: unshocked, committed purchases in this
  network already exceed documented external funding.

## What is done

| phase | state |
|---|---|
| 0, setup and pre-registration | done. `DECISIONS.md` Part A written before any computation |
| 1, ingestion and extraction | done. 617 filing documents and 9,214 XBRL observations cached, 266 candidates extracted, 38 edges promoted through review |
| 2, exposure metrics | done. D, provenance readings, damped multi-hop, structure analysis, all with toy-graph tests |
| 3, cascade stress | done. Fixed-point cascade, 20k Monte Carlo, Eisenberg-Noe and DebtRank cross-checks, tornado |
| 4, news monitor | done. EDGAR 8-K items, IR RSS, GDELT. Review queue. `make refresh` with changelog. GitHub Actions workflow, disabled by default |
| 5, dashboard | done. Eight panels, light and dark, mobile-friendly, D3 vendored locally, client-side stress lab at parity with Python |
| 6, quality and docs | done. 62 tests, self-audit with corrections applied, README, METHODOLOGY, interview notes |

## Known issues and open items

* **`sentence-transformers` is not installed**, so news tagging runs the TF-IDF
  plus keyword path. The embedding path is implemented and is selected
  automatically if the package and model become available. Nothing is blocked.
* **Broadcom's investor-relations pages return HTTP 403 to scripted requests.**
  One ledger row cites one, and `make audit` reports it as "source could not be
  retrieved for re-check" rather than as a pass. The row is recorded at zero
  dollars so it affects no dollar-weighted figure.
* **Two suppliers have dependency row sums above 1** (Nebius 1.31, Nscale 1.20 on
  the central bound). Both are real: their disclosed RPO predates agreements that
  are already in the ledger. Flagged as warnings, deliberately not rescaled.
* **Alphabet is almost certainly understated.** It names Anthropic in no filing
  retrieved and no release found gives an Alphabet investment amount, so no edge
  was recorded and its measured exposure is zero. Its non-marketable securities
  rose from $68.7bn to $131.5bn in the first half of 2026 with no attribution.
* **`SEC_USER_AGENT` lives in `.env`, which is gitignored.** A fresh clone must
  recreate it from `.env.example` before `make ingest`.
* **GDELT rate-limits repeat runs from one address** and can return zero items.
  The pipeline logs it and continues; EDGAR and the IR feeds carry the monitor.
* **Only one pipeline snapshot exists so far.** The trend panel is therefore
  driven by reconstructed vintages, which recompute the headline from evidence
  dated on or before each quarter end and are labelled as reconstructions.
  Real run-to-run snapshots accumulate from each `make refresh`.

## Where to pick up next

In order of value:

1. **Widen the supplier universe.** Add the other neoclouds that now file
   (Applied Digital, IREN, Cipher Mining, TeraWulf, Crusoe if it registers).
   They are already in the alias table. Nscale showed that newly registering
   companies disclose counterparties with amounts that incumbents do not.
2. **Mine 10-K Item 1A risk factors specifically.** The current extractor scans
   whole documents. Customer-concentration language concentrates in risk factors
   and in the revenue note, and a section-aware pass would raise candidate
   precision a lot.
3. **Add an exhibit crawler.** 8-K Item 1.01 exhibits contain the actual
   agreements. The current pipeline reads only the primary document, so dollar
   terms that appear only in exhibit 10.1 are being missed.
4. Parse `data/interim/concentration_sentences.csv` (157 rows) into bounded
   `aggregate_only` dependency entries. The plumbing for bounded aggregates
   exists in the metric definition but no rows use it yet.
5. Let the stress lab edit the shock per node rather than scaling a preset
   uniformly.

## Files that matter

* `DECISIONS.md` Part A is the pre-registered metric definition. Part B is every
  judgement call since, dated, with a one-line rationale.
* `ledger/promotions*.yaml` are the reviewed promotion batches. They are the
  record of what was read and why it was accepted, and they regenerate
  `edges.csv` through `python -m src.review batch`.
* `outputs/audit.md` is the self-audit, including the two corrections it forced.
* `outputs/changelog.md` is rewritten by every `make refresh`.

## A property worth knowing about the news corpus

`data/interim/news_items.csv` accumulates. Most newsrooms expose only their ten
or twenty most recent items, so an item that falls out of a feed is carried over
from the previous run rather than lost. Deleting that file shrinks the corpus to
whatever the feeds expose today. Review decisions live in
`ledger/news_candidates.csv`, are keyed by URL, and survive a rebuild; a promoted
edge lives in `ledger/edges.csv` permanently and is unaffected either way.

`python -m src.news --skip-network` re-tags the stored corpus without touching a
single feed, which is how the relevance rules were tuned.
