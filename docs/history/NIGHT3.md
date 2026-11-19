# Night 3

## State at start

The checked-out branch `feature/deal-extraction-agent` starts at `05d9074` (November 9, 2026). The remote feature tip matches. There are no later commits, no night 2 morning summary, no splits.json, no dev or error report and no live report in this checkout. The laptop's uncommitted files are outside this workspace. PR #1 already exists.

The prior rules run `af0f9c4760ad456ea86b34179efb7321` scored 25 passages (2 TP, 11 FP, 15 FN). The certain-only run `d30705d18c5d484ca010bb3cadd94b90` scored 20 (1 TP, 9 FP, 11 FN). Local LLM quality: Not measured, 0 real model runs. The one committed synthetic cassette exercised replay and repair. Ollama already sends the JSON Schema in `format` and validates responses with Pydantic. The checkout contains the saved news corpus and filing index. Large raw filings are ignored by Git.

## Selection rule recorded before scoring

Group passages about the same source or announced deal together. Keep the two documents used in the existing synthetic demo in development. Stratify on positive, negative and uncertain labels. Reserve at least ten of 25 passages for test. Prior authors had already scored the entire corpus with rules, so this is a prospective comparison on an existing benchmark. Include uncertain labels in the primary comparison. Score all proposed edges, including verification failures.

Choose a completed, real Ollama configuration on dev by directed edge F1, breaking ties by fewer failed verifications, then lower measured time per passage, then model/prompt name. Use the same order among v1 configurations for the comparator. Require at least one additional correctly matched edge at equal or better F1 to adopt a more complex prompt over the strongest baseline. Score the selected configuration, strongest v1 and rules once each on test, reusing a row if both choices coincide. No test tuning. Without completed model runs, report the rules comparison and mark the missing model rows Not measured. Use the existing v1 configuration only for demonstrations with clearly labelled provenance.

## A0. Frozen partitions and benchmark inputs

The freeze uses seed 20261119, ten positive and five negative dev passages (three uncertain), seven positive and three negative test passages (two uncertain). Shared releases, the Nscale filing excerpts and the AMD/OpenAI filing/announcement stay on one side. No new Python dependency. Ollama and downloaded weights are local setup dependencies outside Git.

## Reading and review changes

A4 records applied human decisions, corrections and reopened approvals in an idempotent local feedback projection. Exact held-out sources are filtered before future development use. B1 to B3 supply a single entry point, one read-only inbox across both queue formats and a numbered guide. The original decision log and historical methodology are preserved. Markdown-it-py and its small URL parser are used only for CommonMark link validation, so fenced examples and reference links are interpreted the same way as rendered links.
