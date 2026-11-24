# Deal extraction evaluation

## Rules baseline versus local LLM

Gold manifest SHA-256: `a80c6c97b7f64b6744563b000811cefa64e9ce56976f52c8ba60288ed9e15d9c`.
Excluded uncertain documents: True.
Scored inputs: 20 documents.

| Metric | Rules baseline | Local LLM |
|---|---:|---:|
| triage_precision | 100.0% | Not measured |
| triage_recall | 41.7% | Not measured |
| edge_precision | 10.0% | Not measured |
| edge_recall | 8.3% | Not measured |
| amount_accuracy | 100.0% | Not measured |
| numeric_amount_accuracy | 100.0% | Not measured |
| verification_pass_rate | 50.0% | Not measured |

All predictions are scored, including failed verification. Directed pair/type matching is one-to-one per document.
Amount accuracy is conditional on matched edges; report its sample count alongside the percentage.
This is a small curated corpus, not a representative accuracy estimate. Synthetic playback never produces model metrics.

### Rules baseline

Status: complete. Counts: `{"amounts_scored": 1, "edge_fn": 11, "edge_fp": 9, "edge_tp": 1, "numeric_amounts_scored": 1, "predictions": 10}`.
Run: `d30705d18c5d484ca010bb3cadd94b90`. Provider: `rules`.
