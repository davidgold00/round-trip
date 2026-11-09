# Deal extraction evaluation

Status: **labels_only**. Model: `qwen2.5:7b-instruct`.
Run: `2f4c2c19ab1b485db748962ae07083f0`. Generated: 2026-11-09T07:48:14.696201+00:00.

Gold corpus: 17 positive and 8 negative documents; 5 uncertain labels. 0 structural label failures.

Scored inputs after uncertainty policy: 0 documents. Validate-only does not run an extractor.

The corpus contains short, attributed excerpts, not full filings. It is a small smoke benchmark; scores do not establish full-document or out-of-time accuracy. Uncertain labels remain identified in manifest.json.

## Local LLM

| Metric | Rules baseline | Local LLM |
|---|---:|---:|
| triage_precision | Not measured | Not measured |
| triage_recall | Not measured | Not measured |
| edge_precision | Not measured | Not measured |
| edge_recall | Not measured | Not measured |
| amount_accuracy | Not measured | Not measured |
| numeric_amount_accuracy | Not measured | Not measured |
| verification_pass_rate | Not measured | Not measured |

Edge matching is directed entity pair + deal_type, one-to-one per document. All predictions are scored, including failed verification; failures are never filtered to improve precision. Amount accuracy scores matched pairs, including correct nulls; numeric accuracy excludes null gold amounts. Numeric tolerance: max($1, 0.1%). Final verification rate includes repaired candidates.

Excluded uncertain labels: False. A failed model call makes the run incomplete; metrics are withheld rather than treating an unavailable model as zero recall.

## Reviewed ledger agreement

8 matched, 0 mismatches, 0 ambiguous, 9 unlinked gold edges.
Mismatches are read-only advisories; use --strict-ledger to make them fatal. Neither side is changed.
