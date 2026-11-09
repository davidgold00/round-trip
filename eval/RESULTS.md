# Deal extraction evaluation

## Rules baseline versus local LLM

Gold manifest SHA-256: `92fda0a8c8e5738ffe1f62a12aa1f5fd3a25dc2e2786bd2204bb7b1648aa3aac`.
Excluded uncertain documents: False.

| Metric | Rules baseline | Local LLM |
|---|---:|---:|
| triage_precision | 100.0% | Not measured |
| triage_recall | 41.2% | Not measured |
| edge_precision | 15.4% | Not measured |
| edge_recall | 11.8% | Not measured |
| amount_accuracy | 100.0% | Not measured |
| numeric_amount_accuracy | 100.0% | Not measured |
| verification_pass_rate | 53.8% | Not measured |

All predictions are scored, including failed verification. Directed pair/type matching is one-to-one per document.
Amount accuracy is conditional on matched edges; report its sample count alongside the percentage.
This is a small curated corpus, not a representative accuracy estimate. Synthetic playback never produces model metrics.

### Rules baseline

Status: complete. Counts: `{"amounts_scored": 2, "edge_fn": 15, "edge_fp": 11, "edge_tp": 2, "numeric_amounts_scored": 2, "predictions": 13}`.
Run: `62b4d96cdb6a4ec988cf14b8cd9fe6e5`. Provider: `ollama`.
