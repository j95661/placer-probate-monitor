"""Scoring rule unit tests."""

from __future__ import annotations

from sweep.names import parse_decedent
from sweep.recorder.base import RecorderRow
from sweep.score import (
    classify_doc_type,
    classify_rows,
    hearing_mismatch,
    score_dual_signal,
)


def _row(doc, names, doc_type, date, other=""):
    return RecorderRow(
        doc_number=doc,
        names=names,
        other_party=other,
        doc_type=doc_type,
        record_date=date,
    )


def test_classify_patterns():
    assert classify_doc_type("AFFIDAVIT OF DEATH OF TRUSTEE") == "AFFIDAVIT_OF_DEATH"
    assert classify_doc_type("AFFIDAVIT OF SUCCESSOR TRUSTEE") == "SUCCESSOR_TRUSTEE"
    assert classify_doc_type("TRUST TRANSFER DEED") == "TRUST_TRANSFER_DEED"
    assert classify_doc_type("GRANT DEED") == "DEED"
    assert classify_doc_type("LIS PENDENS WITHDRAWAL") == "LIS_PENDENS_WITHDRAWAL"


def test_hearing_mismatch():
    a, b, mismatch = hearing_mismatch("11/24/2026 9:00 AM", "11/23/2026")
    assert a == "11/24/2026"
    assert b == "11/23/2026"
    assert mismatch is True


def test_sold_estate_deed():
    parsed = parse_decedent("Watkins, Helen")
    rows = [
        _row(
            "2026-0058037-00",
            "ESTATE OF WATKINS, HELEN / EXECUTOR TOM WATKINS",
            "EXECUTOR DEED",
            "08/01/2026",
            "SMITH, BUYER",
        )
    ]
    result = score_dual_signal(
        case_number="S-PR-0014387",
        parsed=parsed,
        classified=classify_rows(rows),
    )
    assert result.dual_signal == "sold"


def test_bain_own_aod_only():
    parsed = parse_decedent("Bain, Arthur")
    rows = [
        _row(
            "2026-0005178-00",
            "BAIN, ARTHUR",
            "AFFIDAVIT OF DEATH OF JOINT TENANT",
            "02/20/2026",
        )
    ]
    result = score_dual_signal(
        case_number="S-PR-0013958",
        parsed=parsed,
        classified=classify_rows(rows),
    )
    assert result.dual_signal in {"no", "maybe"}
    assert result.score < 40


def test_shared_apn_strong():
    parsed = parse_decedent("Assenza, Frank")
    rows = [
        _row(
            "2026-0030505-00",
            "ASSENZA FAMILY TRUST",
            "AFFIDAVIT OF SUCCESSOR TRUSTEE",
            "04/15/2026",
            "ASSENZA, JOSEPH",
        )
    ]
    result = score_dual_signal(
        case_number="S-PR-0014319",
        parsed=parsed,
        classified=classify_rows(rows),
        apn="471-320-024-000",
        apn_peers=["S-PR-0014324"],
    )
    assert result.dual_signal == "yes"
    assert "shared APN" in result.reason
