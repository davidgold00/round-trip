# DECISIONS.md

Decision log for "Round-Trip AI: Who Is Financing Their Own Customers?"

Every ambiguity resolved without asking the user is recorded here with a one-line
rationale. Entries are append-only. Metric definitions in Part A are
pre-registered: they were written before any number was computed, and they are
changed only by a dated amendment entry in Part C that explains why.

Pre-registration timestamp: 2026-10-05 (repository initialisation, Phase 0,
before any ingestion or computation).

---

## Part A. Pre-registered metric definitions

These definitions are frozen. Implementation lives in `src/metrics.py` and is
tested against toy graphs in `tests/test_metrics.py`.

### A.0 Notation

* Nodes are companies. `i` indexes suppliers (sellers of compute, chips, or
  cloud capacity). `j` indexes counterparties (buyers, usually AI labs or
  neoclouds). A node can be both.
* Edges are directed and carry a dollar range `[low, high]`, a basis, a status,
  and an evidence tier.
* **Direction convention (money-flow):** an edge points from the party that pays
  or commits the money to the party that receives it.
  * `equity_investment`, `convertible_or_debt`, `loan_or_guarantee`, `warrants`,
    `vendor_financing`: funder -> recipient.
  * `purchase_commitment`, `cloud_capacity_contract`, `lease`, `offtake_or_rpo`:
    buyer -> seller. The buyer is the payer, so the arrow starts at the buyer.
  * Consequence: a round trip appears as a 2-cycle, `i -> j` (funding) and
    `j -> i` (purchase). This is asserted in `tests/test_direction.py`.
* Two edge families are derived from the above and used separately by the
  metrics:
  * **Funding edges** F-family: `equity_investment`, `convertible_or_debt`,
    `loan_or_guarantee`, `warrants`, `vendor_financing`.
  * **Demand edges** D-family: `purchase_commitment`, `cloud_capacity_contract`,
    `offtake_or_rpo`, `lease`.

### A.1 Status weighting

Each edge is multiplied by a status weight `w(status)` before entering any
metric. Defaults, exposed in `config.yaml` and varied in sensitivity analysis:

| status | low | central | high | rationale |
|---|---|---|---|---|
| `definitive` | 1.00 | 1.00 | 1.00 | signed and binding |
| `conditional` | 0.25 | 0.50 | 0.80 | tranches gated on milestones or deployment |
| `LOI_nonbinding` | 0.05 | 0.25 | 0.60 | letters of intent frequently resize or lapse |
| `announced` | 0.30 | 0.60 | 0.90 | announced by a party but binding terms not disclosed |
| `reported` | 0.00 | 0.25 | 0.60 | third party report only; excluded from headline by tier rule anyway |

The LOWER bound of the headline metric uses the `low` column, CENTRAL uses
`central`, UPPER uses `high`.

### A.2 Evidence tier gate

* T1 = SEC filing (10-K, 10-Q, 8-K, S-1, proxy, exhibits).
* T2 = company press release or investor relations page.
* T3 = reputable media report.
* T4 = unverified or rumor.

The **headline metric admits T1 and T2 only**. T3 is computed in a separately
labelled sensitivity view. T4 is never counted anywhere. Enforced by
`src/metrics.py::filter_tiers` and asserted in `tests/test_tiers.py`.

### A.3 Amount normalisation to an annual comparable basis

Edges carry `amount_basis` in {`notional`, `per-year`, `cumulative`, `RPO`}.
Metrics operate on a single comparable basis, chosen as **total contract value
(TCV)**, because disclosed RPO and announced deal headlines are both
multi-year totals and comparing a per-year figure against them would understate
demand edges.

* `notional`, `cumulative`, `RPO`: used as given.
* `per-year`: multiplied by the contract term in years, where
  `term_years = max(1, (term_end - term_start) / 365.25)`. If the term is
  unknown, `per-year` amounts are multiplied by the config default
  `assumed_term_years` (default 5, sensitivity 3 to 8) and the row is flagged
  `term_assumed`.

### A.4 Backlog dependency matrix D

For supplier `i` and counterparty `j`:

```
D[i, j] = weighted_demand_edges(j -> i) / disclosed_backlog(i)
```

* Numerator: sum over D-family edges from `j` to `i` of
  `w(status) * amount`, on the TCV basis of A.3.
* Denominator `disclosed_backlog(i)`: the supplier's own disclosed backlog
  measure, in strict preference order, taken only from that supplier's filings
  or releases:
  1. XBRL `RevenueRemainingPerformanceObligation` (latest period), else
  2. a stated contracted-backlog or RPO figure quoted from a filing or release,
     recorded in `ledger/backlog.csv`, else
  3. the sum of that supplier's own inbound D-family edges in the ledger. This
     case is flagged `backlog_from_edges` and the supplier's row is marked
     low-confidence, because the denominator is then composed of the same
     observations as the numerator and the share is mechanically inflated.
* If the numerator for a named customer is only available as an aggregate (for
  example "two customers accounted for 77% of revenue"), the row is recorded as
  a **bounded range** `[0, aggregate]` per unnamed member and flagged
  `aggregate_only`. No point estimate is produced from an aggregate.
* `D[i, j]` is clipped to `[0, 1]`. Sum over `j` of `D[i, j]` may exceed 1 only
  when the ledger records more committed demand than the supplier discloses as
  backlog; this is surfaced as a data-quality warning, not silently rescaled.

### A.5 Funding provenance matrix F and the three bounds

For counterparty `j`, `documented_external_funding(j)` is the sum of
`w(status) * amount` over all F-family edges pointing into `j` in the ledger.
This is a **documented** total, not `j`'s true total funding, and for private
companies it is certainly an undercount. That undercount is the reason the
CENTRAL estimate is bracketed rather than reported alone.

Three provenance measures, all in `[0, 1]`:

```
Provenance_LOWER(i -> j)   = min(1, funding(i -> j) / commitment(j -> i))
Provenance_CENTRAL(i -> j) = funding(i -> j) / documented_external_funding(j)
Provenance_UPPER(i -> j)   = 1 if funding(i -> j) > 0 else 0
```

* LOWER answers "what fraction of what j promised to pay i did i itself
  demonstrably hand to j?" It is the conservative reading: only dollars with a
  documented path from i to j count, and they are capped at the size of the
  commitment. If `commitment(j -> i)` is zero the term is zero.
* CENTRAL is pro-rata attribution: i's share of j's documented external funding.
  It is the headline number.
* UPPER is the maximal reading: if i funded j at all under T1 or T2 evidence,
  the whole of j's commitment to i is treated as funding-dependent. It answers
  "how much backlog sits with customers who are not funding-independent of the
  seller?"

### A.6 Multi-hop provenance

Direct F alone misses funding that reaches `j` through an intermediary (for
example supplier -> neocloud -> lab, or supplier -> SPV -> lab). Let `S` be the
column-stochastic share matrix with `S[i, j] = ` i's share of j's documented
external funding (the CENTRAL direct measure). Ultimate provenance is the
absorbing-random-walk / Leontief solution:

```
P = S (I - S)^-1  equivalently  P = sum_{k>=1} S^k
```

computed as `P = S @ inv(I - S)` when the spectral radius of `S` is below 1, and
otherwise by truncated Neumann series with damping (see below).

* Cycles are real here (a lab funds nothing upstream, but a supplier funds a
  neocloud which funds a lab which buys from the supplier, and chip vendors
  also invest in each other's customers), so `S` can have a spectral radius at
  or above 1. Treatment: a damping factor `alpha` (default 0.85, config
  `multihop.alpha`) is applied, `S_d = alpha * S`, guaranteeing convergence, and
  the series is truncated at `max_hops` (default 6) with the residual reported.
  Damping is documented as an assumption, not a modelling nicety: it means
  funding traced through more than a few intermediaries is discounted.
* `Provenance_multihop(i -> j) = min(1, P[i, j])`, used only in the CENTRAL and
  UPPER views. LOWER stays strictly direct, by design, because a multi-hop path
  is weaker evidence than a direct one.
* Convergence (residual of the truncated series) is reported in
  `outputs/metrics.json` and shown on the methodology page.

### A.7 Headline metric: Round-Trip Exposure

For supplier `i`, for each bound `b` in {LOWER, CENTRAL, UPPER}:

```
RTE_b(i) = sum_j  D_b[i, j] * Provenance_b(i -> j)
```

reported as a percentage of supplier `i`'s disclosed backlog. The
ecosystem-level total is the backlog-weighted mean:

```
RTE_b(ecosystem) = sum_i backlog(i) * RTE_b(i) / sum_i backlog(i)
```

Headline sentence template, fixed now so results cannot reshape the framing:

> "Roughly X% (range L to U) of disclosed backlog depends on a counterparty
> whose funding traces back to the seller."

### A.8 Structure analysis

* Strongly connected components on the combined (F plus D) directed graph.
* Simple cycles via Johnson's algorithm (`networkx.simple_cycles`), capped at
  length `max_cycle_len` (default 6) to keep enumeration finite and readable.
* **Cycle bottleneck** = the minimum weighted edge amount along the cycle, using
  the CENTRAL status weights and the TCV basis. It is the most dollars that can
  actually circulate around that loop, since the loop is only as wide as its
  narrowest leg.
* PageRank on the funding subgraph (F-family) with weights = CENTRAL amounts,
  and betweenness centrality on the combined graph, to identify nodes the
  structure depends on.

### A.9 Stress test (Phase 3) pre-registration

* Shock: node `j`'s new external funding falls by `x%`, or a named tranche fails.
* Propagation: `j`'s ability to honour commitments scales by
  `1 - passthrough * x`, where `passthrough` in [0, 1] (default 0.6) is the
  fraction of a funding shortfall that converts into reduced purchasing rather
  than being absorbed by cash on hand, slower deployment, or substitute
  financing.
* Second round: supplier `i` loses demand, and `i`'s own outbound funding and
  purchases shrink by `capacity_to_invest * (revenue loss / revenue)`, default
  `capacity_to_invest = 0.5`. Iterate to a fixed point, tolerance 1e-9, cap 200
  iterations, report the iteration count and residual.
* Monte Carlo (default 20,000 draws) over `passthrough`, LOI conversion
  probability, conditional-tranche realisation, and the attribution bound
  (LOWER/CENTRAL/UPPER sampled as a discrete mixture). Report median and the
  10th to 90th percentile band of "share of each supplier's backlog at risk".
* Cross-validation against a second method, Eisenberg-Noe clearing with
  commitments treated as obligations, plus DebtRank. Disagreements are reported,
  not reconciled away.

---

## Part B. Decision log

Format: `[date] [phase] decision -- rationale`

* `2026-10-05 P0` **SEC_USER_AGENT read from `.env` rather than the shell.** The
  variable was absent from the environment but present in `.env`. Treated as set
  because the user supplied it in the project; `src/sec_client.py` loads `.env`
  itself and still hard-fails if the value is missing or looks like a
  placeholder. -- Honours the stop condition's intent without a spurious halt.
* `2026-10-05 P0` **Ledger stored as CSV, not YAML.** CSV diffs row-by-row in
  git, loads directly into pandas, and is editable by a reviewer without a YAML
  parser. -- Reviewability is the binding constraint, and the schema is flat.
* `2026-10-05 P0` **Amounts stored as a `[low, high]` pair on every row, never a
  single point.** A single disclosed figure is stored as `low == high`. -- Makes
  ranges the default representation so a point estimate can never leak into the
  headline by accident.
* `2026-10-05 P0` **TCV chosen as the common basis** rather than annualised
  run-rate. -- Announced deal headlines and disclosed RPO are both multi-year
  totals; annualising would require inventing term lengths for both sides.
* `2026-10-05 P0` **`sentence-transformers` is not installed in this
  environment, so news tagging uses the TF-IDF plus keyword-rule path.** The
  embedding path is implemented and selected automatically if the package and
  model are present. -- The task requires a working free pipeline, and the
  fallback was specified for exactly this case.
* `2026-10-05 P0` **Separate `ledger/backlog.csv` for supplier denominators.**
  Backlog is a node attribute, not an edge, and forcing it into the edge table
  would require self-edges. -- Keeps the edge schema honest and the denominator
  independently auditable.
* `2026-10-05 P0` **Damping `alpha = 0.85` for multi-hop provenance.** The
  funding graph contains genuine cycles, so the Leontief inverse is not
  guaranteed to exist. -- Standard PageRank-style regularisation, and discounting
  long funding chains is substantively correct, not just numerically convenient.
* `2026-10-05 P1` **Private-company nodes carry no filings and are never
  assigned a point estimate.** Every metric touching OpenAI, Anthropic, xAI, or
  any other non-filer is produced as a range, and the dashboard labels them.
  -- Required by honesty rule 4.
* `2026-10-05 P1` **Candidate extraction never auto-promotes.**
  `src/extract.py` writes only to `ledger/candidates.csv`; promotion requires
  `python -m src.review` and the recording of a quote. -- Required by the brief;
  also enforced by `tests/test_no_autopromote.py`.
* `2026-10-05 P2` **`D[i,j]` is clipped at 1 but row sums are not rescaled.** If
  ledger demand exceeds disclosed backlog, that is a finding about disclosure,
  not an error to normalise away. -- Rescaling would hide the most interesting
  data-quality signal in the dataset.
* `2026-10-05 P1` **Discovered node `Nscale` added with its CIK taken from the
  EDGAR archive path of its S-1 rather than from `company_tickers.json`.** It has
  filed but is not yet listed, so the ticker file cannot resolve it. -- The CIK
  still comes from SEC data, which is what the no-memory rule requires.
* `2026-10-05 P1` **Nvidia's and AMD's tagged `RevenueRemainingPerformanceObligation`
  is recorded in `ledger/backlog.csv` under the metric name `rpo_software_only`,
  which is deliberately outside the denominator preference list.** Both sell data
  centre systems on purchase orders and disclose no product backlog; their tagged
  RPO covers software and services ($3.2bn and $222m). Using it as a denominator
  would produce a nonsense share. -- Visible and auditable in the ledger, but never
  used as a denominator.
* `2026-10-05 P2` **Clarification, not an amendment: bound-correct denominators.**
  A LOWER bound on a share is the smallest numerator over the LARGEST denominator,
  so the `low` bound divides by `backlog_high` and the `high` bound divides by
  `backlog_low`. This is what DECISIONS A.4's own wording implies; the code now
  states it explicitly. -- Caught during implementation, before any result was read.
* `2026-10-05 P2` **UPPER provenance is defined on funding LINKS, not funding
  dollars.** The AMD warrants issued to OpenAI and Meta are share-denominated with
  no disclosed dollar value, so they are recorded at zero dollars. A dollar test
  would make them invisible even to the maximal bound. -- A.5 already defines UPPER
  as "i has any T1/T2 funding link to j"; `link_matrix` implements that literally.
* `2026-10-05 P2` **Supplier universe includes every node with a disclosed backlog
  figure, even with no named customer.** Oracle discloses $664bn of RPO and names
  no customer anywhere in its filings. Dropping it would shrink the ecosystem
  denominator and inflate the headline. -- Its Round-Trip Exposure is reported as
  zero *measurable*, not zero.
* `2026-10-05 P2` **Added a clearly-labelled SECONDARY metric,
  `network_financed_share`, alongside the pre-registered headline.** The headline
  asks "is the seller financing its own buyer?" and is zero for CoreWeave, Nebius
  and Nscale by construction, because they finance nobody. The secondary metric
  asks "is the buyer financed by somebody with compute to sell?" and is 27% to 87%
  for those three. -- An addition, not a change: the headline definition in Part A
  is untouched, and the dashboard labels which is which.
* `2026-10-05 P2` **Alphabet is NOT recorded as an Anthropic investor.** Alphabet
  names Anthropic nowhere in any filing retrieved, and no Alphabet or Anthropic
  release found states an Alphabet investment amount. Alphabet's non-marketable
  securities rose from $68.7bn to $131.5bn in the first half of 2026 with no
  attribution. -- Honesty rule 1: background knowledge decides what to look for, it
  never substitutes for evidence. Logged instead as a known gap.
* `2026-10-05 P2` **An attribution-coverage figure is reported next to the
  headline.** 79% of the disclosed backlog in the covered universe cannot be tied
  to any named customer. -- A round-trip share computed over the attributable fifth
  would be read as though it described the whole, so the denominator's blindness is
  reported as a first-class number.
* `2026-10-05 P2` **Multi-hop series double-count fixed, and the direct term is
  left undamped.** The first implementation computed `P = sum_k (alpha S)^k` and
  then added `S` again, so a direct funding edge was counted roughly 1.85 times.
  The series is now `P = sum_k d_k S^k` with `d_1 = 1` and `d_k = alpha^(k-1)` for
  `k >= 2`. -- A.6 never said to add S back; and a directly documented edge is the
  strongest evidence available, so discounting it by alpha would be perverse. Caught
  by the `half_funded` toy graph, whose answer is 50% by hand.
* `2026-10-05 P3` **Eisenberg-Noe is reported against its own no-shock baseline.**
  Unshocked, the clearing model already puts 14.0% of disclosed backlog in
  shortfall, because in this network committed purchases exceed documented
  external funding before any shock. Comparing raw Eisenberg-Noe numbers against
  the cascade would read that standing level as shock propagation. -- The
  disagreement is reported as excess over baseline, and the level itself is
  reported as a finding in its own right.
* `2026-10-05 P3` **"Single tranche fails" is parameterised as the largest
  conditional or LOI funding edge going to zero**, converted into a share of the
  recipient's documented external funding, rather than naming a tranche by hand.
  -- Keeps the scenario reproducible as the ledger changes, instead of hardcoding
  today's largest deal.
* `2026-10-05 P4` **News monitor sources 8-K events from the submissions API, not
  the browse-edgar Atom feed.** The Atom feed titles every entry "8-K - Current
  report"; the submissions API carries the Item codes, so Item 1.01 material
  agreements and Item 2.03 and 3.02 financings can be surfaced by name. The Atom
  feed is still fetched as a freshness probe. -- A financing monitor that cannot
  see which item was reported is not a financing monitor. (An Atom namespace bug
  was also fixed: ElementTree needs the namespace map handed to `find`, and
  without it every Atom title came back empty and the feed looked like zero items.)
* `2026-10-05 P4` **GDELT queries are batched four entities at a time with a six
  second gap.** Fifteen one-per-entity queries were rate limited with HTTP 429.
  -- Free API, so stay well inside its limits rather than hammering it.
* `2026-10-05 P4` **An IR feed's `pubDate` is treated as a crawl date, not an
  evidence date.** The AMD and Anthropic release arrived in the feed stamped
  2026-10-05 but the release itself is dated 2026-07-22, and the ledger records
  the release date. -- The as-of date has to be the date of the evidence.
* `2026-10-05 P5` **Three edge-colour families, not nine edge types.** A network
  graph is an all-pairs colour form, and the validated categorical palette clears
  the all-pairs colour-vision and normal-vision separation floors only for its
  first three slots. Edge types fold into equity and warrants, credit, and
  committed demand; conditionality is carried by a dash pattern rather than a
  fourth hue. Validator run on both the light and dark steps, all checks pass.
  -- Honest colour beats a nine-hue rainbow nobody can distinguish.
* `2026-10-05 P5` **Non-supplier funding of the private labs is recorded under an
  aggregate node, `Financial investors`.** Before this, Anthropic's only recorded
  funders were suppliers, so the CENTRAL denominator contained nothing but
  suppliers and every supplier's share was overstated by construction. Anthropic's
  Series G and Series H releases give round totals but no per-investor amounts, so
  attributing a figure to any individual fund would be invention; the aggregate
  carries the total net of the supplier money the release itself identifies, as a
  range where the release is imprecise. Adding it moved the ecosystem CENTRAL from
  3.1% to 1.7%. -- The denominator's composition is as important as the numerator's,
  and a denominator made only of suppliers guarantees a flattering answer.
* `2026-10-05 P5` **The three readings are reported by name and the headline range
  is their min and max, because they are not guaranteed to nest.** LOWER divides
  i's funding by j's commitment to i; CENTRAL divides it by j's whole documented
  funding. When i funded j heavily relative to that one commitment but j has many
  other funders, LOWER exceeds CENTRAL. Amazon and Anthropic is exactly that case:
  LOWER 5.0% against CENTRAL 4.7%. -- Both answers are correct answers to different
  questions. Forcing an order would have meant discarding one of them. The
  dashboard flags any supplier whose readings are not nested, and
  `tests/test_metrics.py` has a toy graph (A funds B with 10, C funds B with 90,
  B commits 10 to A) whose LOWER is 1.0 and CENTRAL is 0.1 by hand.
* `2026-10-06 P6` **GDELT batching widened to six entities per query with a
  twelve second gap.** Four-entity batches at six seconds still drew HTTP 429 on
  a second run from the same address. The pipeline degrades gracefully, logging
  and continuing, so a throttled GDELT never blocks a refresh. -- Free API, so
  back off rather than retry harder.
* `2026-10-06 P6` **Two self-audit corrections applied, both logged in
  `outputs/audit.md`.** The audit found two backlog rows whose `quote_snippet`
  paraphrased an XBRL tag instead of quoting the filing, which breaks this
  project's own rule; both were replaced with verbatim text. Fetching those
  quotes then exposed a substantive error: AMD's remaining performance
  obligations figure explicitly includes product revenue, so the annotation
  "covers software and services only" was wrong. The metric was renamed
  `rpo_long_term_contracts_only` for both Nvidia and AMD and the notes rewritten.
  The conclusion is unchanged and now rests on the right reason: the figure
  captures only contracts longer than one year, which is not how either company
  sells its data centre products. -- Found by sampling, which is the point of
  sampling.
* `2026-10-06 P6` **IR feeds are clipped to the lookback window and then to a
  hard per-feed cap of 60 items.** OpenAI's newsroom feed returns its entire
  history, over 1,200 entries, which swamped the corpus and the deduplication
  step. -- One verbose publisher should not dominate a monitor built to spot
  financing events.
* `2026-10-06 P6` **News review decisions are keyed by item URL, not by the
  generated candidate id.** The id is a hash of the URL and is stable, but
  rebuilding `ledger/news_candidates.csv` from scratch loses the decision
  history, which happened once during development. The URL is the durable key
  and the file is the review record. -- A rejection with a reason is as much a
  research output as a promotion.
* `2026-10-06 P6` **RSS date parsing extended to two-digit years and several
  other shapes.** AMD's investor feed stamps items `Mon, 28 Sep 26 16:05:00
  -0400`. The parser did not cover `%y`, so every AMD item fell through to the
  "use today" fallback and months-old releases sorted to the top of the
  timeline. `normalise_date` now returns an empty string when it genuinely
  cannot parse, so the caller's fallback is a real fallback rather than a silent
  default. -- Covered by a parametrised test over every date shape these feeds
  actually emit.
* `2026-10-06 P6` **`src/site_data.py` added to the refresh pipeline.** It was
  missing, so a clean `make refresh` wrote the metrics and stress payloads but
  never the ledger payload, and a fresh clone would have served a dashboard that
  could not load its own ledger. -- Now guarded by a test that reads the fetch
  calls out of `site/app.js` and asserts every file they ask for exists.
* `2026-10-06 P6` **Relevance gate tightened for company feeds, and
  `--skip-network` now re-tags the stored corpus.** A corporate blog uses the
  same verbs for community giving as for financing: "5 ways Amazon is investing
  in Connecticut" and "Amazon in the community" both fired the investment rule.
  A release now needs the verb AND either a second entity or a size hint
  (dollars or gigawatts), and an explicit noise pattern excludes citizenship,
  appointments and customer stories. Flagged items fell from 23 to 14 and the
  survivors are dominated by actual Item 1.01, 2.03 and 3.02 8-Ks.
  `--skip-network` re-tags what is already stored instead of doing nothing,
  which is how the rules were tuned without touching a feed. -- A monitor whose
  queue is mostly press-office copy will not get read.
* `2026-10-07 P6` **Mobile layout verified by measurement, not by screenshot.**
  Headless screenshots at a 390px window appeared to clip, which looked like
  horizontal overflow. An in-page probe reports `documentElement.scrollWidth` of
  390 against a 390px viewport, with the only elements past the edge being tab
  buttons inside the deliberately scrollable tab strip. The clipping was a
  headless device-scale artifact. Defensive CSS was kept anyway: `min-width: 0`
  on grid children, `overflow-wrap: anywhere` in cards, a width cap on the page
  wrappers, and a shorter graph at phone width. -- Screenshots show what a
  renderer did; `scrollWidth` says what the layout is.
