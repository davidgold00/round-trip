# Coverage report

Generated 2026-10-05. Source: SEC EDGAR only.
HTTP cache hits 41, fetches 596, errors 0, total requests 596.

## Filer coverage

| node | SEC name | submissions | companyfacts | XBRL rows | filings listed | docs fetched | docs failed |
|---|---|---|---|---|---|---|---|
| AMD | ADVANCED MICRO DEVICES INC | yes | yes | 1162 | 70 | 70 | 0 |
| Alphabet | Alphabet Inc. | yes | yes | 1099 | 76 | 76 | 0 |
| Amazon | AMAZON COM INC | yes | yes | 1603 | 70 | 70 | 0 |
| Broadcom | Broadcom Inc. | yes | yes | 646 | 67 | 67 | 0 |
| CoreWeave | CoreWeave, Inc. | yes | yes | 136 | 32 | 32 | 0 |
| Meta | Meta Platforms, Inc. | yes | yes | 956 | 33 | 33 | 0 |
| Microsoft | MICROSOFT CORP | yes | yes | 1486 | 53 | 53 | 0 |
| Nebius | Nebius Group N.V. | yes | yes | 135 | 98 | 98 | 0 |
| Nvidia | NVIDIA CORP | yes | yes | 1263 | 59 | 59 | 0 |
| Oracle | ORACLE CORP | yes | yes | 728 | 58 | 58 | 0 |

## XBRL concept-group coverage (observation counts)

| node | rpo | rpo_pct_expected | purchase_obligations | related_party | concentration | capex | leases_not_commenced | debt | cash | revenue | nonmarketable_investments |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AMD | 34 | 0 | 16 | 183 | 0 | 146 | 11 | 137 | 447 | 136 | 52 |
| Alphabet | 27 | 0 | 22 | 81 | 0 | 122 | 18 | 110 | 303 | 164 | 252 |
| Amazon | 10 | 0 | 80 | 15 | 0 | 304 | 55 | 348 | 604 | 128 | 59 |
| Broadcom | 22 | 0 | 44 | 23 | 0 | 79 | 9 | 150 | 172 | 147 | 0 |
| CoreWeave | 6 | 0 | 0 | 4 | 0 | 13 | 6 | 30 | 50 | 19 | 8 |
| Meta | 0 | 0 | 49 | 38 | 0 | 128 | 25 | 58 | 414 | 196 | 48 |
| Microsoft | 37 | 2 | 0 | 16 | 0 | 230 | 37 | 457 | 476 | 165 | 66 |
| Nebius | 1 | 0 | 0 | 7 | 0 | 19 | 7 | 12 | 55 | 24 | 10 |
| Nvidia | 31 | 3 | 20 | 0 | 0 | 90 | 30 | 220 | 471 | 308 | 90 |
| Oracle | 33 | 11 | 17 | 0 | 0 | 137 | 12 | 44 | 213 | 247 | 14 |

## Non-filers (no SEC data exists for these)

These entities do not file periodic reports with the SEC. Every figure
touching them in this project comes from a counterparty's filing or a
company press release, and is reported as a range:

* OpenAI
* Anthropic
* xAI
* SoftBank

## Known gaps

* AMD: no `concentration` XBRL observations found
* Alphabet: no `concentration` XBRL observations found
* Amazon: no `concentration` XBRL observations found
* Broadcom: no `concentration` XBRL observations found
* CoreWeave: no `purchase_obligations` XBRL observations found
* CoreWeave: no `concentration` XBRL observations found
* Meta: no `rpo` XBRL observations found
* Meta: no `concentration` XBRL observations found
* Microsoft: no `purchase_obligations` XBRL observations found
* Microsoft: no `concentration` XBRL observations found
* Nebius: no `purchase_obligations` XBRL observations found
* Nebius: no `concentration` XBRL observations found
* Nvidia: no `related_party` XBRL observations found
* Nvidia: no `concentration` XBRL observations found
* Oracle: no `related_party` XBRL observations found
* Oracle: no `concentration` XBRL observations found

Gaps are expected and meaningful. Not every filer tags remaining
performance obligations in XBRL, and customer concentration is often
narrative text rather than a tagged fact. Narrative disclosures are
picked up by the candidate extractor instead.
