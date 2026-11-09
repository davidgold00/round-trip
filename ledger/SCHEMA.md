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

## Optional deal-agent columns (backward compatible)

`EDGE_FIELDS` remains the original required 17-column contract for callers.
`AGENT_FIELDS` / `EXTENDED_EDGE_FIELDS` define the optional extension, and the
reader/writer preserve unknown extra columns. Missing optional values load blank.
The committed migration preserves every original field in all 38 rows. It copies
`as_of_date` to `announced_date`, `quote_snippet` to `evidence_quote`, and an exact,
positive low==high figure to `amount_usd`. It leaves ranged/undisclosed scalar
amounts blank, sets consideration to unknown, and invents no deal subtype, term,
model confidence or rationale for manually curated historical rows.

| field | meaning |
|---|---|
| deal_type | Rich extraction enum; see README mapping to legacy edge_type |
| consideration_type | cash / equity / compute_credits / mixed / unknown |
| amount_usd | Extracted explicit USD scalar; CSV blank means null, ranges remain in legacy low/high |
| amount_text | Verbatim amount wording; empty if unstated |
| term_or_duration | Verbatim duration wording, or blank |
| announced_date | Extracted announcement date (ISO) |
| evidence_quote | Continuous verbatim sentence(s) / excerpt from stored source |
| confidence | Local model confidence, 0..1; blank on legacy rows |
| extraction_rationale | One-line source-grounded rationale |
| agent_candidate_id | Links an approved row to the local SQLite queue |
| document_sha256 | SHA-256 of the exact saved text used for verification |

The agent queue is **not** another approved ledger: it lives in local,
gitignored `data/deal_agent/queue.sqlite3`. `documents`, `jobs` and `chunks` hold
content identities, every source's metadata, raw hashes and checkpoints;
`candidates` stores the full extraction plus verification/history/reconciliation;
`issues`, `runs` and `audit` hold failures, counters and human changes.

Only `python -m deal_agent review` may apply an agent candidate. UPDATE requires
an explicit target row and stores its previous contents in an immutable audit
payload before replacement. This is a deliberate exception to the original
append-observation convention: appending a second financial row for a restatement
would double-count it in the current metrics. It does not rewrite old snapshots.
NEW remains a distinct row. `src.review` continues to support the old queues;
do not use the two review programs concurrently on the same ledger.

A reviewer who explicitly chooses a distinct NEW contract on the same day may
produce an edge id with a stable candidate suffix after the usual date slug.
This preserves distinct tranches without changing old ids or double-counting
updates. No consumer should infer contract identity solely from the date slug.
