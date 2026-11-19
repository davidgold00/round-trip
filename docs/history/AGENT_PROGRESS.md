# Morning summary

2026-11-09, America/Detroit. Work stayed on `feature/deal-extraction-agent`.
Eleven items are done, item 5 is partial, and item 13 is skipped under its gate.
The reviewed ledger's original financial fields, existing promotions, metric
formulas and stress logic are unchanged. The original `make refresh` path is
regression-tested against pinned main `ceedd24` with identical cached acquisition
inputs and all analysis/stress/export steps running.

| Item | Status | Result |
|---|---|---|
| 1. Rules baseline | done | Same gold reader, verifier and scorer; real results committed |
| 2. Record/replay | done | Exact request matching, live recordings, synthetic retry/queue tests |
| 3. Local benchmark | done | `make agent-bench`; preflight and two-model comparison |
| 4. Uncertain labels | done | Three original cases resolved; four original cases remain uncertain |
| 5. Harder cases | partial | Eight additions, three hard negatives, two post-June deals; three full-length passages still missing |
| 6. Ledger agreement | done | Eight confirmed links, zero direction/type conflicts; strict option |
| 7. One promotion path | done | Reviewed YAML adapter, original batch application and audit |
| 8. Reuse ingestion | done | Stored news/cached filing input, explicit own-fetcher fallback |
| 9. Pending panel | done | Read-only News card, existing styling; visual browser QA remains manual |
| 10. README diet | done | Short overview; original sections preserved; detailed agent guide moved |
| 11. Interview notes | done | Illustrative gold walkthrough and five honest Q&As |
| 12. Prompt v2 | done | Opt-in, v1 unchanged/default, model/prompt cross-comparison |
| 13. CI regression job | skipped | P5 gate unmet because item 5 remains partial |

## Measured baseline

The saved corpus has 17 positive and 8 negative passages, with five uncertain
document labels. Sources overlap; these are not independent observations.

| Metric | Rules, all 25 passages | Rules, 20 certain passages | Local LLM |
|---|---:|---:|---:|
| Edge precision | 15.4% | 10.0% | Not measured |
| Edge recall | 11.8% | 8.3% | Not measured |
| Matched amount accuracy | 100% on 2 edges | 100% on 1 edge | Not measured |
| Final verification pass rate | 53.8% | 50.0% | Not measured |

Inclusive counts: 2 true positives, 11 false positives, 15 false negatives.
Certain-only counts: 1 true positive, 9 false positives, 11 false negatives.
The amount sample is too small to support a general accuracy claim. LLM model
accuracy and v2 performance are **Not measured**. Synthetic cassettes never
produce model metrics. Full reports are in `eval/RESULTS.md` and
`eval/RESULTS-certain.md`; scored inputs and counts are explicit.

## Every changed gold label

| Document | Change | Resolving evidence or remaining issue |
|---|---|---|
| `amazon_anthropic_2023` | equity_investment -> debt_or_loan; uncertain -> false | Amazon 10-Q `0001018724-23-000018` explicitly identifies a convertible note |
| `amazon_anthropic_2024` | equity_investment -> debt_or_loan; uncertain -> false | Amazon 10-K `0001018724-25-000004` identifies the third convertible note; saved exact clause plus sentence location |
| `nvidia_coreweave_2025` | uncertain -> false; type/amount unchanged | 8-K `0001769628-25-000047` establishes residual-capacity purchases; Sept 15 disclosure versus Sept 9 execution |
| `nscale_nvidia_warrants` (new case) | uncertain false -> true; direction/type unchanged | Short receipt quote cannot establish the ledger's financing direction; issuer/holder direction differs from financial support |

Amazon instrument supplements are included in the input itself, with separate
primary-source attribution. Amount caps/new commitments are unchanged. Exact
spans, URLs, accessions and adjudication notes are in `eval/gold/manifest.json`.
Remaining uncertain cases: `microsoft_openai_2023`, `nvidia_openai_2025`,
`oracle_openai_2024`, `oracle_openai_2025`, and `nscale_nvidia_warrants`.

## What to verify by hand

- Add three intact multi-paragraph primary-source passages. The eight verified
  additions are short spans; full-document coverage is still missing. Do not
  present stitched snippets as full filings or quote full-document accuracy.
- Check the four label edits/flags above and the five remaining uncertain cases.
  Three harder negatives describe parallel merger cases or separate fines;
  they do not assert financing between the tracked companies they co-mention.
- Run actual local models before claiming precision/recall, model superiority or
  a v2 improvement. Validate inclusive and certain-only results separately.
- View News in light/dark and at phone width. No browser binary was installed
  here, so automated visual QA could not run. No stylesheet or stress engine changed.
- Live SEC discovery still needs your contact-valued `SEC_USER_AGENT`. Reuse
  caches and run one SEC-fetching command at a time. Source snippets and feed
  dates require original-source review before choosing dates and legal status.

## Exact local VS Code commands

Activate the repository's Python 3.12 environment with dependencies installed.

```bash
ollama pull qwen2.5:7b-instruct
```

Start the Ollama app, or run `ollama serve` in a separate terminal, then:

```bash
make agent-bench
```

Optional two-model/two-prompt experiment, after pulling the second model:

```bash
ollama pull llama3.1:8b
make agent-bench AGENT_BENCH_ARGS="--models qwen2.5:7b-instruct llama3.1:8b --prompt-versions v1 v2"
make agent-bench AGENT_BENCH_ARGS="--exclude-uncertain --output eval/results/certain-comparison.md"
```

Use stored ingestion, then review candidates:

```bash
python -m deal_agent run --source news
python -m deal_agent review list
python -m deal_agent review --actor "David Gold"
```

Approval exports a reviewed YAML and prints its path; it does not write the ledger.
Inspect it and apply through the original mechanism, replacing the placeholder:

```bash
python -m src.review batch PATH_PRINTED_BY_REVIEW
python -m deal_agent publish
python -m deal_agent export-pending
```

`run --source fetch` explicitly selects the fallback fetcher. For a stale export,
use `review reopen ID --actor "David Gold" --reason "..."`, then review again;
old exports/audits are retained. Applied approvals cannot be reopened.
See `docs/AGENT_REVIEW.md` and `docs/DEAL_AGENT.md` for the full workflow.

## Verification

Full pytest and `python -m deal_agent eval --validate-only` passed after every
committed item. Final suite: 171 tests. Strict ledger validation has eight matches,
zero mismatches and zero ambiguous links. Rules were measured on both uncertainty
policies; LLM was not run. Synthetic replay covers verification failure/repair,
reconciliation, queue insertion and idempotency. Original refresh headline parity,
original financial fields/promotions and browser/Python stress parity pass.
V1 prompt bytes match the initial feature commit exactly. JavaScript syntax,
Python compilation, diff whitespace and introduced em-dash checks pass.

---

# Agent progress

## 1. Rules baseline: done

- Added a label-blind adapter over the original `src.extract` rules. Kept its
  $50M floor, first amount, guessed direction and verb order. Fixed taxonomy
  mapping is in `deal_agent/rules.py`; no gold-dependent rules were added.
- News tags are not directed financial edges, so they are not additional
  predictions. Both extractors use the same gold reader, verifier and scorer.
- Added `eval --extractor rules|llm` with llm default and side-by-side reporting.
- Verified full pytest suite and `eval --validate-only`; measured baseline in
  `eval/baselines/rules.json` and `eval/RESULTS.md`. LLM: Not measured.
- Main parity test runs `make refresh` on main and the feature working tree
  in temporary copies, with only network acquisition disabled. It compares all
  ecosystem headline values and checks original ledger fields/promotions.
- Manual: run local LLM benchmark before interpreting a comparison.
- Baseline counts: 1 true positive, 10 false positives, 11 false negatives.
  Edge precision 9.1%, recall 8.3%; amount accuracy 100% on just ONE match.
  This is a warning about sample size, not evidence of reliable amount parsing.

## 2. Record/replay provider: done

- Added strict sequential cassettes with exact prompt/schema/options/model hashes,
  every live response including raw Ollama metadata, and recorded exceptions.
  Replay has no network fallback and refuses changed prompts or settings.
- `eval` and `run` accept `--provider record|replay --cassette PATH`.
  Recording refuses existing files; real cassettes can be committed explicitly.
- A two-document cassette is explicitly synthetic test data. Its first extraction
  has an incorrect amount, then a verified repair. Synthetic eval metrics are
  always withheld. Tests cover queue insertion, retry history and idempotency.
- Verified full pytest suite and `eval --validate-only`, no model or network.
- Git's direct push has no credentials here. Published the tested commit through
  the selected GitHub integration and synchronized the local branch to it.
- Manual: collect and commit a real cassette with a live local benchmark.

## 3. One-command local benchmark: done

- `make agent-bench` preflights Ollama and every selected model, records LLM
  evaluations, runs rules and writes a combined report with matched corpus and
  uncertainty policy. `--models MODEL MODEL` compares two local models.
- Live cassettes are deliberately committable under `eval/cassettes/`.
  Missing service/model messages include exact setup commands. No remote fallback.
- Verified full pytest suite and `eval --validate-only`. Preflight, comparison
  compatibility and unmeasured reporting have offline tests. The actual command
  exits clearly while Ollama is absent, before overwriting the committed report.
- Manual: run `make agent-bench` locally. No LLM accuracy was measured here.

## 4. Resolve uncertain labels: done, four remain honestly uncertain

- Re-read all seven linked primary sources, plus Amazon SEC 10-Q
  `0001018724-23-000018` and 10-K `0001018724-25-000004`.
- `amazon_anthropic_2023`: equity_investment -> debt_or_loan; uncertain -> false.
  Amazon explicitly describes a convertible note. The $4B cap remains a cap.
- `amazon_anthropic_2024`: equity_investment -> debt_or_loan; uncertain -> false.
  The new $4B commitment consists of convertible notes; it is not cumulative $8B.
  Saved a short exact SEC clause and its sentence location. Supplemental SEC
  excerpts are included in the inputs, with separate attribution, so the labels
  are observable to the extractor rather than relying on hidden evidence.
- `nvidia_coreweave_2025`: uncertain -> false, type and amount unchanged.
  8-K `0001769628-25-000047`, Item 1.01 explicitly says NVIDIA purchases
  residual unsold capacity. Sept 15 is disclosure date; Sept 9 is execution date.
- Kept uncertain: `microsoft_openai_2023` (instrument unspecified),
  `nvidia_openai_2025` (LOI plus unspecified instrument),
  `oracle_openai_2024` (three-party payer), `oracle_openai_2025` (development
  versus purchase and payer). Sharpened each reason and recorded exact evidence.
- No ledger or promotions were changed. Reran rules against the revised corpus
  and committed updated measured reports. Full pytest and validate-only pass.
- Manual: check all three adjudications and the four remaining ambiguities.
  Legal status, range bounds and payment timing are not settled by extraction.

## 5. Harder cases: partial

- Added 8 source-backed documents: 5 positives checked against reviewed ledger
  quotes, 3 hard negatives with dollars and two tracked entities. Every saved
  text has URL, SHA-256, date and scope. Re-read AMD release and Nscale S-1.
- New positives: AMD/Anthropic equity and chip deployment; Nscale/Anthropic
  capacity; Nscale/Microsoft capacity; Nvidia/Nscale warrants. Three cases cover
  two distinct deals announced after June 2026. The warrants are a later
  disclosure of a 2025 instrument and explicitly NOT an out-of-time deal.
- Negatives: FTC parallel merger list, parallel merger challenges, and separate
  Amazon/Microsoft privacy penalties. Non-adjacent spans are explicitly marked.
- Outstanding: 3 intact multi-paragraph primary-source passages. This environment
  provides parsed source views but no permitted bulk source download route for
  preserving/verifying complete original passages. Kept short verified spans;
  did not synthesize paragraphs or present stitched snippets as full documents.
  Corpus documentation makes this coverage gap explicit. Local model accuracy
  and full-document accuracy both remain unmeasured.
- Reran rules and committed real updated baseline; full pytest and validate-only
  pass. No reviewed ledger or promotions changed.
- Manual: add the 3 full source passages before claiming full-document coverage.
  P5 CI is gated on all preceding items, so item 13 will remain skipped if this
  gap cannot be completed in this session.

## 6. Ledger-derived labels check: done

- Validate-only now compares linked gold positives against reviewed direction
  and the explicit existing taxonomy mapping. It reports matches, mismatches,
  ambiguous shared-source matches and unlinked observations separately.
- Linked ids are explicit for known corresponding edges; URL + unordered pair
  can discover additional exact-source matches without hiding reversed direction.
  Different historical tranches or cumulative totals are not assumed identical.
- Mismatches are read-only advisories by default so the mandatory validation
  command can still be used while a human adjudicates a conflict; use
  `--strict-ledger` to fail on mismatches or ambiguous links. No source is edited.
- Verified full pytest, validate-only and strict-ledger. Tests deliberately
  reverse a direction, change a type, and reference a missing edge to prove all
  are reported. Current linked corpus has no mismatches.
- Manual: explicitly link any additional historical tranche only after confirming
  it is the same arrangement rather than a subsequent order or cumulative total.

## 7. Single review/promotion path: done via adapter

- Retired the agent's direct ledger writer. Approval exports a one-edge promotions
  YAML plus immutable SQLite before/after audit, and leaves the ledger unchanged.
- Apply with the original `src.review batch`; it adds an append-only application
  audit for agent exports and refuses altered rows or a ledger changed since
  review. Original promotions retain their previous behavior.
- Approval no longer auto-rebuilds a dashboard. Apply the YAML, then `publish`.
  Approved queue status means reviewed/exported, not published. Rich metadata
  stays in the audit; canonical published rows use the original 17 fields.
- Appended the integration decision to DECISIONS.md. Existing promotions and
  financial ledger untouched. Tests use temporary ledgers only and exercise
  both the adapter and actual original batch function, including updates,
  distinct same-day contracts, stale reviews and crash recovery.
- Verified full pytest and validate-only. Manual: use the documented review ->
  original batch -> publish workflow. Never apply development fixtures to ledger.
- Stale exported approvals can be explicitly reopened with a reason. Each new
  export has a revision suffix; previous YAML/audit is preserved. Applied
  approvals cannot be reopened. Canonical workflow: `docs/AGENT_REVIEW.md`.

## 8. Reuse existing ingestion: done

- `run` defaults to the original stored `news_items.csv` when present. It imports
  financing-flagged items without HTTP and reuses full cached SEC text when the
  original filings index points to a local file. Otherwise it labels title and
  snippet scope explicitly, with conservative evidence tier and publisher context.
- `--source news --news-corpus PATH` selects a corpus explicitly; `--source fetch`
  preserves the agent fetcher as fallback. Auto falls back only if no corpus is
  present, so an empty valid corpus does not trigger duplicate network work.
  `--no-fetch` still processes only documents already in SQLite.
- Source identities and document hashes make repeated imports idempotent. A stored
  full primary document is not downgraded to a snippet. No unseen article body is
  inferred from its URL. Malformed rows are recorded as import issues.
- Verified full pytest and validate-only. Tests run ingestion -> extraction ->
  pending queue without network, reuse a cached full filing and check idempotency.
- Manual: refresh the original ingestion first; snippets alone often lack the
  evidence required for a useful deal proposal. Use the explicit fallback when
  you want primary document discovery rather than the stored news corpus.

## 9. Pending review panel: done; visual browser check remains manual

- Added a read-only snapshot export with pending count and the latest five
  candidates: entities, type, original amount text, evidence quote, source link
  and verification status. Approved/rejected items are excluded. Missing queues
  are not created; unreadable queues are shown as unavailable rather than zero.
- Added one card at the top of the existing News tab. Reused the exact current
  card, list, note and status classes; no stylesheet or other panel was restyled.
  Candidate strings use DOM text nodes and source links allow HTTP(S) only.
- `src.site_data` refreshes the snapshot; `python -m deal_agent export-pending`
  refreshes it without analysis or a model. Snapshot time is displayed.
- Verified full pytest, validate-only, JavaScript syntax, read-only exporter
  tests and existing client-side stress parity tests. Metrics match main.
- Manual: view News in light/dark and at phone width. Attempted automated visual
  QA, but no Chromium/Firefox binary is installed in this environment; the
  available Playwright package cannot launch. No browser results are claimed.

## 10. README diet: done

- Moved detailed setup, fetching, review, tracing, evaluation and limitations to
  `docs/DEAL_AGENT.md`, and corrected retired direct-write/auto-publication claims.
- README now has a short agent section with diagram, measured rules-versus-LLM
  table, one reproduction command and documentation links. Original README
  sections match the initial feature commit exactly (verified before editing the agent section).
- Documented corpus gaps, four remaining uncertain labels, sample counts,
  record/replay, news input scope and pending snapshot semantics.
- Verified full pytest, validate-only, diff checks and the original README prefix.
- Manual: follow the local benchmark and review workflow; real model results and
  visual browser checks remain pending as already recorded.

## 11. Interview notes: done

- Appended a plain-English AMD/Anthropic gold-document walkthrough covering
  triage, structured extraction, quote/USD checks, bounded repair, reconciliation,
  human review, promotions and publication. Clearly illustrative, not a model run.
- Added five honest interview questions/answers about evidence of correctness,
  local models, verifier limits, double counting and the next improvements.
  Includes actual rules counts/sample-size limits and Not measured LLM accuracy.
- Verified full pytest and validate-only; checked appended text for em dashes.
- Manual: run the benchmark before replacing any Not measured statement or
  describing model/prompt quality in an interview.

## 12. Prompt v2: done, offline experiment only

- Added separate v2 triage/extract/retry prompts covering unrelated dollars,
  financial roles, unspecified instruments, multi-party payers, caps/floors,
  warrant value versus exercise/guarantee amounts, continuous quotes and fixed
  identity on repair. V1 files are byte-for-byte unchanged and remain default.
- Configuration and `eval/run --prompt-version` select the version. Benchmark
  `--prompt-versions v1 v2` crosses every selected local model with both versions,
  with distinct cassettes and active prompt hashes. No v2 performance claim.
- Corrected rules report provenance to provider=rules and no prompt hashes;
  added actual scored-input counts to both individual and combined reports.
- Offline review exposed an additional gold ambiguity: `nscale_nvidia_warrants`
  now has label_uncertain=true. Its saved receipt quote establishes issuer/holder,
  not the reviewed ledger's financial-support direction. Expected direction/type
  remain unchanged, and strict-ledger still passes. This is a new uncertainty flag,
  not a change to the reviewed ledger. Five document labels are now uncertain.
- Reran real inclusive and uncertainty-excluded rules baselines, refreshed the
  validation report, and tested version selection, v1 immutability, prompt hashes,
  two-model/two-prompt orchestration and the existing synthetic replay fixture.
- Verified full pytest and `eval --validate-only`. Local model accuracy and the
  v1/v2 comparison remain Not measured. Manual: run the recorded benchmark locally.

## 13. Branch CI regression job: skipped

- The user explicitly gated P5 on completion of every earlier item. Item 5 still
  lacks three full-length primary-source passages, so this gate is not satisfied.
  No workflow was added or enabled. Revisit after the corpus coverage gap is closed.
