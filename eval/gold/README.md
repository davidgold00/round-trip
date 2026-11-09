# Source-backed benchmark corpus

The manifest records provenance, SHA-256, expected edges, uncertainty and optional
reviewed-ledger ids. There are 17 positive and 8 negative saved passages, with four
uncertain document labels. The source URL is attribution, not extra model input.
Labels apply only to the saved text. Blank lines separate non-adjacent spans;
editorial attribution in the Amazon supplements is explicitly marked.

Eight cases were added in item 5: five positives and three harder negatives.
The negatives mention dollar figures and two tracked companies, but describe
separate merger challenges or government penalties, with no deal between those
companies. Three positive cases cover two deals announced after 2026-06:
AMD/Anthropic (2026-07-22) and Nscale/Anthropic (2026-08-25, disclosed in the
2026-09-18 S-1). This is a date split relative to v1 development examples, not
proof of held-out model-training data. Cases sharing a release or S-1 are
correlated. Do not quote independent-sample confidence intervals for this set.

Full-length multi-paragraph source passages remain outstanding. These saved
excerpts do not establish full-document accuracy. Chunking has deterministic
coverage and is also tested on source text with deliberately small windows;
that does not substitute for a full-document model benchmark.

Announced date uses the cited source's public disclosure date, which can differ
from contract execution. USD figures preserve explicit caps or instrument values,
not cash paid. Null means no precise USD value in the span. Consideration remains
unknown unless explicitly stated. Only directed pair/type and amount are scored.
Generic cloud-services and compute-capacity types are distinct in edge scoring.

The Amazon 2023 and 2024 instrument corrections include separately attributed SEC
supplements in the input itself. `label_review` records the adjudication evidence.
Microsoft 2023, Nvidia/OpenAI 2025 and the two Oracle arrangements remain uncertain.
Run both inclusive and `--exclude-uncertain` comparisons before relying on scores.

```bash
python -m deal_agent eval --validate-only
python -m deal_agent eval --extractor rules
make agent-bench
```

Validation is offline. Evaluation uses a temporary database and never enqueues to
production. Synthetic cassettes test execution only and never report model metrics.
