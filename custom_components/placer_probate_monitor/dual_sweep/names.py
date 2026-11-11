"""Stage 1: decedent name parsing, AKA extraction, and dedupe helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

AKA_SPLIT_RE = re.compile(
    r"\b(?:also\s+known\s+as|a/?k/?a\.?|aka)\b",
    re.I,
)
# Trailing role / estate chrome that sometimes rides on the listing name.
JUNK_TAIL_RE = re.compile(
    r"[\s,;:/|-]*(?:deceased|estate\s+of|decedent)\s*$",
    re.I,
)
# Unreadable: all digits, empty after cleanup, or single letter tokens only.
READABLE_RE = re.compile(r"[A-Za-z]{2,}")


@dataclass(frozen=True)
class ParsedName:
    raw: str
    last: str
    first: str
    middle: str = ""
    akas: tuple[str, ...] = ()
    searchable: str = ""  # "LAST FIRST" for recorder

    @property
    def display(self) -> str:
        parts = [self.last, self.first]
        if self.middle:
            parts.append(self.middle)
        return " ".join(p for p in parts if p)


def _upper_clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).upper()


def _split_person(chunk: str) -> tuple[str, str, str]:
    """Parse LAST, FIRST MIDDLE or FIRST MIDDLE LAST into (last, first, middle)."""
    text = _upper_clean(chunk)
    text = JUNK_TAIL_RE.sub("", text).strip(" ,;")
    if not text:
        return "", "", ""

    if "," in text:
        last, _, rest = text.partition(",")
        tokens = rest.strip().split()
        first = tokens[0] if tokens else ""
        middle = " ".join(tokens[1:]) if len(tokens) > 1 else ""
        return last.strip(), first, middle

    tokens = text.split()
    if len(tokens) == 1:
        return tokens[0], "", ""
    if len(tokens) == 2:
        # Prefer FIRST LAST for natural listing order.
        return tokens[1], tokens[0], ""
    # FIRST MIDDLE... LAST
    return tokens[-1], tokens[0], " ".join(tokens[1:-1])


def parse_decedent(raw: str) -> ParsedName | None:
    """Parse a listing decedent string into structured uppercase parts.

    Returns None when the name is unreadable (caller should skip + log).
    """
    original = (raw or "").strip()
    if not original:
        return None

    pieces = AKA_SPLIT_RE.split(original)
    primary = pieces[0].strip(" ,;")
    akas = tuple(
        _upper_clean(p.strip(" ,;"))
        for p in pieces[1:]
        if p and _upper_clean(p.strip(" ,;"))
    )

    last, first, middle = _split_person(primary)
    if not last or not READABLE_RE.search(last):
        return None
    if first and not READABLE_RE.search(first) and len(first) > 1:
        # Keep single middle initials; reject garbage first tokens.
        if not re.fullmatch(r"[A-Z]\.?", first):
            return None
    if not first and not akas:
        # Surname-only is usable for a surname-wide recorder search.
        pass

    searchable = " ".join(p for p in (last, first) if p)
    return ParsedName(
        raw=original,
        last=last,
        first=first,
        middle=middle,
        akas=akas,
        searchable=searchable,
    )


def dedupe_listings(listings: list[dict]) -> list[dict]:
    """Dedupe by case_number; collapse multiple notices for the same decedent.

    Prefer the row with the newest last_seen, then one that has a DE-111.
    """
    by_case: dict[str, dict] = {}
    skipped: list[str] = []

    for row in listings:
        case = str(row.get("case_number") or "").strip()
        if not case:
            skipped.append(str(row.get("decedent") or "<no-case>"))
            continue
        parsed = parse_decedent(str(row.get("decedent") or ""))
        if parsed is None:
            log.warning("skip unreadable decedent for %s: %r", case, row.get("decedent"))
            skipped.append(case)
            continue
        enriched = dict(row)
        enriched["_parsed_name"] = parsed
        prev = by_case.get(case)
        if prev is None:
            by_case[case] = enriched
            continue
        prev_seen = str(prev.get("last_seen") or "")
        new_seen = str(enriched.get("last_seen") or "")
        prev_de111 = bool(prev.get("has_de111") or prev.get("de111_url"))
        new_de111 = bool(enriched.get("has_de111") or enriched.get("de111_url"))
        if new_seen > prev_seen or (new_seen == prev_seen and new_de111 and not prev_de111):
            by_case[case] = enriched

    # Collapse same-decedent multi-case notices only for logging; keep all cases.
    # Dual-APN signals across cases (Assenza) need both rows retained.
    if skipped:
        log.info("skipped %d unreadable/unnamed listings", len(skipped))
    return sorted(by_case.values(), key=lambda r: str(r.get("case_number") or ""))
