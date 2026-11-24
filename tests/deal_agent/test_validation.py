import json
from decimal import Decimal

import pytest

from deal_agent.entities import Resolver
from deal_agent.models import Deal, Extraction, parse_json
from deal_agent.verify import dollars, verify


def test_aliases_resolve_without_fuzzy_inventions(runtime):
    pipeline = runtime[3]()
    resolver = pipeline.resolver
    for alias in ("Microsoft Corporation", "MSFT", " Microsoft "):
        assert resolver.resolve(alias) == "Microsoft"
    assert resolver.resolve("Google Cloud") == "Alphabet"
    assert resolver.resolve("Microsoftish") is None
    assert resolver.mentioned("AMZN will invest in Anthropic; xAI is unrelated") == {
        "Amazon",
        "Anthropic",
        "xAI",
    }
    assert resolver.mentioned("metaphor and amznish") == set()


def test_ambiguous_alias_is_configuration_error():
    with pytest.raises(ValueError, match="ambiguous"):
        Resolver([{"node": "A"}, {"node": "B"}], {"A": ["same"], "B": ["same"]})


@pytest.mark.parametrize(
    "bad",
    [
        {"deal_type": "investment"},
        {"consideration_type": "tokens"},
        {"amount_usd": -1},
        {"amount_usd": "1000000000"},
        {"confidence": 1.1},
        {"confidence": "0.9"},
        {"announced_date": "yesterday"},
        {"surprise": "field"},
        {"source_url": "file:///tmp/x"},
        {"rationale": "two\nlines"},
    ],
)
def test_strict_schema_rejects_bad_fields(deal_dict, bad):
    with pytest.raises(ValueError):
        parse_json(json.dumps({**deal_dict, **bad}), Deal)


def test_parser_allows_single_fence_but_no_prose_or_duplicate_keys(deal_dict):
    good = json.dumps({"edges": [deal_dict]})
    assert len(parse_json(good, Extraction).edges) == 1
    assert len(parse_json("```json\n" + good + "\n```", Extraction).edges) == 1
    for bad in (
        "Here is the JSON " + good,
        good + " trailing",
        '{"edges":[],"edges":[]}',
        '{"edges":[],"x":NaN}',
        "[]",
        '{"edges": null}',
    ):
        with pytest.raises(ValueError):
            parse_json(bad, Extraction)


def test_verifier_normalises_whitespace_only(runtime, deal_dict):
    resolver = runtime[3]().resolver
    edge = parse_json(json.dumps(deal_dict), Deal)
    assert verify(
        edge, "NVIDIA will\n invest $1 billion in OpenAI.", resolver, edge.source_url
    )["passed"]
    assert not verify(
        edge, "Nvidia will invest $1 billion in OpenAI.", resolver, edge.source_url
    )["passed"]
    assert not verify(
        edge, "NVIDIA might invest $1 billion in OpenAI.", resolver, edge.source_url
    )["passed"]


@pytest.mark.parametrize(
    "quote,amount,passed",
    [
        ("NVIDIA will invest $1 billion in OpenAI.", 1e9, True),
        ("NVIDIA will invest USD 1,000,000 in OpenAI.", 1e6, True),
        ("NVIDIA will invest 1 billion US dollars in OpenAI.", 1e9, True),
        ("NVIDIA will invest $1B in OpenAI.", 1e9, True),
        ("NVIDIA will issue 160 million shares to OpenAI.", 160e6, False),
        ("NVIDIA will deploy 6 gigawatts for OpenAI.", 6e9, False),
        ("NVIDIA will invest €1 billion in OpenAI.", 1e9, False),
        ("NVIDIA will invest $1 billion in OpenAI.", 1e8, False),
        ("NVIDIA will invest $1 billion in OpenAI.", None, True),
    ],
)
def test_amount_must_be_actual_usd_in_quote(runtime, deal_dict, quote, amount, passed):
    edge = parse_json(
        json.dumps(
            {
                **deal_dict,
                "evidence_quote": quote,
                "amount_usd": amount,
                "amount_text": quote.split("invest ")[-1].split(" in ")[0],
            }
        ),
        Deal,
    )
    assert (
        verify(edge, quote, runtime[3]().resolver, edge.source_url)["passed"] == passed
    )
    assert dollars("160 million shares at 2%") == set()
    assert dollars("$2.75 billion") == {Decimal("2750000000")}


def test_verifier_retains_multiple_failures(runtime, deal_dict):
    edge = parse_json(
        json.dumps(
            {
                **deal_dict,
                "source_entity": "Unknown Corp",
                "evidence_quote": "Fabricated $99 billion",
                "amount_usd": 1e9,
            }
        ),
        Deal,
    )
    checked = verify(
        edge, "Microsoft meets OpenAI.", runtime[3]().resolver, "https://different.test"
    )
    assert not checked["passed"]
    assert len(checked["errors"]) >= 4
