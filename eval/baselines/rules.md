# Deal extraction evaluation

Status: **complete**. Model: `original-rules`.
Run: `62b4d96cdb6a4ec988cf14b8cd9fe6e5`. Generated: 2026-11-09T07:16:17.440862+00:00.

Gold corpus: 17 positive and 8 negative documents; 4 uncertain labels. 0 structural label failures.

The corpus contains short, attributed excerpts, not full filings. It is a small smoke benchmark; scores do not establish full-document or out-of-time accuracy. Uncertain labels remain identified in manifest.json.

## Rules baseline

| Metric | Rules baseline | Local LLM |
|---|---:|---:|
| triage_precision | 100.0% | Not measured |
| triage_recall | 41.2% | Not measured |
| edge_precision | 15.4% | Not measured |
| edge_recall | 11.8% | Not measured |
| amount_accuracy | 100.0% | Not measured |
| numeric_amount_accuracy | 100.0% | Not measured |
| verification_pass_rate | 53.8% | Not measured |

Edge matching is directed entity pair + deal_type, one-to-one per document. All predictions are scored, including failed verification; failures are never filtered to improve precision. Amount accuracy scores matched pairs, including correct nulls; numeric accuracy excludes null gold amounts. Numeric tolerance: max($1, 0.1%). Final verification rate includes repaired candidates.

Excluded uncertain labels: False. A failed model call makes the run incomplete; metrics are withheld rather than treating an unavailable model as zero recall.

## Reviewed ledger agreement

8 matched, 0 mismatches, 0 ambiguous, 9 unlinked gold edges.
Mismatches are read-only advisories; use --strict-ledger to make them fatal. Neither side is changed.
