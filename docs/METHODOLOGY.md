# Methodology

The pre-registered definitions live in `DECISIONS.md` Part A and are the
authority. This document explains them in prose and states what the design can
and cannot deliver.

## The question

For each seller of AI infrastructure, what share of its own disclosed backlog is
owed by a customer whose funding traces back to that same seller?

The question is deliberately narrow. It is not "is this a bubble". It is not "is
the backlog real". It is one thing: how much of the promise to pay was financed
by the party being paid.

## The ledger

One row per directed edge, with a source URL, a verbatim quote under 25 words,
and an SEC accession number on every T1 row. Direction is money-flow: the arrow
starts at whoever pays. Funding edges run funder to recipient, purchase and
capacity edges run buyer to seller. A round trip is therefore a two-cycle, which
`tests/test_direction.py` asserts.

Nothing enters the ledger automatically. `src/extract.py` writes candidates only,
and `tests/test_no_autopromote.py` parses its source to confirm the module never
references `edges.csv`. Promotion is `python -m src.review`, which refuses a
promotion without a quote, refuses a T1 row without an accession number, and
refuses T4 evidence outright.

## Evidence tiers

| tier | meaning | headline | sensitivity view |
|---|---|---|---|
| T1 | SEC filing | yes | yes |
| T2 | company release or IR page | yes | yes |
| T3 | reputable media report | no | yes, labelled |
| T4 | unverified or rumour | never | never |

## Normalisation

Every amount is carried as a `[low, high]` pair; a single disclosed figure is
stored with low equal to high. Amounts are normalised to total contract value,
because disclosed remaining performance obligations and announced deal headlines
are both multi-year totals. A per-year amount is multiplied by its term, or by
the configured default of five years when the term is not disclosed, and the row
is flagged.

Each edge is multiplied by a status weight before entering any metric. The
weights were set before any result was computed and are varied in the stress lab.
A non-binding letter of intent is never counted at full weight by default.

## The three readings

For seller `i` and customer `j`:

```
D[i, j]                = share of i's disclosed backlog that j has committed
Provenance_LOWER       = funding(i to j) / commitment(j to i), capped at 1
Provenance_CENTRAL     = i's share of j's documented external funding, with
                         multi-hop paths traced back and discounted
Provenance_UPPER       = 1 if i has any T1 or T2 funding link to j, else 0
RTE_b(i)               = sum over j of D[i, j] times Provenance_b(i to j)
```

**These three are not guaranteed to nest.** LOWER divides i's funding by j's
commitment to i; CENTRAL divides the same funding by j's whole documented
funding. When i funded j heavily relative to that one commitment but j has many
other funders, LOWER exceeds CENTRAL. Amazon and Anthropic is exactly that case
in the current data. Both answers are correct answers to different questions, so
all three are reported by name and the headline range is their minimum and
maximum. The dashboard flags any supplier whose readings do not nest.

### Multi-hop provenance

Funding that reaches a lab through an intermediary is traced back with a damped
Leontief series:

```
P = sum over k of d_k * S^k,   d_1 = 1,   d_k = alpha^(k-1) for k >= 2
```

where `S[i, j]` is i's share of j's documented external funding. The direct term
carries full weight because a directly documented edge is the strongest evidence
available; each additional intermediary is discounted by `alpha`, default 0.85.
Damping also guarantees convergence, which matters because the funding graph
contains genuine cycles and the undamped inverse is not guaranteed to exist. The
series is truncated at six hops and the truncation residual is reported.

An early implementation added the direct term twice, inflating a direct edge by
roughly 1.85x. It was caught by a toy graph whose answer is 50% by hand, fixed,
and logged in `DECISIONS.md`.

## Why bounds rather than a number

The denominator is unknowable. OpenAI, Anthropic and xAI file nothing, so their
total external funding is only ever a documented subset. A point estimate of
"i's share of j's funding" would silently assume the documented subset is the
whole, which inflates every supplier's share.

This is not theoretical. Recording Anthropic's Series G and Series H rounds
under an aggregate non-supplier node moved the ecosystem CENTRAL figure from
3.1% to 1.7%, because before that Anthropic's only recorded funders were the
companies selling it compute.

## The attribution-coverage figure

Reported next to the headline, and the single most important caveat. It is the
backlog-weighted share of the universe that any filing ties to a named customer.
A round-trip share computed over the attributable fifth would be read as though
it described the whole.

## Stress test

A funding shock to buyer `j` scales its ability to honour commitments by
`1 - passthrough * shock`. Sellers lose the committed demand of impaired buyers.
A seller that loses revenue reduces its own outbound funding in proportion to
`capacity_to_invest` times its loss rate, which re-shocks the buyers it was
financing. The loop iterates to a fixed point.

Cross-checked against two independent methods:

* **Eisenberg-Noe** proportional clearing, treating commitments as obligations
  and documented external funding as resources.
* **DebtRank**, with commitment exposure as the impact weight.

Eisenberg-Noe is reported net of its own no-shock baseline. That baseline is
11.4%: unshocked, committed purchases in this network already exceed documented
external funding. That level is a finding in itself, and comparing raw
Eisenberg-Noe numbers against the cascade would misread it as shock propagation.

A 20,000-draw Monte Carlo varies pass-through, capacity to invest, LOI weight,
conditional-tranche weight and the attribution bound. A tornado chart swings each
parameter across its configured range one at a time. The widest swing is larger
than half the base result, so the report states plainly that the stress answer is
driven as much by assumptions as by data.

## What this cannot tell you

* Whether any backlog figure is realistic. This measures who financed the buyer,
  not whether the buyer will pay.
* Anything about the roughly four fifths of disclosed backlog that names no
  customer.
* Anything quantitative about instruments disclosed without a dollar figure.
  Five ledger edges are recorded at zero dollars because no party disclosed an
  amount, including AMD's warrants to OpenAI and Meta and the Broadcom gigawatt
  agreements.
* Anything about private companies beyond what a counterparty or the company
  itself has published.
* Whether any of this is good or bad for any security. There are no price
  targets and no recommendations here.

## What would change the answer most

1. Oracle or Broadcom naming a customer and a dollar split. Together they hold
   $843 billion of entirely unattributed backlog, which is more than any
   parameter in the model.
2. An OpenAI or Anthropic S-1 with a real funding table, replacing the
   documented-subset denominator.
3. The Nvidia and OpenAI letter of intent converting to a signed, sized
   investment. It is the largest single row in the ledger and it is non-binding.
