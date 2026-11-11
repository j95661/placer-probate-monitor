"""DE-111 field extraction from OCR text (no live RapidOCR)."""

from __future__ import annotations

from pathlib import Path

from sweep.ocr import extract_de111_fields

FIX = Path(__file__).parent / "fixtures" / "de111"


def test_eisley_spouse_and_hearing():
    text = (FIX / "S-PR-0014335.ocr.txt").read_text(encoding="utf-8")
    fields = extract_de111_fields("S-PR-0014335", text)
    assert fields.hearing_date == "11/23/2026"
    assert fields.spouse_deceased is True
    assert "DEBORAH" in fields.spouse_name
    assert fields.spouse_dod == "03/18/2023"
    assert "138" in fields.property_address or "138" in fields.residence_address
    assert fields.date_of_death == "01/15/2022"


def test_lasater_gmv_and_address():
    text = (FIX / "S-PR-0014196.ocr.txt").read_text(encoding="utf-8")
    fields = extract_de111_fields("S-PR-0014196", text)
    assert fields.estate_real == "850000"
    assert "412" in (fields.property_address or fields.residence_address)
