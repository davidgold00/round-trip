# STATE.md

Resume file. A new session should read this first, then DECISIONS.md.

**Last updated:** 2026-10-05, end of Phase 0.

## Done
* Phase 0 complete. Repo layout, `config.yaml`, `Makefile`, `.gitignore`,
  `ledger/SCHEMA.md`, pre-registered metric definitions in `DECISIONS.md` Part A,
  `src/util.py`, `src/sec_client.py` (rate limiter verified at 5 req/s, disk
  cache, retries with exponential backoff, hard fail on missing SEC_USER_AGENT).

## Next
* Phase 1: `src/ingest.py` (CIK resolution, submissions, companyfacts, filing
  text), `src/extract.py` (rule and regex candidate extractor), coverage report.

## Known issues
* `sentence-transformers` is not installed, so news tagging will run on the
  TF-IDF plus keyword path. Logged in DECISIONS.md.
* `SEC_USER_AGENT` lives in `.env`, which is gitignored. A fresh clone must
  recreate it before `make ingest`.
