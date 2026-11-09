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
