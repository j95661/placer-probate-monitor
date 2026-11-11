"""Row parsing from saved HTML / JSON fixtures (no live CountyFusion)."""

from __future__ import annotations

from pathlib import Path

from sweep.recorder.placer_countyfusion import parse_result_rows

FIX = Path(__file__).parent / "fixtures"


def test_parse_html_fixture():
    html = (FIX / "html" / "sample_results.html").read_text(encoding="utf-8")
    rows = parse_result_rows(html)
    docs = {r.doc_number for r in rows}
    assert "2025-0072761-00" in docs
    assert "2026-0015534-00" in docs
    aod = next(r for r in rows if r.doc_number == "2025-0072761-00")
    assert "AFFIDAVIT" in aod.doc_type


def test_parse_json_fixture():
    text = (FIX / "recorder" / "EISLEY.json").read_text(encoding="utf-8")
    rows = parse_result_rows(text)
    docs = [r.doc_number for r in rows]
    assert "2023-0004968-00" in docs
    assert "2022-0014623-00" in docs
    assert all(r.doc_type for r in rows)


def test_parse_plain_line():
    line = (
        "2026-0058037-00  ESTATE OF WATKINS, HELEN  "
        "SMITH, BUYER  EXECUTOR DEED  08/01/2026"
    )
    rows = parse_result_rows(line)
    assert len(rows) == 1
    assert rows[0].doc_number == "2026-0058037-00"
    assert "DEED" in rows[0].doc_type
