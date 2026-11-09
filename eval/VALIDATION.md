# Deal extraction evaluation

Status: **labels_only**. Model: `qwen2.5:7b-instruct`.
Run: `c1673536a1de4ff1a3c373952ad2e44a`. Generated: 2026-11-09T06:22:33.896919+00:00.

Gold corpus: 12 positive and 5 negative documents; 7 uncertain labels. 0 structural label failures.

The corpus contains short, attributed excerpts, not full filings. It is a small smoke benchmark; scores do not establish full-document or out-of-time accuracy. Uncertain labels remain identified in manifest.json.

| Metric | Result |
|---|---:|
| triage_precision | Not measured |
| triage_recall | Not measured |
| edge_precision | Not measured |
| edge_recall | Not measured |
| amount_accuracy | Not measured |
| numeric_amount_accuracy | Not measured |
| verification_pass_rate | Not measured |

Edge matching is directed entity pair + deal_type, one-to-one per document. All predictions are scored, including failed verification; failures are never filtered to improve precision. Amount accuracy scores matched pairs, including correct nulls; numeric accuracy excludes null gold amounts. Numeric tolerance: max($1, 0.1%). Final verification rate includes repaired candidates.

Excluded uncertain labels: False. A failed model call makes the run incomplete; metrics are withheld rather than treating an unavailable model as zero recall.

