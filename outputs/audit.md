# Self-audit: random re-verification of ledger rows

Run 2026-10-06 with `python -m src.audit -n 20` (seed 20261005, so the sample is
reproducible). Twenty rows were drawn at random from `ledger/edges.csv` and
`ledger/backlog.csv` combined, each row's cited source was re-fetched, and each
row's `quote_snippet` was searched for in that document.

## Result

* **19 of 20 rows verified.** The quote was found in the document the row cites.
* **0 rows failed.** No row's quote was absent from a source that could be retrieved.
* **1 row could not be re-checked mechanically** because the publisher blocks automated fetches. Details below.

## What the mechanical check does and does not cover

It covers one thing: is the quote actually in the document the row points at?
It does not, and cannot, tell you whether the quote supports the amount, the
direction or the status recorded. Those were checked by reading each source at
promotion time, and the findings below came out of that reading, not out of the
string search.

## Corrections made as a result of this audit

**1. Two backlog rows carried a paraphrase where a quote was required.**

The rows recording Nvidia's and AMD's tagged remaining performance obligations
had `quote_snippet` values reading "RevenueRemainingPerformanceObligation tagged
at $3.2 billion as of July 26, 2026" and the AMD equivalent. That is a
description of an XBRL tag, not a verbatim quote from a filing, and it breaks
this project's own rule. The audit caught it as a token-overlap failure at 71%.

Both rows were replaced with verbatim text from the filings:

* Nvidia 10-Q, accession 0001045810-26-000075: "revenue related to remaining
  performance obligations from contracts greater than one year in length was
  $3.2 billion".
* AMD 10-Q, accession 0000002488-26-000123: "the aggregate transaction price
  allocated to remaining performance obligations under contracts with an original
  expected duration of more than one year was $222 million".

**2. A substantive error was found while fetching those quotes.**

Both rows were annotated "covers software and services only" and the metric was
named `rpo_software_only`. Reading AMD's actual sentence shows that is wrong:
AMD says the figure covers "development and engineering services, IP licensing,
and product revenue". It does include product revenue. What it excludes is
contracts with an original duration of one year or less, which is how almost all
of AMD's product business is sold.

The metric was renamed `rpo_long_term_contracts_only` for both companies and the
notes were rewritten. The conclusion is unchanged and the reason for it is now
stated correctly: neither figure is a product backlog, so neither is used as a
denominator. Nvidia and AMD therefore carry no headline number at all.

**3. One source blocks automated re-fetch.**

The Broadcom investor-relations page for the OpenAI collaboration
(`openai-and-broadcom-announce-strategic-collaboration-deploy-10`) returns HTTP
403 to a scripted request. It is readable in a browser and was read at promotion
time. The row it supports is recorded at **zero dollars** because neither party
disclosed an amount, so it contributes nothing to any dollar-weighted figure; it
appears only as a funding-link and structural edge. No corroborating SEC filing
exists: Broadcom's 8-K index contains no OpenAI reference, and its 10-Q refers to
"a long-term contract for custom AI accelerators" without naming a customer.

This is logged as its own audit category rather than counted as a pass, because
a row whose source cannot be re-fetched is weaker than one whose source can.

## Row-by-row result

| row | kind | tier | quote found | method |
|---|---|---|---|---|
| `Amazon/contracted_backlog/2026-06-30` | backlog | T1 | yes | verbatim |
| `Nscale/rpo/2026-06-30` | backlog | T1 | yes | token overlap 100% |
| `Nvidia/rpo_long_term_contracts_only/2026-07-26` | backlog | T1 | yes | verbatim |
| `amazon__anthropic__equity_investment__20260731` | edge | T1 | yes | verbatim |
| `amazon__anthropic__vendor_financing__20260731` | edge | T1 | yes | verbatim |
| `amazon__openai__equity_investment__20260430` | edge | T1 | yes | verbatim |
| `anthropic__amazon__cloud_capacity_contract__20260731` | edge | T1 | yes | token overlap 100% |
| `anthropic__microsoft__cloud_capacity_contract__20251118` | edge | T2 | yes | verbatim |
| `meta__coreweave__cloud_capacity_contract__20260812` | edge | T1 | yes | token overlap 100% |
| `meta__nebius__cloud_capacity_contract__20251112` | edge | T1 | yes | verbatim |
| `microsoft__anthropic__equity_investment__20251118` | edge | T2 | yes | verbatim |
| `microsoft__nscale__cloud_capacity_contract__20260918` | edge | T1 | yes | verbatim |
| `nvidia__coreweave__cloud_capacity_contract__20260422` | edge | T1 | yes | verbatim |
| `nvidia__coreweave__equity_investment__20260131` | edge | T1 | yes | token overlap 100% |
| `nvidia__nscale__cloud_capacity_contract__20260918` | edge | T1 | yes | verbatim |
| `nvidia__nscale__loan_or_guarantee__20260918` | edge | T1 | yes | verbatim |
| `nvidia__nscale__warrants__20260918` | edge | T1 | yes | verbatim |
| `nvidia__openai__equity_investment__20250922` | edge | T2 | yes | verbatim |
| `softbank__openai__equity_investment__20261001` | edge | T2 | yes | verbatim |
| `openai__broadcom__purchase_commitment__20251013` | edge | T2 | NO | source could not be retrieved for re-check |

## Reproducing this

```
python -m src.audit -n 20 --seed 20261005
```

The seed is fixed so the sample is the same every run. Change it to draw a
different twenty. Results are written to `outputs/audit.json` and this file is
the analyst's write-up of them.
