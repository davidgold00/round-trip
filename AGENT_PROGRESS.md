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
