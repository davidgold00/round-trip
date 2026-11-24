# Development runs

| Configuration | Edge precision | Edge recall | Verification pass | Parse failures / calls | Seconds / passage | Passages | Evidence |
|---|---:|---:|---:|---:|---:|---:|---|
| Original rules | 8.3% (1/12) | 10.0% (1/10) | 50.0% (6/12) | n/a (rules) | 0.001 | 15 | [`12ea4134fa2e47fbb91c936e524724dd`](evidence/dev/rules.json) · [cassette](evidence/dev/rules.cassette.json.gz) |

All scores include failed verification and uncertain labels. Time is local extraction and checking per saved passage. For a resumed prefix, it includes recorded inference time. Raw model responses and deterministic rules observations have different cassette formats.
