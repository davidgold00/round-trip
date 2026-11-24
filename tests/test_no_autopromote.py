"""The extractor must never be able to write to the ledger."""
import inspect
from pathlib import Path

import src.extract as extract
import src.review as review

ROOT = Path(__file__).resolve().parent.parent


def _code_only(module) -> str:
    """Module source with docstrings and comments removed.

    The extractor's own docstring talks about edges.csv on purpose, to tell a
    reader it will never write there. This test is about executable code.
    """
    import ast
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:]
    return ast.unparse(tree)


def test_extract_module_never_references_edges_csv():
    code = _code_only(extract)
    assert "edges.csv" not in code
    assert "write_edges" not in code
    assert "append_edge" not in code
    assert "backlog.csv" not in code


def test_extract_writes_only_candidates_and_interim():
    src = inspect.getsource(extract)
    assert "candidates.csv" in src


def test_candidates_file_is_not_the_ledger():
    cand = ROOT / "ledger" / "candidates.csv"
    edges = ROOT / "ledger" / "edges.csv"
    if cand.exists() and edges.exists():
        assert cand.read_text() != edges.read_text()


def test_promotion_requires_a_quote():
    import pytest
    with pytest.raises(SystemExit):
        review.check_quote("")
    with pytest.raises(SystemExit):
        review.check_quote(" ".join(["word"] * 25))
    review.check_quote("a short verbatim quote from the filing")


def test_promotion_rejects_t4_and_t1_without_accession():
    import pytest
    base = dict(source_node="A", target_node="B", edge_type="equity_investment",
                status="definitive", amount_basis="notional",
                source_url="https://example.test/x", quote_snippet="short quote here")
    with pytest.raises(SystemExit):
        review.check_row({**base, "evidence_tier": "T4"})
    with pytest.raises(SystemExit):
        review.check_row({**base, "evidence_tier": "T1", "accession_no": ""})
    review.check_row({**base, "evidence_tier": "T1", "accession_no": "0000-00-0"})
    review.check_row({**base, "evidence_tier": "T2", "accession_no": ""})


def test_missing_cached_filing_preserves_queue_and_evidence(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(extract, "ROOT", tmp_path)
    monkeypatch.setattr(extract, "INTERIM", tmp_path)
    monkeypatch.setattr(extract, "LEDGER", tmp_path)
    (tmp_path / "filings_index.csv").write_text("local_path\nmissing.html\n")
    files = [tmp_path / name for name in ("candidates.csv", "backlog_sentences.csv", "concentration_sentences.csv")]
    for path in files:
        path.write_text("saved evidence\n")
    with pytest.raises(SystemExit, match="Missing 1 of 1"):
        extract.run()
    assert all(path.read_text() == "saved evidence\n" for path in files)
