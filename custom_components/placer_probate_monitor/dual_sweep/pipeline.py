"""Orchestrate Stages 1–5 into CSV / JSON / leads.md outputs."""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .names import ParsedName, dedupe_listings, parse_decedent
from .ocr import De111Fields, load_or_ocr
from .parcels import ParcelHit, resolve_apn
from .recorder.base import RecorderSearchResult, RecorderSource
from .recorder.placer_countyfusion import PlacerCountyFusionRecorder, parse_result_rows
from .score import (
    DualSignalResult,
    classify_rows,
    hearing_mismatch,
    score_dual_signal,
)
from .sources.ha import HAClient, load_listings_fixture

log = logging.getLogger(__name__)

CSV_COLUMNS = [
    "case_number",
    "decedent",
    "dod",
    "spouse",
    "spouse_dod",
    "address",
    "apn",
    "apn_source",
    "land_value",
    "structure_value",
    "own_aod_docs",
    "related_docs",
    "dual_signal",
    "score",
    "reason",
    "coverage",
    "hearing_de111",
    "hearing_listing",
    "hearing_mismatch",
]


@dataclass
class SweepPaths:
    root: Path
    data: Path = field(init=False)
    de111: Path = field(init=False)
    recorder: Path = field(init=False)
    parcels: Path = field(init=False)
    out: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data = self.root / "data"
        self.de111 = self.data / "de111"
        self.recorder = self.data / "recorder"
        self.parcels = self.data / "parcels"
        self.out = self.root / "out"
        for p in (self.de111, self.recorder, self.parcels, self.out):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class CaseResult:
    case_number: str
    decedent: str
    listing: dict[str, Any]
    parsed: ParsedName
    de111: De111Fields
    parcel: ParcelHit | None
    recorder_queries: list[str]
    truncated: bool
    dual: DualSignalResult
    hearing_listing: str
    hearing_de111: str
    hearing_mismatch: bool

    def csv_row(self) -> dict[str, Any]:
        addr = (
            (self.de111.property_address or self.de111.residence_address)
            or str(self.listing.get("decedent_address") or "")
        )
        return {
            "case_number": self.case_number,
            "decedent": self.decedent,
            "dod": self.de111.date_of_death,
            "spouse": self.de111.spouse_name,
            "spouse_dod": self.de111.spouse_dod,
            "address": addr,
            "apn": self.parcel.apn if self.parcel else "",
            "apn_source": self.parcel.apn_source if self.parcel else "",
            "land_value": self.parcel.land_value if self.parcel else "",
            "structure_value": self.parcel.structure_value if self.parcel else "",
            "own_aod_docs": ";".join(self.dual.own_aod_docs),
            "related_docs": ";".join(self.dual.related_docs),
            "dual_signal": self.dual.dual_signal,
            "score": self.dual.score,
            "reason": self.dual.reason,
            "coverage": self.dual.coverage,
            "hearing_de111": self.hearing_de111,
            "hearing_listing": self.hearing_listing,
            "hearing_mismatch": "yes" if self.hearing_mismatch else "no",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.csv_row(),
            "listing": {
                k: v
                for k, v in self.listing.items()
                if k != "_parsed_name"
            },
            "de111": self.de111.to_dict(),
            "parcel": self.parcel.to_dict() if self.parcel else None,
            "recorder_queries": self.recorder_queries,
            "evidence": self.dual.evidence,
        }


def _since_filter(listings: list[dict], since: str | None) -> list[dict]:
    if not since:
        return listings
    return [
        row
        for row in listings
        if str(row.get("last_seen") or row.get("first_seen") or "") >= since
    ]


def _case_filter(listings: list[dict], case: str | None) -> list[dict]:
    if not case:
        return listings
    wanted = {c.strip() for c in case.split(",") if c.strip()}
    return [row for row in listings if str(row.get("case_number") or "") in wanted]


def search_strategy(
    recorder: RecorderSource,
    parsed: ParsedName,
    *,
    spouse_name: str = "",
    heirs: list[str] | None = None,
    refresh: bool = False,
) -> tuple[list, bool, list[str]]:
    """Surname-wide first; if truncated, LAST FIRST then spouse/heir names."""
    queries: list[str] = []
    all_rows = []
    truncated = False

    surname_q = parsed.last
    queries.append(surname_q)
    surname_result: RecorderSearchResult = recorder.search_name(surname_q, refresh=refresh)
    all_rows.extend(surname_result.rows)
    truncated = surname_result.truncated

    if truncated:
        narrow = parsed.searchable
        if narrow and narrow != surname_q:
            queries.append(narrow)
            r2 = recorder.search_name(narrow, refresh=refresh)
            all_rows.extend(r2.rows)
            truncated = truncated or r2.truncated
        extras = []
        if spouse_name:
            extras.append(spouse_name)
        for heir in heirs or []:
            extras.append(heir)
        for extra in extras:
            q = " ".join(str(extra).upper().split())
            if not q or q in queries:
                continue
            queries.append(q)
            r3 = recorder.search_name(q, refresh=refresh)
            all_rows.extend(r3.rows)

    # Deduplicate rows by doc number.
    seen: set[str] = set()
    unique = []
    for row in all_rows:
        if row.doc_number in seen:
            continue
        seen.add(row.doc_number)
        unique.append(row)
    return unique, truncated, queries


class SweepRunner:
    def __init__(
        self,
        root: Path,
        *,
        fixtures_dir: Path | None = None,
        ha: HAClient | None = None,
        recorder: RecorderSource | None = None,
        listings: list[dict] | None = None,
        max_searches: int = 40,
        refresh: bool = False,
        offline: bool = False,
    ) -> None:
        self.paths = SweepPaths(root)
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self.refresh = refresh
        self.offline = offline or self.fixtures_dir is not None
        self.ha = ha
        self._listings_override = list(listings) if listings is not None else None
        if recorder is not None:
            self.recorder = recorder
        else:
            fixture_recorder = None
            if self.fixtures_dir:
                fixture_recorder = self.fixtures_dir / "recorder"
            self.recorder = PlacerCountyFusionRecorder(
                self.paths.recorder,
                max_searches=max_searches,
                fixture_dir=fixture_recorder if self.offline else None,
            )

    def load_listings(self, *, case: str | None = None, since: str | None = None) -> list[dict]:
        if self._listings_override is not None:
            listings = [
                row
                for row in self._listings_override
                if isinstance(row, dict)
                and str(row.get("source") or "") in {"", "Placer County"}
            ]
        elif self.fixtures_dir:
            path = self.fixtures_dir / "listings" / "listings.json"
            listings = [
                row
                for row in load_listings_fixture(path)
                if str(row.get("source") or "") in {"", "Placer County"}
            ]
        else:
            client = self.ha or HAClient()
            listings = client.fetch_listings(source="Placer County")
        listings = _case_filter(listings, case)
        listings = _since_filter(listings, since)
        return dedupe_listings(listings)

    def _parcel_features_override(self, address: str) -> list[dict] | None:
        if not self.fixtures_dir:
            return None
        parcels_dir = self.fixtures_dir / "parcels"
        if not parcels_dir.is_dir():
            return None
        # Match by street number token in filename or JSON address field.
        num_m = re.match(r"\s*(\d+)", address or "")
        num = num_m.group(1) if num_m else ""
        for path in parcels_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if num and num in path.stem:
                return payload.get("features") or payload.get("results") or []
            if address and address.upper() in json.dumps(payload).upper():
                return payload.get("features") or payload.get("results") or []
        # Fallback: any file that embeds the street number in features.
        if num:
            for path in parcels_dir.glob("*.json"):
                text = path.read_text(encoding="utf-8")
                if num in text:
                    payload = json.loads(text)
                    return payload.get("features") or payload.get("results") or []
        return []

    def process_listing(
        self, listing: dict, *, apn_index: dict[str, list[str]]
    ) -> tuple[CaseResult, list, bool]:
        parsed: ParsedName = listing["_parsed_name"]
        case = str(listing["case_number"])

        # DE-111
        pdf_path = self.paths.de111 / f"{case}.pdf"
        if self.fixtures_dir:
            # Prefer fixture OCR text; optional PDF.
            fix_ocr = self.fixtures_dir / "de111" / f"{case}.ocr.txt"
            cached_ocr = self.paths.de111 / f"{case}.ocr.txt"
            if fix_ocr.exists() and (self.refresh or not cached_ocr.exists()):
                cached_ocr.write_text(fix_ocr.read_text(encoding="utf-8"), encoding="utf-8")
            fix_pdf = self.fixtures_dir / "de111" / f"{case}.pdf"
            if fix_pdf.exists() and not pdf_path.exists():
                pdf_path.write_bytes(fix_pdf.read_bytes())
        elif not self.offline:
            client = self.ha or HAClient()
            client.download_de111(listing, pdf_path, refresh=self.refresh)

        de111 = load_or_ocr(
            case,
            pdf_path if pdf_path.exists() else None,
            self.paths.de111,
            refresh=self.refresh,
        )

        # APN
        addr_de111 = de111.property_address or de111.residence_address
        features = self._parcel_features_override(
            addr_de111 or str(listing.get("decedent_address") or "")
        )
        parcel = resolve_apn(
            de111_property=addr_de111,
            decedent_address=str(listing.get("decedent_address") or ""),
            petitioner_address=str(listing.get("petitioner_address") or ""),
            cache_dir=self.paths.parcels,
            refresh=self.refresh,
            features_override=features if self.offline else None,
        )
        if parcel and parcel.apn:
            apn_index.setdefault(parcel.apn, []).append(case)

        # Recorder
        rows, truncated, queries = search_strategy(
            self.recorder,
            parsed,
            spouse_name=de111.spouse_name,
            heirs=de111.heirs,
            refresh=self.refresh,
        )
        classified = classify_rows(rows)

        result = CaseResult(
            case_number=case,
            decedent=parsed.display,
            listing=listing,
            parsed=parsed,
            de111=de111,
            parcel=parcel,
            recorder_queries=queries,
            truncated=truncated,
            dual=DualSignalResult(
                case_number=case,
                decedent=parsed.display,
                dual_signal="no",
                score=0,
                reason="pending",
                coverage="partial" if truncated else "full",
            ),
            hearing_listing="",
            hearing_de111=de111.hearing_date,
            hearing_mismatch=False,
        )
        return result, classified, truncated

    def run(
        self,
        *,
        case: str | None = None,
        since: str | None = None,
        top_n: int = 25,
    ) -> list[CaseResult]:
        listings = self.load_listings(case=case, since=since)
        log.info("processing %d listings", len(listings))

        # First pass: gather parcels so shared-APN peers are known.
        interim: list[tuple[CaseResult, list, bool]] = []
        apn_index: dict[str, list[str]] = {}
        for listing in listings:
            try:
                result, classified, truncated = self.process_listing(listing, apn_index=apn_index)
                interim.append((result, classified, truncated))
            except Exception:
                log.exception("failed on %s", listing.get("case_number"))

        results: list[CaseResult] = []
        for result, classified, truncated in interim:
            peers: list[str] = []
            if result.parcel and result.parcel.apn:
                peers = [
                    c
                    for c in apn_index.get(result.parcel.apn, [])
                    if c != result.case_number
                ]
            dual = score_dual_signal(
                case_number=result.case_number,
                parsed=result.parsed,
                classified=classified,
                spouse_name=result.de111.spouse_name,
                spouse_deceased=result.de111.spouse_deceased,
                spouse_dod=result.de111.spouse_dod,
                apn=result.parcel.apn if result.parcel else "",
                apn_peers=peers,
                truncated=truncated,
                will_spouse_predeceased=result.de111.spouse_deceased,
            )
            h_list, h_de111, mismatch = hearing_mismatch(
                str(result.listing.get("hearing") or ""),
                result.de111.hearing_date,
            )
            result.dual = dual
            result.hearing_listing = h_list
            result.hearing_de111 = h_de111 or result.de111.hearing_date
            result.hearing_mismatch = mismatch
            results.append(result)

        self.write_outputs(results, top_n=top_n)
        return results

    def write_outputs(self, results: list[CaseResult], *, top_n: int = 25) -> None:
        csv_path = self.paths.out / "affidavit_sweep.csv"
        json_path = self.paths.out / "affidavit_sweep.json"
        leads_path = self.paths.out / "leads.md"

        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in results:
                writer.writerow(row.csv_row())

        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        ranked = sorted(results, key=lambda r: (-r.dual.score, r.case_number))
        leads = [r for r in ranked if r.dual.dual_signal in {"yes", "maybe", "sold"}][:top_n]
        lines = [
            "# Dual Affidavit Leads",
            "",
            f"Generated {payload['generated_at']}. Top {len(leads)} of {len(results)}.",
            "",
            "## Copy-order instructions",
            "",
            "Placer County Recorder copies: **$2** first page, **$1** each page after,",
            "at **3715 Atherton Rd, Rocklin, CA**. Bring document numbers below.",
            "",
        ]
        for i, r in enumerate(leads, 1):
            lines.append(f"## {i}. {r.case_number} — {r.decedent}")
            lines.append("")
            lines.append(f"- Signal: **{r.dual.dual_signal}** (score {r.dual.score})")
            lines.append(f"- Reason: {r.dual.reason}")
            if r.parcel:
                lines.append(
                    f"- APN: `{r.parcel.apn}` ({r.parcel.apn_source}, "
                    f"confidence {r.parcel.confidence}) — not vesting proof"
                )
            if r.dual.own_aod_docs:
                lines.append(f"- Own AOD docs: {', '.join(r.dual.own_aod_docs)}")
            if r.dual.related_docs:
                lines.append(f"- Related docs: {', '.join(r.dual.related_docs)}")
            if r.hearing_mismatch:
                lines.append(
                    f"- Hearing mismatch: listing {r.hearing_listing} vs "
                    f"DE-111 {r.hearing_de111}"
                )
            lines.append("")
        leads_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("wrote %s, %s, %s", csv_path, json_path, leads_path)

    def close(self) -> None:
        close = getattr(self.recorder, "close", None)
        if callable(close):
            close()
