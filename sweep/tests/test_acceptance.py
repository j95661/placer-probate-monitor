"""Acceptance tests from the 2026-11-11 run (fixtures only; no live CountyFusion)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sweep.pipeline import SweepRunner

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def results(tmp_path: Path):
    # Isolate data/out under tmp so repo caches are not required.
    runner = SweepRunner(
        tmp_path,
        fixtures_dir=FIX,
        max_searches=10,
        refresh=True,
        offline=True,
    )
    try:
        out = runner.run(top_n=10)
    finally:
        runner.close()
    return {r.case_number: r for r in out}


def _has_doc(result, prefix: str) -> bool:
    blob = " ".join(
        result.dual.own_aod_docs
        + result.dual.related_docs
        + [e.get("doc_number", "") for e in result.dual.evidence]
    )
    return prefix in blob


def test_lasater(results):
    r = results["S-PR-0014196"]
    assert r.parcel is not None
    assert r.parcel.apn == "001-062-015-000"
    assert _has_doc(r, "2025-0072761")
    assert _has_doc(r, "2026-0015534")
    assert _has_doc(r, "2025-0072762")
    assert _has_doc(r, "2026-0015535")
    assert r.dual.dual_signal == "yes"


def test_eisley(results):
    r = results["S-PR-0014335"]
    assert r.parcel is not None
    assert r.parcel.apn == "001-032-006-000"
    for prefix in (
        "2022-0014623",
        "2022-0014625",
        "2022-0014631",
        "2022-0014635",
        "2022-0014637",
        "2022-0014643",
        "2022-0091025",
        "2023-0004968",
    ):
        assert _has_doc(r, prefix), prefix
    assert r.hearing_mismatch is True
    assert r.hearing_listing == "11/24/2026"
    assert r.hearing_de111 == "11/23/2026"
    assert r.dual.dual_signal == "yes"
    assert "DEBORAH" in r.de111.spouse_name


def test_assenza_shared_apn(results):
    a = results["S-PR-0014319"]
    b = results["S-PR-0014324"]
    assert a.parcel and b.parcel
    assert a.parcel.apn == b.parcel.apn == "471-320-024-000"
    assert _has_doc(a, "2026-0030505") or _has_doc(b, "2026-0030505")
    assert a.dual.dual_signal == "yes"
    assert b.dual.dual_signal == "yes"


def test_watkins_sold(results):
    r = results["S-PR-0014387"]
    assert _has_doc(r, "2026-0058037")
    assert r.dual.dual_signal == "sold"


def test_bain_no_or_weak(results):
    r = results["S-PR-0013958"]
    assert _has_doc(r, "2026-0005178")
    assert r.dual.dual_signal in {"no", "maybe"}
    assert r.dual.score < 40
