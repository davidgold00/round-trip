# Agent review and publication

The agent queue stores extraction and verification history. All ledger changes
use the project's existing promotions mechanism. No model writes the ledger.

1. Run `python -m deal_agent review list` and inspect a candidate with
   `python -m deal_agent review show ID`.
2. Run `python -m deal_agent review --actor "David Gold"` for interactive
   edit/reject/approve. Read the original source and choose the publication quote,
   legal status, amount bounds and rationale. Approval exports a YAML and records
   its path in the immutable review audit. It does not change the ledger.
3. Inspect that YAML, then run `python -m src.review batch PATH_PRINTED_BY_REVIEW`.
   This is the original promotion path. It records an application event in
   `ledger/promotion_audit.jsonl`. Keep the reviewed YAML with your promotion
   history and audit; do not edit its guard fields or approved edge.
4. Run `python -m deal_agent publish` to rebuild metrics, stress and dashboard.
   This rebuild uses the reviewed ledger and performs no model extraction.

An approved SQLite status means reviewed/exported, not published. An UPDATE
requires an explicit existing edge id, and the original promotion mechanism
updates that row rather than appending a second copy. Distinct same-day contracts
require an explicit NEW decision and receive stable distinct edge ids.

If the ledger changed before application, batch refuses the stale review.
Use `python -m deal_agent review reopen ID --actor "David Gold" --reason "..."`,
then review the candidate again. A new revision preserves the old YAML and audit.
An applied approval cannot be reopened; a later restatement needs a new reviewed
candidate. Failed verification requires an edit and successful recheck first.
Rich extraction metadata remains in SQLite audit; promotion rows use the original
ledger fields. Existing filing/news queues and promotion files are unchanged.
