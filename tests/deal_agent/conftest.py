import csv
import json
import shutil

import pytest

from deal_agent.config import ROOT, load
from deal_agent.pipeline import Pipeline
from deal_agent.store import Store
from deal_agent.trace import Trace
from src.ledger import EDGE_FIELDS

FIXTURES = ROOT / "tests/fixtures/deal_agent"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Unit tests must never access the network")

    monkeypatch.setattr("requests.sessions.Session.request", refuse)


@pytest.fixture
def deal_dict():
    return json.loads((FIXTURES / "valid_deal.json").read_text())


@pytest.fixture
def runtime(tmp_path):
    cfg = load()
    cfg["_root"] = tmp_path
    cfg["deal_agent"]["legacy_queues"] = []
    (tmp_path / "ledger").mkdir()
    shutil.copy(ROOT / "ledger/nodes.csv", tmp_path / "ledger/nodes.csv")
    with (tmp_path / "ledger/edges.csv").open("w", newline="") as handle:
        csv.DictWriter(handle, fieldnames=EDGE_FIELDS).writeheader()
    store = Store(tmp_path / "queue.sqlite3")
    trace = Trace(tmp_path / "traces", "mock-local")

    def factory(responses=()):
        class MockProvider:
            model = "mock-local"

            def __init__(self):
                self.calls = []
                self.responses = iter(responses)

            def generate(self, prompt, schema, stage):
                self.calls.append((stage, prompt))
                response = next(self.responses)
                if isinstance(response, Exception):
                    raise response
                result = response if isinstance(response, str) else json.dumps(response)
                trace.event(
                    stage, {"prompt": prompt, "schema": schema}, result, kind="llm"
                )
                return result

        provider = MockProvider()
        return Pipeline(cfg, store, trace, provider)

    yield cfg, store, trace, factory
    store.close()
