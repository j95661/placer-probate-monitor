#!/usr/bin/env python3
"""Probate lead datasource for the Home Assistant / Follow Up Boss app.

Every county uses Follow Up Boss lead source ``probate`` and tags
``probate`` plus the county name. Callers must merge tags onto a
person (Follow Up Boss ``mergeTags=true``). Sending tags without
that flag replaces the person's whole tag list.
"""

from __future__ import annotations

import io
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

FUB_TAG_PROBATE = "probate"
FUB_LEAD_SOURCE = "probate"

COUNTY_FUB_TAGS = {
    "placer": [FUB_TAG_PROBATE, "placer"],
    "sacramento": [FUB_TAG_PROBATE, "sacramento"],
}

COUNTY_FUB_LEAD_SOURCES = {
    "placer": FUB_LEAD_SOURCE,
    "sacramento": FUB_LEAD_SOURCE,
}


def fub_tags(county: str) -> list[str]:
    key = county.strip().lower()
    try:
        return list(COUNTY_FUB_TAGS[key])
    except KeyError as exc:
        known = ", ".join(sorted(COUNTY_FUB_TAGS))
        raise ValueError(f"Unknown county {county!r}. Known: {known}") from exc


def fub_lead_source(county: str) -> str:
    key = county.strip().lower()
    try:
        return COUNTY_FUB_LEAD_SOURCES[key]
    except KeyError as exc:
        known = ", ".join(sorted(COUNTY_FUB_LEAD_SOURCES))
        raise ValueError(f"Unknown county {county!r}. Known: {known}") from exc


def petition_docs_dir(
    source_id: str | None = None,
    *,
    out_dir: Path | None = None,
    data_dir: Path | None = None,
) -> Path:
    """Directory for downloaded DE-111 / DE-147 PDFs for one county.

    Placer stays at ``reports/docs``. Sacramento is
    ``reports/sacramento/docs`` so HMAC URLs can still look up either folder.
    """
    key = (
        str(source_id or os.environ.get("FUB_DATA_SOURCE") or "placer")
        .strip()
        .lower()
        or "placer"
    )
    if key == "sacramento":
        env = str(os.environ.get("FUB_SACRAMENTO_PETITION_DOCS_DIR") or "").strip()
        if env:
            return Path(env)
        if out_dir is not None:
            return Path(out_dir) / "docs"
        if data_dir is not None:
            return Path(data_dir) / "reports" / "sacramento" / "docs"
        placer_env = str(os.environ.get("FUB_PETITION_DOCS_DIR") or "").strip()
        if placer_env:
            base = Path(placer_env)
            if base.name == "docs":
                return base.parent / "sacramento" / "docs"
            return base / "sacramento" / "docs"
        return Path("data/reports/sacramento/docs")
    env = str(os.environ.get("FUB_PETITION_DOCS_DIR") or "").strip()
    if env:
        return Path(env)
    if out_dir is not None:
        return Path(out_dir) / "docs"
    if data_dir is not None:
        return Path(data_dir) / "reports" / "docs"
    return Path("data/reports/docs")


PDF_MAGIC = b"%PDF"
_SAFE_CASE_RE = re.compile(r"[^\w\-]+")


def case_safe_name(case_number: str) -> str:
    return _SAFE_CASE_RE.sub("_", (case_number or "").strip())


def is_valid_pdf(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        if not path.is_file() or path.stat().st_size <= 4:
            return False
        with path.open("rb") as handle:
            return handle.read(4) == PDF_MAGIC
    except OSError:
        return False


def _compact_doc_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def is_de147s_name(name: str) -> bool:
    return "de147s" in _compact_doc_name(name)


def is_de147_name(name: str) -> bool:
    if is_de147s_name(name):
        return False
    return "de147" in _compact_doc_name(name)


def is_de160_name(name: str) -> bool:
    compact = _compact_doc_name(name)
    if "de147s" in compact:
        return False
    if "de160" in compact or "de161" in compact:
        return True
    return "inventory and appraisal" in (name or "").lower()


def is_de150_name(name: str) -> bool:
    compact = _compact_doc_name(name)
    if "de147s" in compact:
        return False
    return "de150" in compact


def is_de111_name(name: str) -> bool:
    if (
        is_de147s_name(name)
        or is_de147_name(name)
        or is_de160_name(name)
        or is_de150_name(name)
    ):
        return False
    return "de111" in _compact_doc_name(name)


def case_docs_folder(docs_dir: Path, case_number: str) -> Path:
    return Path(docs_dir) / case_safe_name(case_number)


def _iter_case_pdfs(docs_dir: Path, case_number: str) -> list[Path]:
    safe = case_safe_name(case_number)
    if not safe:
        return []
    found: list[Path] = []
    seen: set[str] = set()
    for folder in (Path(docs_dir) / safe, Path(docs_dir)):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.pdf")):
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            found.append(path)
    return found


def local_de111_pdf(docs_dir: Path | None, case_number: str) -> Path | None:
    """Valid on-disk DE-111, or any other public petition PDF in the case folder."""
    if docs_dir is None or not str(case_number or "").strip():
        return None
    base = Path(docs_dir)
    safe = case_safe_name(case_number)
    for path in (
        base / safe / f"{safe}_DE-111.pdf",
        base / f"{safe}_DE-111.pdf",
    ):
        if is_valid_pdf(path) and not is_de147s_name(path.name):
            return path
    fallback = None
    for path in _iter_case_pdfs(base, case_number):
        if (
            not is_valid_pdf(path)
            or is_de147s_name(path.name)
            or is_de147_name(path.name)
            or is_de160_name(path.name)
            or is_de150_name(path.name)
        ):
            continue
        if is_de111_name(path.name):
            return path
        if fallback is None:
            fallback = path
    return fallback


def local_de147_pdf(docs_dir: Path | None, case_number: str) -> Path | None:
    if docs_dir is None or not str(case_number or "").strip():
        return None
    base = Path(docs_dir)
    safe = case_safe_name(case_number)
    for path in (
        base / safe / f"{safe}_DE-147.pdf",
        base / f"{safe}_DE-147.pdf",
    ):
        if is_valid_pdf(path) and not is_de147s_name(path.name):
            return path
    for path in _iter_case_pdfs(base, case_number):
        if is_valid_pdf(path) and is_de147_name(path.name):
            return path
    return None


def local_de160_pdf(docs_dir: Path | None, case_number: str) -> Path | None:
    if docs_dir is None or not str(case_number or "").strip():
        return None
    base = Path(docs_dir)
    safe = case_safe_name(case_number)
    for path in (
        base / safe / f"{safe}_DE-160.pdf",
        base / f"{safe}_DE-160.pdf",
        base / safe / f"{safe}_DE-161.pdf",
        base / f"{safe}_DE-161.pdf",
    ):
        if is_valid_pdf(path) and not is_de147s_name(path.name):
            return path
    for path in _iter_case_pdfs(base, case_number):
        if is_valid_pdf(path) and is_de160_name(path.name):
            return path
    return None


def local_de150_pdf(docs_dir: Path | None, case_number: str) -> Path | None:
    if docs_dir is None or not str(case_number or "").strip():
        return None
    base = Path(docs_dir)
    safe = case_safe_name(case_number)
    for path in (
        base / safe / f"{safe}_DE-150.pdf",
        base / f"{safe}_DE-150.pdf",
    ):
        if is_valid_pdf(path) and not is_de147s_name(path.name):
            return path
    for path in _iter_case_pdfs(base, case_number):
        if is_valid_pdf(path) and is_de150_name(path.name):
            return path
    return None


def local_case_complete(
    docs_dir: Path | None,
    case_number: str,
    *,
    require_duties: bool = False,
) -> bool:
    """True when we already have the petition materials needed to parse/FUB.

    A valid DE-111 (or another public petition PDF in the case folder / docs
    root) is enough for parse/FUB. DE-147 is optional unless ``require_duties``
    is set. Empty folders, non-PDFs, login failures, and Not Viewable-only
    results are incomplete. Confidential DE-147S files never count.
    """
    petition = local_de111_pdf(docs_dir, case_number)
    if petition is None:
        return False
    if require_duties:
        return local_de147_pdf(docs_dir, case_number) is not None
    return True


def _local_decedent_address(docs_dir: Path | None, case_number: str) -> str:
    dest111 = local_de111_pdf(docs_dir, case_number)
    if dest111 is None:
        return ""
    try:
        from .petition_parse import parse_de111_pdf
    except ImportError:
        from petition_parse import parse_de111_pdf
    try:
        parsed = parse_de111_pdf(dest111)
    except Exception:  # noqa: BLE001
        return ""
    return str(parsed.get("decedent_residence") or "").strip()


def missing_petition_forms(docs_dir: Path | None, case_number: str) -> list[str]:
    """Public DE-111 / DE-147 names that are missing or not a valid PDF."""
    missing: list[str] = []
    if local_de111_pdf(docs_dir, case_number) is None:
        missing.append("DE-111")
    if local_de147_pdf(docs_dir, case_number) is None:
        missing.append("DE-147")
    return missing


def listing_source_id(listing: dict | None) -> str:
    rec = listing or {}
    raw = str(rec.get("source_id") or "").strip().lower()
    if raw in ("placer", "sacramento"):
        return raw
    if "sacramento" in str(rec.get("source") or "").lower():
        return "sacramento"
    return "placer"


def listing_skips_form_retry(listing: dict | None) -> bool:
    rec = listing or {}
    return bool(rec.get("fub_removed") or rec.get("professional_fiduciary"))


def listings_missing_petition_forms(
    catalog: dict[str, dict] | None,
    docs_dir: Path | None,
    *,
    source_id: str,
    exclude_cases: Iterable[str] | None = None,
) -> list[str]:
    """Stored listings for this county that still lack DE-111 and/or DE-147."""
    exclude = {str(item).strip() for item in (exclude_cases or []) if str(item).strip()}
    wanted = str(source_id or "").strip().lower() or "placer"
    cases: list[str] = []
    for case, listing in (catalog or {}).items():
        key = str(case or "").strip()
        if not key or key in exclude:
            continue
        rec = listing if isinstance(listing, dict) else {}
        if listing_source_id(rec) != wanted:
            continue
        if listing_skips_form_retry(rec):
            continue
        if missing_petition_forms(docs_dir, key):
            cases.append(key)
    cases.sort()
    return cases


def listing_to_notice(listing: dict, source_id: str):
    """Minimal Notice so an already-captured listing can re-open the docket."""
    try:
        from .placer_probate_monitor import Notice
    except ImportError:
        from placer_probate_monitor import Notice

    rec = listing or {}
    county = "SACRAMENTO" if str(source_id).strip().lower() == "sacramento" else "PLACER"
    return Notice(
        case_number=str(rec.get("case_number") or "").strip(),
        decedent=str(rec.get("decedent") or "").strip(),
        petitioner=str(rec.get("petitioner") or "").strip(),
        court_county=county,
        hearing=str(rec.get("hearing") or "").strip(),
        attorney="",
        attorney_phone="",
        newspaper=str(rec.get("newspaper") or "").strip(),
        post_date=str(rec.get("date") or rec.get("filed") or "").strip(),
        publication_line="",
        will_offered=False,
        iaea_requested=False,
        refcode="",
        advert_id="",
        notice_url=str(rec.get("notice_url") or "").strip(),
        snippet="",
        raw_text="",
        first_seen=False,
        status="repeat",
    )


def saved_petition_form_count(rows: Iterable[dict]) -> int:
    total = 0
    for row in rows:
        for name in row.get("saved_forms") or []:
            if str(name) in ("DE-111", "DE-147"):
                total += 1
    return total


def log_missing_form_retry(rechecked: int, saved: int) -> None:
    print(
        f"Missing DE-111/DE-147 retry: rechecked {rechecked} incomplete cases, "
        f"saved {saved} new documents.",
        flush=True,
    )


def retry_missing_petition_rows(
    *,
    catalog: dict[str, dict] | None,
    docs_dir: Path | None,
    source_id: str,
    exclude_cases: Iterable[str],
    enrich_fn: Callable[[list], list[dict]],
) -> list[dict]:
    """Re-query the public docket for stored listings missing a petition form."""
    cases = listings_missing_petition_forms(
        catalog,
        docs_dir,
        source_id=source_id,
        exclude_cases=exclude_cases,
    )
    if not cases:
        return []
    notices = [
        listing_to_notice((catalog or {}).get(case) or {"case_number": case}, source_id)
        for case in cases
    ]
    print(
        f"Rechecking {len(notices)} stored listings missing DE-111 or DE-147…",
        flush=True,
    )
    rows = enrich_fn(notices)
    try:
        from .fub_client import apply_listing_go
    except ImportError:
        from fub_client import apply_listing_go

    catalog = catalog or {}
    for row in rows:
        case = str(row.get("case_number") or "").strip()
        listing = catalog.get(case) or {}
        overlay_prior_listing(row, listing)
        apply_listing_go(row)
    return rows


def should_reuse_local_case(
    docs_dir: Path | None,
    case_number: str,
    *,
    reuse_local: bool = True,
    refresh_cases: Iterable[str] | None = None,
    decedent_address: str = "",
) -> bool:
    """Skip court when both public forms exist and home address is already known.

    Reuse requires a valid DE-111 and DE-147. Missing either form must reopen
    the docket so the court copy can be downloaded later. Known home means a
    filled decedent address (listing or DE-111 usual residence) or a local
    DE-160 / DE-161. Empty address with no inventory PDF must still reopen
    the public docket so Inventory and Appraisal can be downloaded.
    """
    if not reuse_local or docs_dir is None or not str(case_number or "").strip():
        return False
    refresh = {str(item).strip() for item in (refresh_cases or []) if str(item).strip()}
    if str(case_number).strip() in refresh:
        return False
    if not local_case_complete(docs_dir, case_number, require_duties=True):
        return False
    if local_de160_pdf(docs_dir, case_number) is not None:
        return True
    if str(decedent_address or "").strip():
        return True
    return bool(_local_decedent_address(docs_dir, case_number))


def preview_refresh_case(
    notices: Iterable[Any],
    docs_dir: Path | None,
) -> str:
    """One case for Preview: prefer incomplete local files, else the first case."""
    numbered = [str(getattr(item, "case_number", "") or "").strip() for item in notices]
    numbered = [item for item in numbered if item]
    incomplete = [
        case for case in numbered if not local_case_complete(docs_dir, case)
    ]
    if incomplete:
        return incomplete[0]
    return numbered[0] if numbered else ""


def _blank(value) -> bool:
    """True when a field is unset. Integer/string 0 is present, not blank."""
    return value in (None, "", [], {})


def overlay_prior_listing(portal: dict, listing: dict | None) -> dict:
    if not listing:
        return portal
    mapping = (
        ("court_url", "court_url"),
        ("filed", "filed"),
        ("decedent", "decedent"),
        ("petitioner", "petitioner"),
        ("decedent_address", "decedent_residence"),
        ("petitioner_address", "mailing_address"),
        ("petitioner_phone", "petitioner_phone"),
        ("hearing", "next_event"),
        ("notice_url", "notice_url"),
        ("professional_fiduciary", "professional_fiduciary"),
        ("fub_person_id", "fub_person_id"),
        ("fub_removed", "fub_removed"),
        ("estate_real", "estate_real"),
        ("estate_personal", "estate_personal"),
    )
    try:
        from .petition_parse import stored_person_name
    except ImportError:
        from petition_parse import stored_person_name

    for src, dest in mapping:
        value = listing.get(src)
        if src in ("petitioner", "decedent") and not _blank(value):
            cleaned = stored_person_name(str(value))
            if not cleaned:
                continue
            value = cleaned
        if not _blank(value) and _blank(portal.get(dest)):
            portal[dest] = value
    for key in ("petition_ocr", "petition_ocr_gmv"):
        if listing.get(key) and not portal.get(key):
            portal[key] = True
    engine = str(listing.get("ocr_engine") or "").strip().lower()
    if engine in {"tesseract", "rapidocr"} and _blank(portal.get("ocr_engine")):
        portal["ocr_engine"] = engine
    return portal


def _stamp_petition_ocr(portal: dict, *, gmv: bool = False) -> None:
    portal["petition_ocr"] = True
    if gmv:
        portal["petition_ocr_gmv"] = True
    try:
        from .pdf_ocr import ocr_status
    except ImportError:
        from pdf_ocr import ocr_status

    engine = str((ocr_status() or {}).get("engine") or "").strip().lower()
    if engine in {"tesseract", "rapidocr"}:
        portal["ocr_engine"] = engine


def _stamp_parsed_petition(portal: dict, de111: dict) -> dict:
    try:
        from .petition_parse import stored_person_name
    except ImportError:
        from petition_parse import stored_person_name

    if de111.get("petitioner_name"):
        cleaned = stored_person_name(de111["petitioner_name"])
        if cleaned:
            portal["petitioner"] = cleaned
            de111["petitioner_name"] = cleaned
        else:
            de111.pop("petitioner_name", None)
    parsed_dec = stored_person_name(de111.get("decedent_name"))
    existing_dec = stored_person_name(portal.get("decedent"))
    if parsed_dec:
        de111["decedent_name"] = parsed_dec
    else:
        de111.pop("decedent_name", None)
    portal.update(de111)
    decedent = parsed_dec or existing_dec
    if decedent:
        portal["decedent"] = decedent
    else:
        portal.pop("decedent", None)
    return de111


def apply_stored_petitions(
    portal: dict,
    *,
    docs_dir: Path,
    case_number: str,
    petitioner: str = "",
    verbose: bool = False,
    listing: dict | None = None,
) -> dict:
    """Parse on-disk DE-111 / public DE-147 into portal fields. No download."""
    try:
        from .pdf_ocr import ocr_pdf_text, should_ocr_gmv, should_ocr_needed, should_ocr_petition
        from .petition_parse import (
            clean_person_name,
            contact_fields,
            estate_real_needs_gmv_ocr,
            extract_pdf_text,
            is_fiduciary_petitioner_name,
            merge_petitioner_contact,
            parse_de111_pdf,
            parse_de147_pdf,
            parse_de160_pdf,
            stamp_row_professional_fiduciary,
        )
    except ImportError:
        from pdf_ocr import ocr_pdf_text, should_ocr_gmv, should_ocr_needed, should_ocr_petition
        from petition_parse import (
            clean_person_name,
            contact_fields,
            estate_real_needs_gmv_ocr,
            extract_pdf_text,
            is_fiduciary_petitioner_name,
            merge_petitioner_contact,
            parse_de111_pdf,
            parse_de147_pdf,
            parse_de160_pdf,
            stamp_row_professional_fiduciary,
        )

    de111: dict = {}
    de147: dict = {}
    dest111 = local_de111_pdf(docs_dir, case_number)
    dest147 = local_de147_pdf(docs_dir, case_number)
    de111_text = ""
    de147_text = ""
    if dest111 is not None:
        try:
            de111_text = extract_pdf_text(dest111)
        except Exception:  # noqa: BLE001
            de111_text = ""
        try:
            de111 = parse_de111_pdf(dest111, petitioner=petitioner, text=de111_text)
            de111 = _stamp_parsed_petition(portal, de111)
            portal["petition_pdf"] = str(dest111)
            if verbose:
                print(
                    f"DE-111 {case_number}: "
                    f"mailing={de111.get('mailing_address') or '(empty)'} "
                    f"phone={de111.get('petitioner_phone') or '(empty)'} "
                    f"residence={de111.get('decedent_residence') or '(empty)'}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            portal["petition_parse_error"] = str(exc)
    if dest147 is not None:
        try:
            de147_text = extract_pdf_text(dest147)
        except Exception:  # noqa: BLE001
            de147_text = ""
        try:
            de147 = parse_de147_pdf(dest147, text=de147_text)
            portal["duties_pdf"] = str(dest147)
            if verbose:
                print(
                    f"DE-147 {case_number}: "
                    f"mailing={de147.get('mailing_address') or '(empty)'} "
                    f"phone={de147.get('petitioner_phone') or '(empty)'} "
                    f"email={de147.get('petitioner_email') or '(empty)'}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            portal["duties_parse_error"] = str(exc)
    dest160 = local_de160_pdf(docs_dir, case_number)
    if dest160 is not None:
        try:
            de160 = parse_de160_pdf(dest160, death_place=str(portal.get("death_place") or ""))
            portal["inventory_pdf"] = str(dest160)
            if de160.get("decedent_residence") and not portal.get("decedent_residence"):
                portal.update(de160)
            if verbose:
                print(
                    f"DE-160 {case_number}: "
                    f"residence={de160.get('decedent_residence') or '(empty)'}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            portal["inventory_parse_error"] = str(exc)
    portal["contact_de111"] = contact_fields(de111)
    portal["contact_de147"] = contact_fields(de147)
    contact = merge_petitioner_contact(de111, de147)
    if contact:
        portal.update(contact)
        if verbose:
            print(
                f"contact {case_number}: "
                f"mailing={contact.get('mailing_address') or '(empty)'} "
                f"phone={contact.get('petitioner_phone') or '(empty)'} "
                f"email={contact.get('petitioner_email') or '(empty)'}",
                flush=True,
            )
    if de111.get("professional_fiduciary") or is_fiduciary_petitioner_name(
        str(portal.get("petitioner") or petitioner or "")
    ) or is_fiduciary_petitioner_name(str(de111.get("item2b_name") or "")):
        portal["professional_fiduciary"] = True
    stamp_row_professional_fiduciary(portal)
    parsed_for_ocr = dict(contact or {})
    parsed_for_ocr.update(de111)
    if listing:
        for key in (
            "petitioner",
            "petitioner_name",
            "petitioner_first",
            "petitioner_last",
            "petitioner_address",
            "mailing_address",
            "decedent_address",
            "decedent_residence",
            "estate_real",
            "estate_personal",
            "fub_removed",
            "professional_fiduciary",
        ):
            if not _blank(listing.get(key)) and _blank(parsed_for_ocr.get(key)):
                parsed_for_ocr[key] = listing.get(key)
            if key in {"estate_real", "estate_personal"} and not _blank(
                listing.get(key)
            ) and _blank(portal.get(key)):
                portal[key] = listing.get(key)
    if portal.get("professional_fiduciary"):
        parsed_for_ocr["professional_fiduciary"] = True
    if should_ocr_needed(
        listing=listing,
        parsed=parsed_for_ocr,
        native_text=de111_text,
    ) and dest111 is not None:
        ocr111 = ocr_pdf_text(dest111)
        if ocr111.strip():
            try:
                de111 = parse_de111_pdf(dest111, petitioner=petitioner, text=ocr111)
                de111 = _stamp_parsed_petition(portal, de111)
                _stamp_petition_ocr(portal)
                if de111.get("item2b_name") and not str(portal.get("petitioner") or "").strip():
                    portal["petitioner"] = (
                        clean_person_name(de111["item2b_name"])
                        or de111["item2b_name"]
                    )
                if verbose:
                    print(
                        f"DE-111 OCR {case_number}: "
                        f"chars={len(ocr111)} "
                        f"mailing={de111.get('mailing_address') or '(empty)'} "
                        f"gmv={de111.get('estate_real') or '(empty)'} "
                        f"residence={de111.get('decedent_residence') or '(empty)'}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                portal["petition_ocr_error"] = str(exc)
        contact = merge_petitioner_contact(de111, de147)
        if contact:
            portal.update(contact)
        parsed_for_ocr = dict(contact or {})
        parsed_for_ocr.update(de111)
    if should_ocr_petition(
        listing=listing,
        parsed=parsed_for_ocr,
        native_text=de147_text,
    ) and dest147 is not None:
        ocr147 = ocr_pdf_text(dest147)
        if ocr147.strip():
            try:
                de147 = parse_de147_pdf(dest147, text=ocr147)
                portal["duties_ocr"] = True
                _stamp_petition_ocr(portal)
                if verbose:
                    print(
                        f"DE-147 OCR {case_number}: "
                        f"chars={len(ocr147)} "
                        f"mailing={de147.get('mailing_address') or '(empty)'} "
                        f"phone={de147.get('petitioner_phone') or '(empty)'} "
                        f"email={de147.get('petitioner_email') or '(empty)'}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                portal["duties_ocr_error"] = str(exc)
        contact = merge_petitioner_contact(de111, de147)
        if contact:
            portal.update(contact)
        parsed_for_ocr = dict(contact or {})
        parsed_for_ocr.update(de111)
        if portal.get("professional_fiduciary"):
            parsed_for_ocr["professional_fiduciary"] = True
    if should_ocr_gmv(
        listing=listing,
        parsed=parsed_for_ocr,
        native_text=de111_text,
    ) and dest111 is not None:
        ocr_gmv = ocr_pdf_text(dest111)
        if ocr_gmv.strip():
            try:
                gmv_parsed = parse_de111_pdf(dest111, petitioner=petitioner, text=ocr_gmv)
                real = gmv_parsed.get("estate_real")
                if not _blank(real) and (
                    _blank(portal.get("estate_real"))
                    or (
                        estate_real_needs_gmv_ocr(portal.get("estate_real"))
                        and not estate_real_needs_gmv_ocr(real)
                    )
                ):
                    de111["estate_real"] = real
                    portal["estate_real"] = real
                personal = gmv_parsed.get("estate_personal")
                if not _blank(personal) and _blank(portal.get("estate_personal")):
                    de111["estate_personal"] = personal
                    portal["estate_personal"] = personal
                _stamp_petition_ocr(portal, gmv=True)
                if verbose:
                    print(
                        f"DE-111 GMV OCR {case_number}: "
                        f"estate_real={portal.get('estate_real') or '(empty)'}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                portal["petition_ocr_gmv_error"] = str(exc)
    portal["contact_de111"] = contact_fields(de111)
    portal["contact_de147"] = contact_fields(de147)
    if de111.get("professional_fiduciary") or is_fiduciary_petitioner_name(
        str(portal.get("petitioner") or petitioner or "")
    ) or is_fiduciary_petitioner_name(str(de111.get("item2b_name") or "")):
        portal["professional_fiduciary"] = True
    stamp_row_professional_fiduciary(portal)
    return portal


def public_download_items(
    portal: dict,
) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    """Public petition, duties, inventory, and issued letters. Never DE-147S."""
    try:
        from .petition_parse import (
            looks_like_duties_form,
            looks_like_inventory_form,
            looks_like_issued_letters,
            looks_like_probate_petition,
        )
    except ImportError:
        from petition_parse import (
            looks_like_duties_form,
            looks_like_inventory_form,
            looks_like_issued_letters,
            looks_like_probate_petition,
        )

    petition_item = None
    duties_item = None
    inventory_item = None
    letters_item = None
    for item in portal.get("document_files") or []:
        if not item.get("available") or not item.get("url"):
            continue
        name = str(item.get("name") or "")
        if is_de147s_name(name) or "confidential" in name.lower():
            continue
        if looks_like_probate_petition(name) and petition_item is None:
            petition_item = item
        if looks_like_duties_form(name) and duties_item is None:
            duties_item = item
        if looks_like_inventory_form(name) and inventory_item is None:
            inventory_item = item
        if looks_like_issued_letters(name):
            letters_item = item
    return petition_item, duties_item, inventory_item, letters_item


def download_missing_public_pdfs(
    portal: dict,
    *,
    docs_dir: Path,
    case_number: str,
    download: Callable[[str, Path], Any],
    pause: float = 0,
    skip_download: bool = False,
    sleeper: Callable[[float], Any] | None = None,
) -> list[str]:
    """Download only missing/invalid public petition forms. Never DE-147S."""
    sleep = sleeper or time.sleep
    saved: list[str] = []
    portal["saved_forms"] = saved
    if skip_download or not portal.get("found") or not str(case_number or "").strip():
        return saved
    petition_item, duties_item, inventory_item, letters_item = public_download_items(
        portal
    )
    case_dir = case_docs_folder(docs_dir, case_number)
    safe = case_safe_name(case_number)
    dest111 = case_dir / f"{safe}_DE-111.pdf"
    dest147 = case_dir / f"{safe}_DE-147.pdf"
    dest160 = case_dir / f"{safe}_DE-160.pdf"
    dest150 = case_dir / f"{safe}_DE-150.pdf"
    jobs = (
        (petition_item, dest111, "DE-111", "petition_url", "petition_parse_error", local_de111_pdf),
        (duties_item, dest147, "DE-147", "duties_url", "duties_parse_error", local_de147_pdf),
        (inventory_item, dest160, "DE-160", "inventory_url", "inventory_parse_error", local_de160_pdf),
        (letters_item, dest150, "DE-150", "letters_url", "letters_parse_error", local_de150_pdf),
    )
    for item, dest, kind, url_key, err_key, local_fn in jobs:
        if not item or not item.get("url"):
            continue
        if local_fn(docs_dir, case_number) is not None:
            continue
        try:
            sleep(float(pause or 0))
            download(str(item["url"]), dest)
            portal[url_key] = item["url"]
        except Exception as exc:  # noqa: BLE001
            portal[err_key] = str(exc)
        if dest.is_file() and not is_valid_pdf(dest):
            portal[err_key] = "download was not a PDF"
        elif is_valid_pdf(dest):
            saved.append(kind)
    portal["saved_forms"] = saved
    return saved


def _case_from_pdf_name(name: str) -> str:
    stem = Path(name).stem
    upper = stem.upper()
    for token in (
        "_DE-111",
        "_DE-147",
        "_DE-150",
        "_DE-160",
        "_DE-161",
        "_DE111",
        "_DE147",
        "_DE150",
        "_DE160",
        "_DE161",
    ):
        idx = upper.find(token)
        if idx > 0:
            return stem[:idx]
    return stem


def iter_local_case_numbers(docs_dir: Path | None) -> list[str]:
    """Case numbers that already have a public petition or duties PDF on disk."""
    if docs_dir is None:
        return []
    base = Path(docs_dir)
    if not base.is_dir():
        return []
    cases: set[str] = set()
    for child in base.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir():
            name = child.name.strip()
            if name:
                cases.add(name)
            continue
        if child.suffix.lower() != ".pdf" or is_de147s_name(child.name):
            continue
        case = _case_from_pdf_name(child.name).strip()
        if case:
            cases.add(case)
    return sorted(
        case
        for case in cases
        if local_de111_pdf(base, case) or local_de147_pdf(base, case)
    )


def listed_case_pdfs(docs_dir: Path | None, case_number: str) -> list[str]:
    """Public on-disk PDF filenames for one case. Skips DE-147S / invalid files."""
    names: list[str] = []
    seen: set[str] = set()
    for path in _iter_case_pdfs(docs_dir or Path(), case_number):
        if not is_valid_pdf(path) or is_de147s_name(path.name):
            continue
        if path.name in seen:
            continue
        seen.add(path.name)
        names.append(path.name)
    return names


STORED_DOCS_RELATIVE = {
    "placer": "reports/docs",
    "sacramento": "reports/sacramento/docs",
}
STORED_DOCS_ZIP_URL = "/api/placer_probate_monitor/stored_docs/zip"
STORED_DOCS_FILE_URL = "/api/placer_probate_monitor/stored_docs/file"


def _posix_join(*parts: str) -> str:
    return "/".join(str(part).replace("\\", "/").strip("/") for part in parts if str(part).strip("/"))


def iter_stored_pdf_members(
    data_dir: Path, source_id: str | None = None
) -> list[tuple[str, Path]]:
    """Public stored PDFs as (zip member path, absolute file)."""
    root = Path(data_dir).resolve()
    wanted = str(source_id or "").strip().lower()
    keys = [wanted] if wanted in STORED_DOCS_RELATIVE else list(STORED_DOCS_RELATIVE)
    members: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for key in keys:
        relative = STORED_DOCS_RELATIVE[key]
        docs = petition_docs_dir(key, data_dir=root).resolve()
        try:
            docs.relative_to(root)
        except ValueError:
            continue
        for case in iter_local_case_numbers(docs):
            safe = case_safe_name(case)
            if not safe:
                continue
            for name in listed_case_pdfs(docs, case):
                filename = Path(name).name
                if filename != name or is_de147s_name(filename):
                    continue
                path = None
                for candidate in (docs / safe / filename, docs / filename):
                    try:
                        resolved = candidate.resolve()
                        resolved.relative_to(docs)
                    except (OSError, ValueError):
                        continue
                    if is_valid_pdf(resolved):
                        path = resolved
                        break
                if path is None:
                    continue
                member = _posix_join(relative, safe, filename)
                if member in seen:
                    continue
                seen.add(member)
                members.append((member, path))
    return members


def build_stored_pdfs_zip(data_dir: Path, source_id: str | None = None) -> bytes:
    """Zip public stored petition PDFs. Empty bytes when nothing is on disk."""
    members = iter_stored_pdf_members(data_dir, source_id)
    if not members:
        return b""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, path in members:
            archive.write(path, arcname=member)
    return buf.getvalue()


def resolve_stored_pdf_file(
    data_dir: Path, source_id: str, case_number: str, filename: str
) -> Path | None:
    """One inventoried public PDF. Rejects path traversal and DE-147S files."""
    key = str(source_id or "").strip().lower()
    if key not in STORED_DOCS_RELATIVE:
        return None
    name = Path(str(filename or "")).name
    raw = str(filename or "")
    if name != raw or not name.lower().endswith(".pdf") or is_de147s_name(name):
        return None
    root = Path(data_dir).resolve()
    docs = petition_docs_dir(key, data_dir=root).resolve()
    try:
        docs.relative_to(root)
    except ValueError:
        return None
    if name not in listed_case_pdfs(docs, case_number):
        return None
    safe = case_safe_name(case_number)
    if not safe:
        return None
    for candidate in (docs / safe / name, docs / name):
        try:
            path = candidate.resolve()
            path.relative_to(docs)
        except (OSError, ValueError):
            continue
        if is_valid_pdf(path):
            return path
    return None


def safe_extract_stored_zip(blob: bytes, dest_dir: Path) -> list[str]:
    """Extract ``reports/*.pdf`` zip members into dest_dir. Returns relative paths."""
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = Path(name).parts
            if not name or ".." in parts or name.startswith("/"):
                continue
            if not name.startswith("reports/") or not name.lower().endswith(".pdf"):
                continue
            if is_de147s_name(Path(name).name):
                continue
            target = (dest / name).resolve()
            try:
                target.relative_to(dest)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as out:
                out.write(src.read())
            written.append(name)
    return written


def stored_docs_inventory(docs_dir: Path | None, source_id: str, *, relative_dir: str) -> dict:
    """Case/PDF inventory for one county docs folder. No court or CNPA."""
    cases: list[dict[str, Any]] = []
    pdf_count = 0
    for case in iter_local_case_numbers(docs_dir):
        files = listed_case_pdfs(docs_dir, case)
        pdf_count += len(files)
        cases.append(
            {
                "case_number": case,
                "files": files,
                "has_de111": local_de111_pdf(docs_dir, case) is not None,
                "has_de147": local_de147_pdf(docs_dir, case) is not None,
                "has_de150": local_de150_pdf(docs_dir, case) is not None,
            }
        )
    key = str(source_id or "").strip().lower() or "placer"
    return {
        "id": key,
        "relative_dir": relative_dir,
        "ha_path": f"config/placer_probate_monitor/{relative_dir}",
        "laptop_path": f"data/{relative_dir}",
        "download_zip": f"{STORED_DOCS_ZIP_URL}?source_id={key}",
        "case_count": len(cases),
        "pdf_count": pdf_count,
        "cases": cases,
    }


def all_stored_docs_inventory(data_dir: Path) -> dict:
    """All downloaded petition PDFs already on this Home Assistant box."""
    root = Path(data_dir)
    counties = [
        stored_docs_inventory(
            petition_docs_dir("placer", data_dir=root),
            "placer",
            relative_dir="reports/docs",
        ),
        stored_docs_inventory(
            petition_docs_dir("sacramento", data_dir=root),
            "sacramento",
            relative_dir="reports/sacramento/docs",
        ),
    ]
    return {
        "ha_root": "config/placer_probate_monitor",
        "download_zip": STORED_DOCS_ZIP_URL,
        "copy_hint": (
            "These PDFs are already on Home Assistant. Download the zip from "
            "this page (signed in) or run scripts/pull_stored_pdfs.py with a "
            "long-lived access token. Extract into the laptop data/ folder so "
            "parsers read data/reports/docs and data/reports/sacramento/docs. "
            "Test stored data on this box reads the same files in place and "
            "does not scrape CNPA or court portals."
        ),
        "counties": counties,
        "case_count": sum(int(item.get("case_count") or 0) for item in counties),
        "pdf_count": sum(int(item.get("pdf_count") or 0) for item in counties),
    }


def rescan_local_rows(
    source_id: str,
    docs_dir: Path | None,
    listings_catalog: dict[str, dict] | None = None,
) -> list[dict]:
    """Re-parse on-disk PDFs into dossier rows. Does not call CNPA or court."""
    catalog = listings_catalog or {}
    rows: list[dict] = []
    if docs_dir is None:
        return rows
    try:
        from .pdf_ocr import ensure_ocr_packages
    except ImportError:
        from pdf_ocr import ensure_ocr_packages

    ensure_ocr_packages()
    for case in iter_local_case_numbers(docs_dir):
        listing = catalog.get(case) or {}
        portal: dict[str, Any] = {
            "found": True,
            "reused_local": True,
            "rescanned_local": True,
            "court_fetch": False,
            "case_number": case,
        }
        overlay_prior_listing(portal, listing)
        apply_stored_petitions(
            portal,
            docs_dir=Path(docs_dir),
            case_number=case,
            petitioner=str(listing.get("petitioner") or portal.get("petitioner") or ""),
            verbose=True,
            listing=listing,
        )
        overlay_prior_listing(portal, listing)
        row: dict[str, Any] = {
            "case_number": case,
            "advert_id": "",
            "decedent": listing.get("decedent") or "",
            "petitioner": listing.get("petitioner") or "",
            "court_county": "Sacramento" if source_id == "sacramento" else "Placer",
            "hearing": listing.get("hearing") or "",
            "attorney": "",
            "attorney_phone": "",
            "newspaper": listing.get("newspaper") or "",
            "post_date": listing.get("date") or "",
            "publication_line": "",
            "will_offered": False,
            "iaea_requested": False,
            "refcode": "",
            "notice_url": listing.get("notice_url") or "",
            "snippet": "",
            "raw_text": "",
            "source_id": source_id,
            "first_seen": False,
            "status": "repeat",
        }
        merged = {key: value for key, value in portal.items() if value not in (None, "", [], {})}
        if "status" in merged and "court_status" not in merged:
            merged["court_status"] = merged.pop("status")
        else:
            merged.pop("status", None)
        row.update(merged)
        row["status"] = "repeat"
        row["first_seen"] = False
        row["found"] = True
        row["court_fetch"] = False
        row["rescanned_local"] = True
        row["reused_local"] = True
        if not row.get("filed"):
            row["filed"] = portal.get("filed") or listing.get("filed") or ""
        rows.append(row)
        print(f"Local rescan {case}: court skipped", flush=True)
    return rows


def stamp_fub_tags(rows: list[dict], county: str) -> list[dict]:
    tags = fub_tags(county)
    key = county.strip().lower()
    lead_source = fub_lead_source(key) if key in COUNTY_FUB_LEAD_SOURCES else ""
    for row in rows:
        row["tags"] = list(tags)
        row["source_id"] = key if key in COUNTY_FUB_TAGS else county
        if lead_source:
            row["lead_source"] = lead_source
    return rows


def collect_leads(
    county: str,
    *,
    lookback_days: int = 21,
    lookahead_days: int = 21,
    skip_portal: bool = False,
    public_reports_lookback_days: int = 2,
) -> list[dict[str, Any]]:
    """Return dossier rows for one county. Does not email or update seen-cases.

    Sacramento CNPA uses lookback_days/lookahead_days. Node/415 uses
    public_reports_lookback_days (lookahead always 0) and is unused for Placer.
    """
    try:
        from .placer_probate_monitor import dedupe, default_window, paginate
    except ImportError:
        from placer_probate_monitor import dedupe, default_window, paginate

    key = county.strip().lower()
    start, end = default_window(lookback_days, lookahead_days)
    if key == "sacramento":
        from dataclasses import asdict

        try:
            from .sacramento_probate_monitor import (
                collect_sacramento_cnpa_notices,
                enrich_notices,
                hydrate_notice,
                keep_sacramento_notices,
                needs_advert,
                sacramento_cnpa_candidates,
            )
        except ImportError:
            from sacramento_probate_monitor import (
                collect_sacramento_cnpa_notices,
                enrich_notices,
                hydrate_notice,
                keep_sacramento_notices,
                needs_advert,
                sacramento_cnpa_candidates,
            )

        notices, _urls, scoped_keys = collect_sacramento_cnpa_notices(start, end)
        unique = dedupe(notices)
        candidates = sacramento_cnpa_candidates(unique, scoped_keys)
        for notice in candidates:
            if needs_advert(notice):
                notice.source_note = hydrate_notice(notice)
        unique = keep_sacramento_notices(candidates, scoped_keys)
        if not skip_portal:
            try:
                from .sacramento_probate_monitor import (
                    collect_public_report_notices,
                    public_reports_filing_window,
                )
            except ImportError:
                from sacramento_probate_monitor import (
                    collect_public_report_notices,
                    public_reports_filing_window,
                )

            pr_start, pr_end = public_reports_filing_window(
                public_reports_lookback_days
            )
            unique = collect_public_report_notices(unique, pr_start, pr_end)
        if skip_portal:
            rows = [asdict(notice) for notice in unique]
            for row, notice in zip(rows, unique):
                note = getattr(notice, "source_note", "")
                if note:
                    row["extra_flag"] = note
        else:
            rows = enrich_notices(
                unique,
                docs_dir=petition_docs_dir("sacramento"),
                reuse_local=True,
            )
        return stamp_fub_tags(rows, "Sacramento")
    if key == "placer":
        from dataclasses import asdict

        try:
            from .placer_probate_monitor import (
                enrich_notices,
                hydrate_notice,
                keep_placer_notices,
                needs_advert,
            )
        except ImportError:
            from placer_probate_monitor import (
                enrich_notices,
                hydrate_notice,
                keep_placer_notices,
                needs_advert,
            )

        notices, _urls = paginate(start, end)
        unique = dedupe(notices)
        for notice in unique:
            if needs_advert(notice) and not notice.case_number:
                notice.source_note = hydrate_notice(notice)
        unique = keep_placer_notices(unique)
        unique = dedupe(unique)
        if skip_portal:
            rows = [asdict(notice) for notice in unique]
        else:
            rows = enrich_notices(
                unique,
                year=start.year,
                docs_dir=petition_docs_dir("placer"),
                reuse_local=True,
            )
        return stamp_fub_tags(rows, "Placer")
    raise ValueError(f"Unknown county {county!r}. Known: placer, sacramento")
