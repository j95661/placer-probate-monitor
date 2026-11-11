"""Unit tests for decedent name parsing and dedupe."""

from __future__ import annotations

from sweep.names import dedupe_listings, parse_decedent


def test_parse_first_last():
    p = parse_decedent("Robert E. Lasater")
    assert p is not None
    assert p.last == "LASATER"
    assert p.first == "ROBERT"
    assert p.middle == "E."
    assert p.searchable == "LASATER ROBERT"


def test_parse_last_comma_first():
    p = parse_decedent("Eisley, John A.")
    assert p is not None
    assert p.last == "EISLEY"
    assert p.first == "JOHN"
    assert "A" in p.middle


def test_parse_aka():
    p = parse_decedent("Mary Smith aka Mary Jones also known as M. Smith")
    assert p is not None
    assert p.last == "SMITH"
    assert p.first == "MARY"
    assert any("JONES" in a for a in p.akas)


def test_skip_unreadable():
    assert parse_decedent("") is None
    assert parse_decedent("12345") is None


def test_dedupe_by_case():
    rows = [
        {
            "case_number": "S-PR-1",
            "decedent": "Jane Doe",
            "last_seen": "2026-01-01",
            "has_de111": False,
        },
        {
            "case_number": "S-PR-1",
            "decedent": "Jane Doe",
            "last_seen": "2026-02-01",
            "has_de111": True,
        },
        {
            "case_number": "S-PR-2",
            "decedent": "???",
            "last_seen": "2026-02-01",
        },
    ]
    out = dedupe_listings(rows)
    assert len(out) == 1
    assert out[0]["last_seen"] == "2026-02-01"
    assert out[0]["has_de111"] is True
