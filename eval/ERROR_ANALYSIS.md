# Development error analysis

Each FP is an extra directed pair/type. Each FN is a missing one. A reversed proposal can produce both. Each failed verifier check is listed at its actual attempt, including a failure later repaired. Counts are diagnostic events, so the same document can contribute several. Categories describe observed differences, not a hidden reason for the model's decision.

## qwen2.5:7b-instruct / v1

15 passages. [Run `a64e32868cb44af7931521fef23a1237`](evidence/dev/qwen-v1.json).

Most frequent categories: confusable deal_type (8), amount wording absent from quote (3), wrong direction (2).

| Document | Event | Category | Evidence |
|---|---|---|---|
| microsoft_openai_2019 | first check | amount wording absent from quote | amount_text is missing from evidence_quote |
| microsoft_openai_2019 | repair check | amount wording absent from quote | amount_text is missing from evidence_quote |
| amazon_anthropic_2023 | FN | confusable deal_type | Amazon → Anthropic → debt_or_loan |
| amazon_anthropic_2023 | FP | confusable deal_type | Amazon → Anthropic → equity_investment |
| amazon_anthropic_2023 | FP | confusable deal_type | Amazon → Anthropic → equity_investment |
| amazon_anthropic_2024 | FN | confusable deal_type | Amazon → Anthropic → debt_or_loan |
| amazon_anthropic_2024 | FP | confusable deal_type | Amazon → Anthropic → equity_investment |
| amazon_anthropic_2024 | FP | confusable deal_type | Amazon → Anthropic → equity_investment |
| coreweave_openai_2025 | FN | wrong direction | OpenAI → CoreWeave → compute_purchase_commitment |
| coreweave_openai_2025 | FP | wrong direction | CoreWeave → OpenAI → cloud_services_contract |
| oracle_openai_2025 | FN | label dispute | OpenAI → Oracle → compute_purchase_commitment |
| nvidia_coreweave_2025 | FN | confusable deal_type | Nvidia → CoreWeave → compute_purchase_commitment |
| nvidia_coreweave_2025 | FP | confusable deal_type | Nvidia → CoreWeave → cloud_services_contract |
| nscale_anthropic_2026 | FN | triage miss | Anthropic → Nscale → compute_purchase_commitment |
| nscale_microsoft_2026 | FN | triage miss | Microsoft → Nscale → compute_purchase_commitment |
| nscale_nvidia_warrants | first check | amount wording absent from quote | amount_text is missing from evidence_quote |

| Model confidence | Correct / proposed | Distinct source URLs |
|---|---:|---:|
| below 0.70 | Not measured (0/0) | 0 |
| 0.70 to <0.90 | Not measured (0/0) | 0 |
| 0.90 to 1.00 | 33.3% (3/9) | 7 |

3 passages have uncertain labels. They are included above.
The review-only convertible-note advisory flags 2 of 9 saved proposals, including 2 directed pair/type errors. It changes zero predictions and zero verification decisions.

## Original rules

15 passages. [Run `12ea4134fa2e47fbb91c936e524724dd`](evidence/dev/rules.json).

Most frequent categories: missed or spurious alias (12), wrong direction (8), triage miss (4).

| Document | Event | Category | Evidence |
|---|---|---|---|
| microsoft_openai_2019 | FN | wrong direction | Microsoft → OpenAI → equity_investment |
| microsoft_openai_2019 | FP | missed or spurious alias | OpenAI → Meta → equity_investment |
| microsoft_openai_2019 | first check | missed or spurious alias | entity absent from document text: Meta |
| microsoft_openai_2019 | FP | wrong direction | OpenAI → Microsoft → equity_investment |
| microsoft_openai_2019 | FP | missed or spurious alias | OpenAI → Intel → equity_investment |
| microsoft_openai_2019 | first check | missed or spurious alias | unknown target entity: Intel |
| nvidia_openai_2025 | FP | missed or spurious alias | Nvidia → Meta → equity_investment |
| nvidia_openai_2025 | first check | missed or spurious alias | entity absent from document text: Meta |
| amazon_anthropic_2023 | FN | wrong direction | Amazon → Anthropic → debt_or_loan |
| amazon_anthropic_2023 | FP | missed or spurious alias | Anthropic → Meta → debt_or_loan |
| amazon_anthropic_2023 | first check | missed or spurious alias | entity absent from document text: Meta |
| amazon_anthropic_2023 | FP | wrong direction | Anthropic → Amazon → debt_or_loan |
| amazon_anthropic_2024 | FN | wrong direction | Amazon → Anthropic → debt_or_loan |
| amazon_anthropic_2024 | FP | missed or spurious alias | Anthropic → Meta → debt_or_loan |
| amazon_anthropic_2024 | first check | missed or spurious alias | entity absent from document text: Meta |
| amazon_anthropic_2024 | FP | wrong direction | Anthropic → Amazon → debt_or_loan |
| coreweave_openai_2025 | FN | confusable deal_type | OpenAI → CoreWeave → compute_purchase_commitment |
| coreweave_openai_2025 | FP | missed or spurious alias | Meta → CoreWeave → cloud_services_contract |
| coreweave_openai_2025 | first check | missed or spurious alias | entity absent from document text: Meta |
| coreweave_openai_2025 | FP | confusable deal_type | OpenAI → CoreWeave → cloud_services_contract |
| oracle_openai_2025 | FN | triage miss | OpenAI → Oracle → compute_purchase_commitment |
| nvidia_coreweave_2025 | FN | triage miss | Nvidia → CoreWeave → compute_purchase_commitment |
| nscale_anthropic_2026 | FN | triage miss | Anthropic → Nscale → compute_purchase_commitment |
| nscale_microsoft_2026 | FN | triage miss | Microsoft → Nscale → compute_purchase_commitment |
| nscale_nvidia_warrants | FN | wrong direction | Nvidia → Nscale → warrants_or_options |
| nscale_nvidia_warrants | FP | wrong direction | Nscale → Nvidia → warrants_or_options |

3 passages have uncertain labels. They are included above.
The review-only convertible-note advisory flags 0 of 12 saved proposals, including 0 directed pair/type errors. It changes zero predictions and zero verification decisions.

## What to investigate

The rules adapter guesses financial direction. It also matches Meta inside the editorial word `metadata` and Intel inside `intelligence`; the exact-node verifier catches those proposals. A missing positive on which rules proposed nothing is a triage miss at the rules stage. The short excerpts provide little evidence about full-document chunk boundaries. Use the model-specific rows above to choose a prompt or verifier experiment.
