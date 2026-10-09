"""County datasource helpers for the monitor and Follow Up Boss export.

Placer people are tagged ``probate``. Sacramento people are tagged
``probate`` and ``sacramento``. Callers that update an existing person
must send ``mergeTags=true`` so those tags are added beside tags the
person already has.
"""

from __future__ import annotations

FUB_TAG_PROBATE = "probate"
FUB_TAG_SACRAMENTO = "sacramento"

COUNTY_FUB_TAGS = {
    "placer": [FUB_TAG_PROBATE],
    "sacramento": [FUB_TAG_PROBATE, FUB_TAG_SACRAMENTO],
}

PLACER_KEYWORDS = '"NOTICE OF PETITION TO ADMINISTER ESTATE"'
SACRAMENTO_KEYWORDS = '"NOTICE OF PETITION"'

COUNTY_NAMES = {
    "placer": "Placer",
    "sacramento": "Sacramento",
}


def county_key(county: str | None) -> str:
    text = str(county or "").strip().lower()
    if "sacramento" in text:
        return "sacramento"
    if "placer" in text:
        return "placer"
    return text or "placer"


def normalize_county_name(county: str | None) -> str:
    key = county_key(county)
    if key in COUNTY_NAMES:
        return COUNTY_NAMES[key]
    text = str(county or "").strip()
    return text or "Placer"


def fub_tags(county: str) -> list[str]:
    key = county_key(county)
    try:
        return list(COUNTY_FUB_TAGS[key])
    except KeyError as exc:
        known = ", ".join(sorted(COUNTY_FUB_TAGS))
        raise ValueError(f"Unknown county {county!r}. Known: {known}") from exc


def stamp_fub_tags(rows: list[dict], county: str) -> list[dict]:
    tags = fub_tags(county)
    key = county_key(county)
    label = f"{normalize_county_name(county)} County"
    for row in rows:
        row["tags"] = list(tags)
        row["source_id"] = key
        row["source"] = label
    return rows


def keywords_for_county(county: str | None, keywords: str | None = None) -> str:
    """CNPA keywords that actually return this county's estate notices.

    Sacramento ads are missed by the long exact phrase. The shorter
    ``NOTICE OF PETITION`` query is used, and cards are kept only when
    the body contains PETITION TO ADMINISTER ESTATE.
    """
    raw = str(keywords or "").strip()
    if county_key(county) == "sacramento":
        if not raw or raw == PLACER_KEYWORDS:
            return SACRAMENTO_KEYWORDS
        return raw
    if not raw:
        return PLACER_KEYWORDS
    return raw
