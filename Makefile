PY := python3
.DEFAULT_GOAL := help

.PHONY: help setup ingest extract build stress news refresh test serve audit clean

help:
	@echo "Round-Trip AI targets:"
	@echo "  make setup    install python deps"
	@echo "  make ingest   pull SEC submissions + XBRL companyfacts + filing text (cached)"
	@echo "  make extract  regenerate ledger/candidates.csv from cached filing text"
	@echo "  make build    compute exposure metrics -> outputs/ + site/data/"
	@echo "  make stress   run cascade stress test + monte carlo -> outputs/"
	@echo "  make news     pull EDGAR atom / GDELT / RSS, tag, dedupe"
	@echo "  make refresh  ingest + extract + news + build + stress + site data + snapshot + changelog"
	@echo "  make test     run the test suite"
	@echo "  make audit    re-verify a random sample of 20 ledger edges"
	@echo "  make serve    serve the static dashboard at http://localhost:8765"

setup:
	$(PY) -m pip install -r requirements.txt

ingest:
	$(PY) -m src.ingest

extract:
	$(PY) -m src.extract

build:
	$(PY) -m src.metrics

stress:
	$(PY) -m src.stress

news:
	$(PY) -m src.news

refresh:
	$(PY) -m src.refresh

test:
	$(PY) -m pytest tests/ -q

audit:
	$(PY) -m src.audit

serve:
	@echo "Dashboard at http://localhost:8765  (ctrl-c to stop)"
	@cd site && $(PY) -m http.server 8765

clean:
	rm -rf data/interim/* data/processed/* outputs/*.json site/data/*.json

# Optional local semantic extractor. Publication still requires human review.
.PHONY: agent agent-review agent-eval
agent:
	$(PY) -m deal_agent run

agent-review:
	$(PY) -m deal_agent review

agent-eval:
	$(PY) -m deal_agent eval

.PHONY: agent-bench
agent-bench:
	$(PY) -m deal_agent bench $(AGENT_BENCH_ARGS)
