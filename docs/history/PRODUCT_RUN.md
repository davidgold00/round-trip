# Local product run

Integration base `27b4b05730e2179fddf08aceb9e20ce64f1c062a` is the head of PR #1. Main at inspection was `ceedd24d4d4a3d10486041996879ca2e6b2bb186`. An isolated worktree on `codex/local-product-refinement` preserves a divergent local feature head at `94298cf`. Its five unpublished commits include a different freeze and 49-document corpus. Do not cherry-pick its split into this comparison.

The published freeze has 15 dev passages and ten reserved for test. The previous all-corpus rules scores predate that freeze. The dev rules run and three-call Qwen v1 example have recordings. The local checkout also held eight traces and a labels-only latest report with no completed live score. The six-call prefix described in the night-three notes was unavailable here. No post-freeze test score was found in the two branches, PR description/discussion, or project artifacts inspected. The integration owner owns the final score and merge.

## Experiment checkpoint

Use the [prospective selection rule](NIGHT3.md#selection-rule-recorded-before-scoring). Benchmark original rules and downloaded Llama 3.2 3B v1 on all 15 dev passages. Apple M3, eight CPU cores, 8 GiB unified memory. Installed alternatives include Qwen 1.5B and 7B, Phi 3.5, and Llama 3.1 8B. The historical Qwen example took about 324 seconds for three calls. This run uses loopback Ollama, temperature 0, seed 42 and 8,192 context tokens. The first small-model triage calls took about 2–3 seconds and an extraction about 10 seconds. Raw progress is local under `eval/results/` and `eval/cassettes/`. Resume only the corresponding directory with the original model and prompt. The first live run ID is `28c1703818f84c469a786e85feb1dd63`.

## Publication audit

The project environment file contains operator-specific SEC configuration and stays local. The tracked example uses placeholders. Current instructions use an audit alias. New reviews default to a neutral alias and accept `ROUNDTRIP_REVIEWER` or `--actor`. New commits use a project pseudonym. The local database, raw traces, unrestricted cassettes and application audit stay outside version control.

Reachable earlier commits contain an operator identity in author/committer metadata and examples of named reviewers. These examples also occur in the public PR description and its historical diff. A scan checked reachable blobs, including compressed evidence, for the configured contact, home paths and common credential patterns. The tracked snapshot contained no match for the configured contact. The public repository reported zero Actions runs, zero Actions artifacts, zero releases and Pages disabled. Historical cleanup and hosted edits require a separate owner decision.

## First completed development comparison

Original rules produced 1 TP, 11 FP and 9 FN. Llama 3.2 3B v1 produced 2 TP, 15 FP and 8 FN (11.8% precision and 20% recall). Six of 17 final proposals passed verification. All ten positives reached extraction. A purchase from CoreWeave came back reversed, AWS was confused with the recipient of an investment, and a capped amount lost a zero. The baseline completed 39 calls in 350 seconds across 15 passages. Test the role instructions and the evidence-span instructions independently, preserving v1 triage, repair, schema, generation settings and scorer. Use their combination as a separate configuration if dev evidence warrants it.

## Dashboard and interview paths

The browser showed object strings in force-graph edges, misleading denominator copy and an empty inbox with no discoverable example. Selecting a different stress slider also silently changed the people receiving a single-company shock. The dashboard now exposes a source-backed example independently of the queue, preserves the shock recipients, and compares outcomes with the starting preset. An explicit custom shock still targets private labs. Static interview assets rebuild with `make guide`. Browser checks cover both themes, eight phone-width panels, keyboard selection, the ledger and source detail.

Browser captures contain rendered public data only. [Desktop headline](../screenshots/headline-desktop.png) · [Stress comparison](../screenshots/stress-comparison.png) · [Phone review](../screenshots/review-mobile.png).
