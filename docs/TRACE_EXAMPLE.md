# One candidate, end to end

Run `make demo`, then `make explain ID=a_81cddd0804260229a87a`. This is a recorded local qwen2.5:7b-instruct extraction from a development source, prompt v1. The extractor run was `a64e32868cb44af7931521fef23a1237`. A separate offline replay produced the checks and queue events quoted below.

## 1. Read the source

The input is the cached OpenAI disclosure dated 2019-07-22. The recorded SHA identifies the exact text that the verifier can search.

```jsonl
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.354548+00:00", "stage": "document.read", "kind": "tool", "inputs": {"document": "abf67d748d22f6de0345617f2a9d59bcfb14779d8c8eadede02e734f8185ddc3", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/"}, "outputs": {"sha256": "abf67d748d22f6de0345617f2a9d59bcfb14779d8c8eadede02e734f8185ddc3", "characters": 186}, "latency_ms": 0.054, "model": null}
```

## 2. Admit the passage

The first screen finds tracked companies and a financing term. The model then explains why this particular passage contains a possible deal.

```jsonl
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.359554+00:00", "stage": "triage.keyword", "kind": "stage", "inputs": {"chunk_sha256": "abf67d748d22f6de0345617f2a9d59bcfb14779d8c8eadede02e734f8185ddc3"}, "outputs": {"relevant": true, "entities": ["Microsoft", "OpenAI"], "hits": ["investing", "billion"]}, "latency_ms": 0, "model": null}
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.364551+00:00", "stage": "triage.decision", "kind": "stage", "inputs": {"chunk_sha256": "abf67d748d22f6de0345617f2a9d59bcfb14779d8c8eadede02e734f8185ddc3"}, "outputs": {"relevant": true, "reason": "The passage describes a financial relationship between Microsoft and OpenAI, specifically an investment of $1 billion, which fits the criteria of a deal as defined."}, "latency_ms": 0, "model": null}
```

## 3. Extract the relationship

The prompt hash identifies the instructions. The parse event includes the original model text as its input and the schema-validated fields as its output.

```jsonl
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.365781+00:00", "stage": "prompt", "kind": "stage", "inputs": {"version": "v1", "name": "extract"}, "outputs": {"sha256": "e7de3ceb1ad467deb6935ac7e081f384f161c49b0fd1df71c407de7bddf361e1"}, "latency_ms": 0, "model": null}
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.367540+00:00", "stage": "extract.parse", "kind": "tool", "inputs": {"response": "{\n  \"edges\": [\n    {\n      \"source_entity\": \"Microsoft\",\n      \"target_entity\": \"OpenAI\",\n      \"deal_type\": \"equity_investment\",\n      \"consideration_type\": \"cash\",\n      \"amount_usd\": 1000000000,\n      \"amount_text\": \"one billion\",\n      \"term_or_duration\": null,\n      \"announced_date\": \"2019-07-22\",\n      \"source_url\": \"https://openai.com/index/microsoft-invests-in-and-partners-with-openai/\",\n      \"evidence_quote\": \"Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.\",\n      \"confidence\": 1,\n      \"rationale\": \"Directly stated in the passage.\"\n    }\n  ]\n}"}, "outputs": {"edges": [{"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}]}, "latency_ms": 0.294, "model": null}
```

## 4. Verify and try one repair

The first amount-text check fails. The model writes “one billion” where the source says “$1 billion”. The repair is checked against the same source and the original failure remains auditable.

```jsonl
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.368422+00:00", "stage": "verify", "kind": "tool", "inputs": {"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}, "outputs": {"passed": false, "errors": ["amount_text is missing from evidence_quote"], "source_node": "Microsoft", "target_node": "OpenAI", "checks": ["verbatim_quote", "USD_amount", "known_nodes", "entities_in_text_or_filer_metadata", "source_url"], "details": {"verbatim_quote": {"result": "pass", "errors": []}, "known_nodes": {"result": "pass", "errors": []}, "source_url": {"result": "pass", "errors": []}, "entities_in_text_or_filer_metadata": {"result": "pass", "errors": []}, "USD_amount": {"result": "fail", "errors": ["amount_text is missing from evidence_quote"]}}}, "latency_ms": 0.686, "model": null}
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.371399+00:00", "stage": "retry.parse", "kind": "tool", "inputs": {"response": "{\n  \"edges\": [\n    {\n      \"source_entity\": \"Microsoft\",\n      \"target_entity\": \"OpenAI\",\n      \"deal_type\": \"equity_investment\",\n      \"consideration_type\": \"cash\",\n      \"amount_usd\": 1000000000.0,\n      \"amount_text\": \"one billion\",\n      \"term_or_duration\": null,\n      \"announced_date\": \"2019-07-22\",\n      \"source_url\": \"https://openai.com/index/microsoft-invests-in-and-partners-with-openai/\",\n      \"evidence_quote\": \"Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.\",\n      \"confidence\": 1.0,\n      \"rationale\": \"Directly stated in the passage.\"\n    }\n  ]\n}"}, "outputs": {"edges": [{"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}]}, "latency_ms": 0.069, "model": null}
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.372222+00:00", "stage": "verify.retry", "kind": "tool", "inputs": {"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}, "outputs": {"passed": false, "errors": ["amount_text is missing from evidence_quote"], "source_node": "Microsoft", "target_node": "OpenAI", "checks": ["verbatim_quote", "USD_amount", "known_nodes", "entities_in_text_or_filer_metadata", "source_url"], "details": {"verbatim_quote": {"result": "pass", "errors": []}, "known_nodes": {"result": "pass", "errors": []}, "source_url": {"result": "pass", "errors": []}, "entities_in_text_or_filer_metadata": {"result": "pass", "errors": []}, "USD_amount": {"result": "fail", "errors": ["amount_text is missing from evidence_quote"]}}}, "latency_ms": 0.759, "model": null}
```

## 5. Reconcile and queue

The actual classification is NEW. It compares the pair, type, source, date and amount with prior records. A proposal enters pending review even when a check fails.

```jsonl
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.373431+00:00", "stage": "reconcile", "kind": "tool", "inputs": {"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}, "outputs": {"classification": "NEW", "match_id": null, "reason": "No same-direction, same-type deal with shared source/date or unique expansion antecedent", "related_ids": ["microsoft__openai__equity_investment__20251029", "c_42eafa33d99cb9", "c_16bddfbf4114ba", "c_1f1a0e1c724a15", "c_7e0eedcee762a2", "c_7d7810545e45f4", "c_ab45c8380c84ed", "c_4ae914f888c8eb", "c_4660623ccfb760", "c_b711018ebc94dc", "c_a84e177f8eff54", "c_1444b22a10bc14", "c_6a3193c0b04ef7", "c_f97e71ff6e571e"]}, "latency_ms": 0.827, "model": null}
{"run_id": "91ffb4fbec0d454484fce57543cea5c3", "timestamp": "2026-11-19T07:08:25.373576+00:00", "stage": "propose", "kind": "tool", "inputs": {"source_entity": "Microsoft", "target_entity": "OpenAI", "deal_type": "equity_investment", "consideration_type": "cash", "amount_usd": 1000000000.0, "amount_text": "one billion", "term_or_duration": null, "announced_date": "2019-07-22", "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/", "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.", "confidence": 1.0, "rationale": "Directly stated in the passage."}, "outputs": true, "latency_ms": 0.084, "model": null}
```

## 6. Review and financial effect

The recorded review outcome is **pending**. There is no human approval or applied promotion for this candidate. If independently confirmed, an eligible Microsoft-to-OpenAI investment could change Microsoft's share of OpenAI's documented funding, and therefore the share of eligible customer commitments attributed back to Microsoft. A reviewer would first have to check whether existing cumulative terms already cover the amount. No incremental metric or stress delta has been measured.

[Source passage](../eval/gold/texts/microsoft_openai_2019.txt) · [Recorded calls](../eval/example/cassette.json) · [Replay trace](../eval/example/trace.jsonl) · [Queue and review state](../eval/example/story.json)

## Exact command output

```text
Candidate a_81cddd0804260229a87a
Source: OpenAI | 2019-07-22 | https://openai.com/index/microsoft-invests-in-and-partners-with-openai/
Source text SHA-256: abf67d748d22f6de0345617f2a9d59bcfb14779d8c8eadede02e734f8185ddc3
Evidence: Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.
Recorded local inference run: a64e32868cb44af7931521fef23a1237
Keyword triage: admitted; companies Microsoft, OpenAI; terms investing, billion.
triage prompt v1 | template 474341b44a23ae31058714f9dc4e488115f1a9841f28f91131c4b74582e3e428
Raw qwen2.5:7b-instruct triage response:
{
  "relevant": true,
  "reason": "The passage describes a financial relationship between Microsoft and OpenAI, specifically an investment of $1 billion, which fits the criteria of a deal as defined."
}
Model triage: The passage describes a financial relationship between Microsoft and OpenAI, specifically an investment of $1 billion, which fits the criteria of a deal as defined.
extract prompt v1 | template e7de3ceb1ad467deb6935ac7e081f384f161c49b0fd1df71c407de7bddf361e1
Raw qwen2.5:7b-instruct extract response:
{
  "edges": [
    {
      "source_entity": "Microsoft",
      "target_entity": "OpenAI",
      "deal_type": "equity_investment",
      "consideration_type": "cash",
      "amount_usd": 1000000000,
      "amount_text": "one billion",
      "term_or_duration": null,
      "announced_date": "2019-07-22",
      "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/",
      "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.",
      "confidence": 1,
      "rationale": "Directly stated in the passage."
    }
  ]
}
verify: failed
  verbatim_quote: pass
  known_nodes: pass
  source_url: pass
  entities_in_text_or_filer_metadata: pass
  USD_amount: fail | amount_text is missing from evidence_quote
retry prompt v1 | template 1989d18a64d447638c8d2623af75ce05e34710fd71241242ff228e74321c7f89
Raw qwen2.5:7b-instruct retry response:
{
  "edges": [
    {
      "source_entity": "Microsoft",
      "target_entity": "OpenAI",
      "deal_type": "equity_investment",
      "consideration_type": "cash",
      "amount_usd": 1000000000.0,
      "amount_text": "one billion",
      "term_or_duration": null,
      "announced_date": "2019-07-22",
      "source_url": "https://openai.com/index/microsoft-invests-in-and-partners-with-openai/",
      "evidence_quote": "Microsoft is investing $1 billion in OpenAI to support us building artificial general intelligence (AGI) with widely distributed economic benefits.",
      "confidence": 1.0,
      "rationale": "Directly stated in the passage."
    }
  ]
}
verify.retry: failed
  verbatim_quote: pass
  known_nodes: pass
  source_url: pass
  entities_in_text_or_filer_metadata: pass
  USD_amount: fail | amount_text is missing from evidence_quote
Reconcile: NEW | No same-direction, same-type deal with shared source/date or unique expansion antecedent
Human review: pending
Ledger and dashboard effect: no applied promotion. Eligible funding enters OpenAI's documented funding denominator and the funding network used by stress. A duplicate adds no new dollars.
```
