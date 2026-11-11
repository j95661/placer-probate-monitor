"""Stage 5: document classification and dual-affidavit scoring."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable

from .names import ParsedName
from .recorder.base import RecorderRow

# Common surnames get a weak-signal penalty.
COMMON_SURNAMES = {
    "SMITH",
    "JOHNSON",
    "WILLIAMS",
    "BROWN",
    "JONES",
    "GARCIA",
    "MILLER",
    "DAVIS",
    "RODRIGUEZ",
    "MARTINEZ",
    "HERNANDEZ",
    "LOPEZ",
    "GONZALEZ",
    "WILSON",
    "ANDERSON",
    "THOMAS",
    "TAYLOR",
    "MOORE",
    "JACKSON",
    "MARTIN",
    "LEE",
    "PEREZ",
    "THOMPSON",
    "WHITE",
    "HARRIS",
    "SANCHEZ",
    "CLARK",
    "RAMIREZ",
    "LEWIS",
    "ROBINSON",
    "WALKER",
    "YOUNG",
    "ALLEN",
    "KING",
    "WRIGHT",
    "SCOTT",
    "TORRES",
    "NGUYEN",
    "HILL",
    "FLORES",
    "GREEN",
    "ADAMS",
    "NELSON",
    "BAKER",
    "HALL",
    "RIVERA",
    "CAMPBELL",
    "MITCHELL",
    "CARTER",
    "ROBERTS",
}


DOC_CLASS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "AFFIDAVIT_OF_DEATH",
        re.compile(
            r"AFFIDAVIT\s+OF\s+DEATH|AOD\b|DEATH\s+OF\s+(?:JOINT\s+TENANT|TRUSTEE|SPOUSE)",
            re.I,
        ),
    ),
    (
        "SUCCESSOR_TRUSTEE",
        re.compile(
            r"SUCCESSOR\s+TRUSTEE|AFFIDAVIT\s+of\s+SUCCESSOR|CERTIFICATION\s+OF\s+TRUST",
            re.I,
        ),
    ),
    (
        "SURVIVING_SPOUSE",
        re.compile(r"SURVIVING\s+SPOUSE|SPOUSAL\s+PROPERTY", re.I),
    ),
    (
        "DECREE_DISTRIBUTION",
        re.compile(r"DECREE\s+OF\s+DISTRIBUTION|ORDER\s+OF\s+DISTRIBUTION|\bORDER\b", re.I),
    ),
    (
        "TRANSFER_ON_DEATH",
        re.compile(r"TRANSFER\s+ON\s+DEATH|\bTOD\b", re.I),
    ),
    (
        "TRUST_TRANSFER_DEED",
        re.compile(r"TRUST\s+TRANSFER\s+DEED", re.I),
    ),
    (
        "LIS_PENDENS_WITHDRAWAL",
        re.compile(r"LIS\s+PENDENS\s+WITHDRAWAL|WITHDRAWAL\s+OF\s+LIS\s+PENDENS", re.I),
    ),
    (
        "LIS_PENDENS",
        re.compile(r"LIS\s+PENDENS", re.I),
    ),
    (
        "LEASE",
        re.compile(r"\bLEASE\b", re.I),
    ),
    (
        "DEED",
        re.compile(r"\b(?:GRANT|QUITCLAIM|WARRANTY|EXECUTOR|ESTATE|ADMINISTRATOR)?\s*DEED\b", re.I),
    ),
]


@dataclass
class ClassifiedDoc:
    row: RecorderRow
    doc_class: str
    trust_name: str = ""

    def to_dict(self) -> dict:
        d = self.row.to_dict()
        d["doc_class"] = self.doc_class
        d["trust_name"] = self.trust_name
        return d


@dataclass
class DualSignalResult:
    case_number: str
    decedent: str
    dual_signal: str  # yes | maybe | no | sold
    score: int
    reason: str
    coverage: str = "full"  # full | partial
    own_aod_docs: list[str] = field(default_factory=list)
    related_docs: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def classify_doc_type(doc_type: str) -> str:
    text = doc_type or ""
    for label, pattern in DOC_CLASS_PATTERNS:
        if pattern.search(text):
            # DEED excludes trust transfer (matched earlier).
            if label == "DEED" and re.search(r"TRUST\s+TRANSFER", text, re.I):
                continue
            return label
    return "OTHER"


def extract_trust_name(names: str, doc_type: str = "") -> str:
    text = f"{names} {doc_type}"
    m = re.search(
        r"([A-Z][A-Z0-9 .'-]{2,60}?\s+(?:FAMILY\s+)?TRUST(?:\s+DATED\s+\d{1,2}/\d{1,2}/\d{2,4})?)",
        text,
        re.I,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().upper()
    return ""


def classify_rows(rows: Iterable[RecorderRow]) -> list[ClassifiedDoc]:
    out: list[ClassifiedDoc] = []
    for row in rows:
        doc_class = classify_doc_type(row.doc_type)
        trust = extract_trust_name(row.names, row.doc_type)
        if not trust:
            trust = extract_trust_name(row.other_party, row.doc_type)
        out.append(ClassifiedDoc(row=row, doc_class=doc_class, trust_name=trust))
    return out


def _parse_date(text: str) -> datetime | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime((text or "").strip(), fmt)
        except ValueError:
            continue
    return None


def _months_apart(a: datetime, b: datetime) -> float:
    return abs((a - b).days) / 30.4375


def _name_matches_decedent(text: str, parsed: ParsedName) -> bool:
    hay = (text or "").upper()
    if not parsed.last or parsed.last not in hay:
        return False
    if not parsed.first:
        return True
    # LAST FIRST with optional middle initial.
    pattern = re.compile(
        rf"\b{re.escape(parsed.last)}\b[,\s]+{re.escape(parsed.first)}"
        rf"(?:\s+[A-Z]\.?)?\b",
        re.I,
    )
    if pattern.search(hay):
        return True
    # FIRST LAST
    pattern2 = re.compile(
        rf"\b{re.escape(parsed.first)}(?:\s+[A-Z]\.?)?\s+{re.escape(parsed.last)}\b",
        re.I,
    )
    return bool(pattern2.search(hay))


def _is_estate_deed_out(doc: ClassifiedDoc) -> bool:
    if doc.doc_class not in {"DEED", "OTHER"}:
        # Still check type text for estate/executor deeds.
        pass
    blob = f"{doc.row.doc_type} {doc.row.names} {doc.row.other_party}".upper()
    return bool(
        re.search(r"\b(?:ESTATE|EXECUTOR|ADMINISTRATOR|PERSONAL\s+REPRESENTATIVE)\b", blob)
        and re.search(r"\bDEED\b", blob)
    )


def gather_decedent_docs(
    classified: list[ClassifiedDoc],
    parsed: ParsedName,
) -> tuple[list[ClassifiedDoc], list[ClassifiedDoc], list[ClassifiedDoc]]:
    """Own records, same-surname death/successor, last 6 deeds."""
    own: list[ClassifiedDoc] = []
    same_surname_death: list[ClassifiedDoc] = []
    deeds: list[ClassifiedDoc] = []

    for doc in classified:
        blob = f"{doc.row.names} {doc.row.other_party}"
        if _name_matches_decedent(blob, parsed):
            own.append(doc)
        if parsed.last and parsed.last in blob.upper():
            if doc.doc_class in {"AFFIDAVIT_OF_DEATH", "SUCCESSOR_TRUSTEE"}:
                same_surname_death.append(doc)
        if doc.doc_class in {"DEED", "TRUST_TRANSFER_DEED"} or _is_estate_deed_out(doc):
            deeds.append(doc)

    def sort_key(d: ClassifiedDoc) -> tuple:
        dt = _parse_date(d.row.record_date) or datetime.min
        return (dt, d.row.doc_number)

    deeds_sorted = sorted(deeds, key=sort_key, reverse=True)[:6]
    return own, same_surname_death, deeds_sorted


def score_dual_signal(
    *,
    case_number: str,
    parsed: ParsedName,
    classified: list[ClassifiedDoc],
    spouse_name: str = "",
    spouse_deceased: bool = False,
    spouse_dod: str = "",
    apn: str = "",
    apn_peers: list[str] | None = None,
    truncated: bool = False,
    will_spouse_predeceased: bool = False,
) -> DualSignalResult:
    """Apply strong / medium / weak / sold dual-signal rules."""
    own, same_surname, deeds = gather_decedent_docs(classified, parsed)
    coverage = "partial" if truncated else "full"

    own_aod = [
        d.row.doc_number
        for d in own
        if d.doc_class == "AFFIDAVIT_OF_DEATH"
    ]
    related = [
        d.row.doc_number
        for d in same_surname
        if d.row.doc_number not in own_aod
    ]

    reasons: list[str] = []
    score = 0
    signal = "no"
    evidence = [d.to_dict() for d in own + same_surname]

    # SOLD: estate/executor deed out after death.
    for deed in deeds:
        if _is_estate_deed_out(deed):
            # Prefer third-party grantee (other party present / not same surname only).
            signal = "sold"
            score = max(score, 90)
            reasons.append(
                f"estate/executor deed out {deed.row.doc_number} "
                f"({deed.row.record_date or 'undated'})"
            )
            related.append(deed.row.doc_number)
            break

    if signal != "sold":
        # Strong: DE-111 deceased spouse + AOD for that spouse.
        spouse_upper = (spouse_name or "").upper().strip()
        if spouse_deceased and spouse_upper:
            spouse_tokens = spouse_upper.split()
            spouse_hits = []
            for doc in same_surname:
                if doc.doc_class != "AFFIDAVIT_OF_DEATH":
                    continue
                blob = f"{doc.row.names} {doc.row.other_party}".upper()
                if all(tok in blob for tok in spouse_tokens if len(tok) > 1):
                    spouse_hits.append(doc)
            if spouse_hits:
                signal = "yes"
                score = max(score, 100)
                docs = ", ".join(d.row.doc_number for d in spouse_hits)
                reasons.append(
                    f"DE-111 deceased spouse {spouse_upper}"
                    + (f" (dod {spouse_dod})" if spouse_dod else "")
                    + f" matched AOD {docs}"
                )

        # Strong: two AOD / successor-trustee refs to same trust within 24 months.
        trust_docs: dict[str, list[ClassifiedDoc]] = {}
        for doc in same_surname:
            if doc.doc_class not in {"AFFIDAVIT_OF_DEATH", "SUCCESSOR_TRUSTEE"}:
                continue
            if not doc.trust_name:
                continue
            trust_docs.setdefault(doc.trust_name, []).append(doc)
        for trust, docs in trust_docs.items():
            if len(docs) < 2:
                continue
            dates = [(_parse_date(d.row.record_date), d) for d in docs]
            dated = [(dt, d) for dt, d in dates if dt]
            paired = False
            for i, (dt_a, a) in enumerate(dated):
                for dt_b, b in dated[i + 1 :]:
                    if _months_apart(dt_a, dt_b) <= 24:
                        paired = True
                        signal = "yes"
                        score = max(score, 95)
                        reasons.append(
                            f"two {a.doc_class}/{b.doc_class} docs for trust "
                            f"{trust} within 24 months: "
                            f"{a.row.doc_number} & {b.row.doc_number}"
                        )
                        break
                if paired:
                    break
            if not paired and len(docs) >= 2:
                # Still a strong dual if two exist even without parseable dates.
                signal = "yes"
                score = max(score, 90)
                reasons.append(
                    f"multiple AOD/successor-trustee docs for trust {trust}: "
                    + ", ".join(d.row.doc_number for d in docs)
                )

        # Strong: two listings share the same APN.
        peers = [p for p in (apn_peers or []) if p and p != case_number]
        if apn and peers:
            signal = "yes"
            score = max(score, 92)
            reasons.append(f"shared APN {apn} with case(s) {', '.join(peers)}")

        # Medium: same-surname AOD + deed exchanged between the two names.
        if signal in {"no", "maybe"}:
            aods = [d for d in same_surname if d.doc_class == "AFFIDAVIT_OF_DEATH"]
            for aod in aods:
                aod_names = set(re.findall(r"[A-Z]{2,}", f"{aod.row.names} {aod.row.other_party}".upper()))
                for deed in deeds:
                    deed_names = set(
                        re.findall(r"[A-Z]{2,}", f"{deed.row.names} {deed.row.other_party}".upper())
                    )
                    overlap = aod_names & deed_names
                    # Need decedent surname + another party.
                    if parsed.last in overlap and len(overlap) >= 2:
                        signal = "maybe"
                        score = max(score, 60)
                        reasons.append(
                            f"same-surname AOD {aod.row.doc_number} + deed "
                            f"{deed.row.doc_number} linking parties"
                        )
                        break

        # Medium: will/DE-111 says spouse predeceased + older AOD found.
        if signal in {"no", "maybe"} and (will_spouse_predeceased or spouse_deceased):
            older = [d for d in same_surname if d.doc_class == "AFFIDAVIT_OF_DEATH"]
            if older:
                signal = "maybe"
                score = max(score, 55)
                reasons.append(
                    "spouse predeceased noted; older AOD "
                    + ", ".join(d.row.doc_number for d in older[:3])
                )

        # Weak: same-surname AOD with no linking party.
        if signal == "no":
            weak_aods = [
                d
                for d in same_surname
                if d.doc_class == "AFFIDAVIT_OF_DEATH"
                and not _name_matches_decedent(f"{d.row.names} {d.row.other_party}", parsed)
            ]
            # Also count own-only single AOD as no/weak (Bain).
            if weak_aods:
                signal = "maybe"
                score = max(score, 25)
                if parsed.last in COMMON_SURNAMES:
                    score = max(10, score - 15)
                    reasons.append(
                        f"weak same-surname AOD (common surname penalty): "
                        + ", ".join(d.row.doc_number for d in weak_aods[:3])
                    )
                else:
                    reasons.append(
                        "weak same-surname AOD with no linking party: "
                        + ", ".join(d.row.doc_number for d in weak_aods[:3])
                    )
            elif own_aod and not related:
                signal = "no"
                score = 5
                reasons.append(
                    f"own AOD only ({', '.join(own_aod)}); no dual signal"
                )

    # Deduplicate related doc numbers preserving order.
    seen: set[str] = set()
    related_unique: list[str] = []
    for doc_n in related:
        if doc_n not in seen and doc_n not in own_aod:
            seen.add(doc_n)
            related_unique.append(doc_n)

    if not reasons:
        reasons.append("no dual-affidavit evidence found")

    return DualSignalResult(
        case_number=case_number,
        decedent=parsed.display,
        dual_signal=signal,
        score=score,
        reason="; ".join(reasons),
        coverage=coverage,
        own_aod_docs=own_aod,
        related_docs=related_unique,
        evidence=evidence,
    )


def hearing_mismatch(listing_hearing: str, de111_hearing: str) -> tuple[str, str, bool]:
    """Return (listing_date, de111_date, mismatch)."""
    def extract(text: str) -> str:
        m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", text or "")
        if not m:
            return ""
        parts = m.group(1).split("/")
        mm, dd, yy = parts
        if len(yy) == 2:
            yy = ("20" if int(yy) < 70 else "19") + yy
        return f"{int(mm):02d}/{int(dd):02d}/{yy}"

    a = extract(listing_hearing)
    b = extract(de111_hearing)
    return a, b, bool(a and b and a != b)
