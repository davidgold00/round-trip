import json
from types import SimpleNamespace

import pytest

from deal_agent.config import ROOT
from deal_agent.evaluate import evaluate, score
from deal_agent.fetch import (
    HTTP,
    exhibit_urls,
    feed_entries,
    fetch,
    filing_rows,
    text_of,
)
from deal_agent.provider import Ollama


def test_exhibit_type_not_filename_guessing():
    raw = (ROOT / "tests/fixtures/deal_agent/filing-index.html").read_bytes()
    assert exhibit_urls(
        raw, "https://www.sec.gov/Archives/edgar/data/1/acc/acc-index.html"
    ) == ["https://www.sec.gov/Archives/edgar/data/1/acc/release.htm"]
    assert (
        text_of(b"<div>hello</div><p>there</p><script>bad()</script>") == "hello there"
    )


def test_recent_and_historical_submissions_are_filtered():
    data = {
        "accessionNumber": ["one", "two", "old"],
        "filingDate": ["2025-01-02", "2025-01-03", "2024-01-01"],
        "form": ["8-K", "4", "10-Q"],
        "primaryDocument": ["one.htm", "two.htm", "old.htm"],
    }
    assert [
        r["accession_no"]
        for r in filing_rows({"filings": {"recent": data}}, "2025-01-01")
    ] == ["one"]
    assert [r["accession_no"] for r in filing_rows(data, "2025-01-01")] == ["one"]


def test_rss_atom_and_missing_date_preserved():
    rss = b"<rss><channel><item><title>Deal</title><link>/release</link><pubDate>Mon, 22 Sep 2025 10:00:00 GMT</pubDate></item></channel></rss>"
    assert (
        feed_entries(rss, "https://company.test/feed")[0]["published_date"]
        == "2025-09-22"
    )
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>X</title><link rel="alternate" href="https://company.test/x"/><updated>unknown</updated></entry></feed>'
    assert feed_entries(atom, "https://company.test/feed")[0]["published_date"] == ""


def test_fetch_jobs_are_idempotent_and_failed_jobs_survive_cursor(runtime, deal_dict):
    cfg, store, trace, factory = runtime
    pipe = factory()
    cfg["deal_agent"]["watchlist"] = ["Nvidia"]
    cfg["deal_agent"]["initial_since"] = "2025-01-01"
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-25-000001"],
                "filingDate": ["2025-09-22"],
                "form": ["8-K"],
                "primaryDocument": ["main.htm"],
            },
            "files": [],
        }
    }
    index = b'<table class="tableFile"><tr><td>2</td><td>Release</td><td><a href="ex.htm">ex.htm</a></td><td>EX-99.1</td></tr></table>'

    class FakeHTTP:
        fail = True

        def __init__(self):
            self.calls = []

        def get(self, url):
            self.calls.append(url)
            if "submissions" in url:
                return json.dumps(submissions).encode()
            if "-index.html" in url:
                return index
            if url.endswith("main.htm") and self.fail:
                raise OSError("transient")
            return (
                deal_dict["evidence_quote"]
                + (" Exhibit" if url.endswith("ex.htm") else "")
            ).encode()

    http = FakeHTTP()
    first = fetch(cfg, store, trace, pipe.resolver, http=http)
    assert first["docs_fetched"] == 1 and first["fetch_errors"] == 1
    assert store.rows("SELECT * FROM jobs WHERE done=0")
    http.fail = False
    second = fetch(cfg, store, trace, pipe.resolver, http=http)
    assert second["docs_fetched"] == 1
    assert not store.rows("SELECT * FROM jobs WHERE done=0")
    http.calls.clear()
    assert fetch(cfg, store, trace, pipe.resolver, http=http)["docs_fetched"] == 0
    assert all("submissions" in url for url in http.calls)


def test_sec_user_agent_guard_happens_before_http(runtime, monkeypatch):
    cfg, _, trace, _ = runtime
    monkeypatch.setenv("SEC_USER_AGENT", "")
    http = HTTP(cfg, trace)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        http.get("https://data.sec.gov/submissions/CIK1.json")


def test_sec_every_attempt_gets_contact_and_delay(runtime, monkeypatch):
    cfg, _, trace, _ = runtime
    monkeypatch.setenv("SEC_USER_AGENT", "Test Fixture test@fixture.invalid")
    waits = []
    monkeypatch.setattr(
        "deal_agent.fetch.time.sleep", lambda delay: waits.append(delay)
    )
    http = HTTP(cfg, trace)
    attempts = []
    http.limiter.acquire = lambda: attempts.append("limit")

    def fake_get(url, **kwargs):
        attempts.append(kwargs["headers"]["User-Agent"])
        return SimpleNamespace(
            status_code=429 if len(attempts) == 2 else 200,
            content=b"source",
            headers={},
            is_redirect=False,
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(http.session, "get", fake_get)
    assert http.get("https://www.sec.gov/x") == b"source"
    assert attempts == ["limit", "Test Fixture test@fixture.invalid"] * 2
    assert waits and waits[0] >= 1


def test_ollama_uses_schema_loopback_and_traces_request(runtime, monkeypatch):
    cfg, _, trace, _ = runtime
    trace.model = cfg["deal_agent"]["model"]
    provider = Ollama(cfg["deal_agent"], trace)

    def post(url, **kwargs):
        assert url.startswith("http://127.0.0.1:")
        assert kwargs["json"]["stream"] is False
        assert kwargs["json"]["format"] == {"type": "object"}
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"done": True, "response": '{"edges":[]}'},
        )

    monkeypatch.setattr(provider.session, "post", post)
    assert (
        provider.generate("Untrusted text", {"type": "object"}, "extract")
        == '{"edges":[]}'
    )
    event = json.loads(trace.path.read_text().splitlines()[-1])
    assert event["kind"] == "llm" and event["model"] == cfg["deal_agent"]["model"]


def test_eval_metrics_penalise_false_positive_and_missing_amount(runtime, deal_dict):
    resolver = runtime[3]().resolver
    predictions = [
        {"deal": {**deal_dict, "amount_usd": None}, "verification": {"passed": True}}
    ] * 2
    records = [
        {
            "gold_relevant": True,
            "triaged_in": True,
            "expected": [deal_dict],
            "predicted": predictions,
        }
    ]
    result = score(records, resolver)
    assert result["edge_precision"] == 0.5 and result["edge_recall"] == 1
    assert result["amount_accuracy"] == 0 and result["numeric_amount_accuracy"] == 0


def test_gold_labels_validate_without_network_or_llm(runtime, tmp_path):
    pipeline = runtime[3]()
    report = evaluate(
        pipeline, ROOT / "eval/gold", tmp_path / "gold.md", validate_only=True
    )
    assert report["positives"] >= 10 and report["negatives"] >= 5
    assert report["label_failures"] == []
    assert report["metrics"] is None and not pipeline.provider.calls


def test_failed_eval_cannot_claim_metrics_or_enqueue(runtime, tmp_path):
    cfg, store, _, factory = runtime
    pipe = factory([RuntimeError("model offline")] * 50)
    report = evaluate(pipe, ROOT / "eval/gold", tmp_path / "failed.md")
    assert report["status"] == "incomplete"
    assert report["metrics"] is None
    assert not store.candidates()
    assert "Not measured" in (tmp_path / "failed.md").read_text()


def test_publication_refuses_a_graph_the_existing_dashboard_does_not_read(runtime):
    from deal_agent.__main__ import publish

    cfg, _, trace, _ = runtime
    cfg["deal_agent"]["graph_file"] = "experiments/alternative.csv"
    with pytest.raises(RuntimeError, match="existing project layout"):
        publish(cfg, trace)
