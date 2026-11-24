PY := python3
.DEFAULT_GOAL := help

.PHONY: help setup ingest extract build stress news refresh test serve audit clean

help:
	@echo "Run"
	@echo "  demo          replay a real extraction offline in a temporary queue"
	@echo "  serve         serve the bundled dashboard offline on localhost:8765"
	@echo "  refresh       fetch public sources and run the analysis pipeline"
	@echo "  ingest        cache SEC filings and company facts"
	@echo "  extract       regenerate the filing candidate queue"
	@echo "  news          collect and tag EDGAR, company and news items"
	@echo "  build         compute exposure metrics"
	@echo "  stress        compute cascade scenarios and sensitivity"
	@echo "Agent"
	@echo "  agent         use local Ollama to propose deals from stored news or configured feeds"
	@echo "  agent-review  inspect and decide on pending proposals"
	@echo "  explain ID=…  show one candidate's trace and review outcome"
	@echo "Evaluate"
	@echo "  agent-eval    run local inference on development passages"
	@echo "  agent-bench   record a model and prompt comparison on development"
	@echo "  audit         recheck a sample of reviewed sources"
	@echo "Develop"
	@echo "  setup         install the pinned Python dependencies"
	@echo "  test          run the test suite, including refresh parity"
	@echo "  links         check local Markdown links and section anchors"
	@echo "  clean         delete generated interim data and exports"

.PHONY: demo explain links
demo:
	@$(PY) -m deal_agent demo

export ID
explain:
	@test -n "$$ID" || { echo "Usage: make explain ID=<candidate_id>"; exit 2; }
	@$(PY) -m deal_agent explain "$$ID"

links:
	@$(PY) -m pytest -q tests/test_markdown_links.py

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
	@cd site && $(PY) -m http.server 8765 --bind 127.0.0.1

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
