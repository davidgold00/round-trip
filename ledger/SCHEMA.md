# Ledger schema

Two versioned tables plus an append-only snapshot history.

## `ledger/edges.csv`

One row per directed edge. One observation per row: if a deal was announced and
then signed, that is two rows with different `as_of_date` and `status`, not an
edited row.

| column | type | meaning |
|---|---|---|
| `edge_id` | string | stable slug, `source__target__type__YYYYMMDD` |
| `as_of_date` | ISO date | date the evidence is dated (filing or release date) |
| `source_node` | string | canonical node name, the payer or funder |
| `target_node` | string | canonical node name, the recipient or seller |
| `edge_type` | enum | see below |
| `amount_usd_low` | float | lower end of disclosed amount, USD. Equals high if a single figure |
| `amount_usd_high` | float | upper end of disclosed amount, USD |
| `amount_basis` | enum | `notional`, `per-year`, `cumulative`, `RPO` |
| `term_start` | ISO date or blank | contract or investment start |
| `term_end` | ISO date or blank | contract or investment end |
| `status` | enum | `definitive`, `conditional`, `LOI_nonbinding`, `announced`, `reported` |
| `conditions_text` | string | short description of what the money is contingent on |
| `evidence_tier` | enum | `T1`, `T2`, `T3`, `T4` |
| `source_url` | url | direct link to the document |
| `accession_no` | string or blank | SEC accession number when `evidence_tier == T1` |
| `quote_snippet` | string | verbatim supporting quote, under 25 words |
| `notes` | string | analyst note, including flags such as `aggregate_only` |

### `edge_type` values and direction

Money-flow convention: the arrow starts at the party that pays or commits.

Funding family (funder -> recipient):
`equity_investment`, `convertible_or_debt`, `loan_or_guarantee`, `warrants`,
`vendor_financing`.

Demand family (buyer -> seller):
`purchase_commitment`, `cloud_capacity_contract`, `lease`, `offtake_or_rpo`.

A round trip is therefore a 2-cycle: `i -> j` in the funding family and
`j -> i` in the demand family.

## `ledger/backlog.csv`

Supplier-level denominators. Node attribute, not an edge.

| column | type | meaning |
|---|---|---|
| `node` | string | canonical node name |
| `as_of_date` | ISO date | period end of the figure |
| `metric` | string | `rpo`, `contracted_backlog`, `revenue_ttm` |
| `amount_usd_low` | float | lower end |
| `amount_usd_high` | float | upper end |
| `evidence_tier` | enum | `T1`..`T4` |
| `source_url` | url | link |
| `accession_no` | string | SEC accession where applicable |
| `quote_snippet` | string | supporting quote, under 25 words |
| `notes` | string | e.g. XBRL tag used |

## `ledger/nodes.csv`

| column | meaning |
|---|---|
| `node` | canonical name |
| `cik` | zero-padded SEC CIK, blank for non-filers |
| `ticker` | primary ticker, blank for non-filers |
| `is_filer` | `true` / `false` |
| `role` | `supplier`, `buyer`, `investor`, `both` |
| `discovered_via` | why this node is in the graph |

## `ledger/candidates.csv`

Machine-extracted candidate edges awaiting human review. Same columns as
`edges.csv` plus `candidate_id`, `extracted_amount_text`, `context_window`,
`rule_hit`, `review_status` (`pending`, `promoted`, `rejected`),
`review_reason`. Nothing in this file counts toward any metric. Promotion is
only via `python -m src.review`.

## `ledger/snapshots/`

`edges_YYYYMMDD.csv` plus `metrics_YYYYMMDD.json` written by `make refresh`.
These are the vintage history that drives the dashboard's trend panel.
