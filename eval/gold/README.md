# Source-backed smoke corpus

`manifest.json` is the label/provenance contract. `texts/` contains short
verbatim source spans with an explicitly annotated publisher-context header.
Headers are metadata, never supporting evidence; quotes are only from the body.
The excerpts were checked against their linked primary sources on 2026-11-09.
Source SHA-256 hashes make the saved benchmark reproducible offline.

There are 12 positive and 5 negative documents. Each positive is a distinct
reported arrangement or instrument; the 2019 and 2023 Microsoft investments,
two Amazon tranches, AMD purchase and AMD warrant are separate observations.
A saved span is the entire evaluation input: edges elsewhere in a linked release
are outside that span's labels. Negatives mean no financial deal in the saved
passage, not a claim about an entire publisher's website. Multiple spans are
separated by blank lines, never silently fused into a quote.

Seven cases have `label_uncertain: true` with specific reasons. Confirm their
instrument, payer or date manually before calling those labels definitive.
Cloud commitments in this set use `compute_purchase_commitment` for contracted
infrastructure/capacity, versus `cloud_services_contract` for generic cloud
service supply. These related types are not treated as interchangeable in scoring.
Investment instrument labels can differ from eventual legal convertible-note
mechanics; that is why the Amazon and vague-investment cases are flagged.

Gold amounts preserve an explicitly stated cap/contract figure. Null means no
precise deal value in USD, even if a capacity/share count or vague amount exists.
Gold consideration remains unknown when the excerpt does not establish it.
Only pair/type and amount are scored; confidence and rationale are label metadata.

Run from the repository root:

```bash
python -m deal_agent eval --validate-only
python -m deal_agent eval
python -m deal_agent eval --exclude-uncertain
```

The first validates schema, hashes and evidence with no model or network. The
others require downloaded local Ollama weights and call loopback only. Expected
labels and corpus identifiers are never included in model prompts. Evaluation
has a temporary database and never adds to a production review queue or ledger.
Before relying on scores, extend this initial set with adjudicated full documents,
more difficult negatives and deals announced after prompt development.
