"""XBRL companyfacts parsing."""
import json
from pathlib import Path

import pytest

from src.xbrl import CONCEPTS, coverage, extract_facts, latest_in_group

ROOT = Path(__file__).resolve().parent.parent


def synthetic() -> dict:
    return {"cik": 1, "entityName": "Toy Co", "facts": {"us-gaap": {
        "RevenueRemainingPerformanceObligation": {
            "label": "RPO", "units": {"USD": [
                {"val": 100, "end": "2025-12-31", "form": "10-K", "filed": "2026-02-01",
                 "accn": "0000-00-1", "fy": 2025, "fp": "FY"},
                {"val": 250, "end": "2026-06-30", "form": "10-Q", "filed": "2026-07-20",
                 "accn": "0000-00-2", "fy": 2026, "fp": "Q2"},
                {"val": 999, "end": "2026-06-30", "form": "8-K", "filed": "2026-07-25",
                 "accn": "0000-00-3"},
            ]}},
        "ConcentrationRiskPercentage1": {
            "label": "Concentration", "units": {"pure": [
                {"val": 0.67, "end": "2025-12-31", "form": "10-K", "filed": "2026-02-01",
                 "accn": "0000-00-1"}]}},
        "SomeIrrelevantTag": {"label": "noise", "units": {"USD": [
            {"val": 5, "end": "2026-01-01", "form": "10-K", "accn": "x"}]}},
    }}}


def test_only_the_concepts_of_interest_are_extracted():
    rows = extract_facts(synthetic(), "Toy Co")
    assert {r["concept"] for r in rows} == {
        "RevenueRemainingPerformanceObligation", "ConcentrationRiskPercentage1"}
    assert "SomeIrrelevantTag" not in {r["concept"] for r in rows}


def test_group_mapping_and_units():
    rows = extract_facts(synthetic(), "Toy Co")
    rpo = [r for r in rows if r["group"] == "rpo"]
    assert len(rpo) == 3
    assert all(r["unit"] == "USD" for r in rpo)
    conc = [r for r in rows if r["group"] == "concentration"]
    assert conc[0]["unit"] == "pure" and conc[0]["value"] == 0.67


def test_latest_in_group_prefers_periodic_forms_and_the_newest_period():
    rows = extract_facts(synthetic(), "Toy Co")
    latest = latest_in_group(rows, "Toy Co", "rpo")
    assert latest["value"] == 250, "the 8-K value must not win over the 10-Q"
    assert latest["end"] == "2026-06-30"


def test_empty_and_malformed_inputs_do_not_raise():
    assert extract_facts(None, "x") == []
    assert extract_facts({}, "x") == []
    assert extract_facts({"facts": {}}, "x") == []
    assert extract_facts({"facts": {"us-gaap": {
        "RevenueRemainingPerformanceObligation": {"units": {}}}}}, "x") == []


def test_coverage_counts_every_group_for_every_node():
    rows = extract_facts(synthetic(), "Toy Co")
    cov = coverage(rows, ["Toy Co", "Absent Co"])
    assert set(cov) == {"Toy Co", "Absent Co"}
    assert set(cov["Toy Co"]) >= set(CONCEPTS)
    assert cov["Toy Co"]["rpo"] == 3
    assert cov["Absent Co"]["rpo"] == 0


def test_real_cached_facts_parse_if_present():
    p = ROOT / "data" / "interim" / "xbrl_facts.csv"
    if not p.exists():
        pytest.skip("run `make ingest` first")
    import pandas as pd
    df = pd.read_csv(p)
    assert len(df) > 1000
    assert set(df.group) <= set(CONCEPTS)
    rpo = df[(df.group == "rpo") & (df.form == "10-Q")]
    assert len(rpo) > 0, "no RPO observations found in the cached facts"
