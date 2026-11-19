# Night 3

## State at start

The checked-out branch `feature/deal-extraction-agent` starts at `05d9074` (November 9, 2026). The remote feature tip matches. There are no later commits, no night 2 morning summary, no splits.json, no dev or error report and no live report in this checkout. The laptop's uncommitted files are outside this workspace. PR #1 already exists.

The prior rules run `af0f9c4760ad456ea86b34179efb7321` scored 25 passages (2 TP, 11 FP, 15 FN). The certain-only run `d30705d18c5d484ca010bb3cadd94b90` scored 20 (1 TP, 9 FP, 11 FN). Local LLM quality: Not measured, 0 real model runs. The one committed synthetic cassette exercised replay and repair. Ollama already sends the JSON Schema in `format` and validates responses with Pydantic. The checkout contains the saved news corpus and filing index. Large raw filings are ignored by Git.

## Selection rule recorded before scoring

Group passages about the same source or announced deal together. Keep the two documents used in the existing synthetic demo in development. Stratify on positive, negative and uncertain labels. Reserve at least ten of 25 passages for test. Prior authors had already scored the entire corpus with rules, so this is a prospective comparison on an existing benchmark. Include uncertain labels in the primary comparison. Score all proposed edges, including verification failures.

Choose a completed, real Ollama configuration on dev by directed edge F1, breaking ties by fewer failed verifications, then lower measured time per passage, then model/prompt name. Use the same order among v1 configurations for the comparator. Require at least one additional correctly matched edge at equal or better F1 to adopt a more complex prompt over the strongest baseline. Score the selected configuration, strongest v1 and rules once each on test, reusing a row if both choices coincide. No test tuning. Without completed model runs, report the rules comparison and mark the missing model rows Not measured. Use the existing v1 configuration only for demonstrations with clearly labelled provenance.
