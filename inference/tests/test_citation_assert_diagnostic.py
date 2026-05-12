"""Citation assertion diagnostics."""

from src.generation.modules import (
    every_claim_has_chunk_id,
    explain_citation_assertion_failure,
    repair_citations_with_fallback,
)


def test_explain_detects_numeric_footnotes() -> None:
    text = "Kushal works at ACME as of Nov 2025 1. He builds APIs 2."
    assert every_claim_has_chunk_id(text) is False
    detail = explain_citation_assertion_failure(text)
    assert detail["reason"] == "no_bracket_citations_found"
    assert detail.get("suspected_numeric_footnotes") is True


def test_repair_citations_appends_fallback_chunk_id() -> None:
    text = "This answer has no citations."
    fixed = repair_citations_with_fallback(text, ["chunk_1"])
    assert every_claim_has_chunk_id(fixed)
    assert fixed.endswith("[chunk_1]")


def test_explain_line_missing_trailing_bracket() -> None:
    text = "Grounded sentence.[chunk_a]\nUnfinished sentence without citation"
    assert every_claim_has_chunk_id(text) is False
    d = explain_citation_assertion_failure(text)
    assert d["reason"] == "line_missing_trailing_bracket"
    assert d["line_index"] == 1
