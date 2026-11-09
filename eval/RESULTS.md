# Deal extraction evaluation

## Rules baseline versus local LLM

Gold manifest SHA-256: `951a49eab345833bdb6d149058b02507304811f7ba8dc71f0b991ba8739e42da`.
Excluded uncertain documents: False.

| Metric | Rules baseline | Local LLM |
|---|---:|---:|
| triage_precision | 100.0% | Not measured |
| triage_recall | 41.7% | Not measured |
| edge_precision | 9.1% | Not measured |
| edge_recall | 8.3% | Not measured |
| amount_accuracy | 100.0% | Not measured |
| numeric_amount_accuracy | 100.0% | Not measured |
| verification_pass_rate | 45.5% | Not measured |

All predictions are scored, including failed verification. Directed pair/type matching is one-to-one per document.
Amount accuracy is conditional on matched edges; report its sample count alongside the percentage.
This is a small curated corpus, not a representative accuracy estimate. Synthetic playback never produces model metrics.

### Rules baseline

Status: complete. Counts: `{"amounts_scored": 1, "edge_fn": 11, "edge_fp": 10, "edge_tp": 1, "numeric_amounts_scored": 1, "predictions": 11}`.
Run: `005e28cbbdc941158a3d911ec72c535f`. Provider: `ollama`.
