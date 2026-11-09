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
