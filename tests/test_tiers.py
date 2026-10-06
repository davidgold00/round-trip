"""Tier gate: no T3 or T4 in the headline, no T4 anywhere."""
import pytest

from src.ledger import filter_tiers, load_edges
from src.metrics import compute, sensitivity_t3
from src.util import load_config
from tests import toy


@pytest.fixture
def cfg():
    return load_config()


def test_t3_funding_leg_is_excluded_from_headline(cfg):
    e, b = toy.tiered()
    res = compute(e, b, cfg)                       # headline gate: T1 + T2
    row = res.rte.set_index("supplier").loc["A"]
    assert row["rte_central"] == pytest.approx(0.0), "T3 funding must not count"
    sens = sensitivity_t3(e, b, cfg)               # sensitivity gate: T1 + T2 + T3
    assert sens["ecosystem"]["CENTRAL"]["rte"] == pytest.approx(1.0)


def test_t4_is_never_counted_even_in_the_sensitivity_view(cfg):
    e, b = toy.t4_only()
    assert len(filter_tiers(e, ["T1", "T2", "T3", "T4"])) == 1, "only the T1 demand leg"
    sens = sensitivity_t3(e, b, cfg)
    assert sens["ecosystem"]["CENTRAL"]["rte"] == pytest.approx(0.0)


def test_filter_tiers_strips_t4_even_if_explicitly_allowed():
    e, _ = toy.t4_only()
    out = filter_tiers(e, ["T4"])
    assert len(out) == 0


def test_real_ledger_headline_uses_only_t1_t2(cfg):
    df = load_edges()
    if df.empty:
        pytest.skip("no ledger yet")
    gated = filter_tiers(df, cfg["tiers"]["headline_allowed"])
    assert set(gated.evidence_tier) <= {"T1", "T2"}
    assert "T4" not in set(df.evidence_tier), "T4 must never reach the ledger at all"


def test_every_t1_row_has_an_accession_number():
    df = load_edges()
    if df.empty:
        pytest.skip("no ledger yet")
    t1 = df[df.evidence_tier == "T1"]
    assert (t1.accession_no.str.strip() != "").all()


def test_every_row_has_a_short_quote_and_a_url():
    df = load_edges()
    if df.empty:
        pytest.skip("no ledger yet")
    for _, r in df.iterrows():
        assert str(r.source_url).startswith("http"), r.edge_id
        words = len(str(r.quote_snippet).split())
        assert 0 < words < 25, f"{r.edge_id}: {words} words"
