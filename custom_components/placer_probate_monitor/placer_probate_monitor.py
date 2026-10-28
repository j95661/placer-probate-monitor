#!/usr/bin/env python3
"""Daily Placer County probate-notice monitor.

Pulls CNPA public notices for "NOTICE OF PETITION TO ADMINISTER ESTATE"
in Placer County, extracts structured fields, tracks first-seen cases,
and emails an HTML + text report only for new GO contacts.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import smtplib
import ssl
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


def _progress(step: str, message: str, **extra) -> None:
    try:
        from .job_progress import report_progress
    except ImportError:
        from job_progress import report_progress

    report_progress(step, message, **extra)

def get_tz():
    return ZoneInfo(os.environ.get("PROBATE_TZ", "America/Los_Angeles"))
BASE_SEARCH = "https://www.capublicnotice.com/search/query"
NOTICE_HOME = "https://www.capublicnotice.com"
USER_AGENT = (
    "PlacerProbateMonitor/1.0 "
    "(personal research; +local daily digest)"
)
# Placer eCourt uses S-PR-0014270. CNPA ads often print SPR0014270 / S-PR0014270.
CASE_RE = re.compile(r"\bS[\s\-]*PR[\s\-]*0*(\d{3,8})\b", re.I)
PLACER_COURT_RE = re.compile(r"COUNTY OF\s+PLACER", re.I)
OTHER_COURT_RE = re.compile(
    r"COUNTY OF\s+(NEVADA|SACRAMENTO|EL DORADO|YOLO|SUTTER|BUTTE|SAN JOAQUIN)\b",
    re.I,
)
ESTATE_RE = re.compile(
    r"NOTICE OF PETITION TO ADMINISTER ESTATE OF:?\s+"
    r"(?P<name>.+?)(?:\s+CASE\s+(?:NO\.?|NUMBER)|\s+\d+\.\s+To all heirs)",
    re.I | re.S,
)
AKA_LINE_RE = re.compile(
    r"interested in the will or estate, or both,?\s+of[:,]?\s*"
    r"(?P<name>.+?)"
    r"(?=\s*\d+\.\s|\s+A PETITION|\s+THE PETITION|\s*$)",
    re.I | re.S,
)
PETITIONER_RE = re.compile(
    r"(?:A PETITION FOR PROBATE has been filed by|PETITION FOR PROBATE has been filed by)\s*:?\s*"
    r"(?P<name>.+?)\s+in the Superior Court",
    re.I | re.S,
)
COURT_RE = re.compile(
    r"Superior Court of California,\s*County of\s+(?P<county>[A-Z ]+)",
    re.I,
)
HEARING_RE = re.compile(
    r"A HEARING on the petition will be held in this court as follows:\s*"
    r"(?P<when>.+?)"
    r"(?=\s+\d+\.\s+IF YOU OBJECT|\s+IF YOU OBJECT|\s*$)",
    re.I | re.S,
)
ATTORNEY_RE = re.compile(
    r"(?:Attorney for Petitioner|ATTORNEY FOR PETITIONER)\s*:?\s*"
    r"(?P<atty>.+?)"
    r"(?=\s*(?:Telephone|Phone(?:\s*No\.)?|Tel)\s*:|\s*PUBLISHED\b|\s*$)",
    re.I | re.S,
)
PUBLISHED_RE = re.compile(r"PUBLISHED IN\s+(?P<pub>.+)", re.I)
WILL_RE = re.compile(r"will and codicils, if any, be admitted to probate", re.I)
IAEA_RE = re.compile(r"Independent Administration of Estates Act", re.I)
PHONE_RE = re.compile(
    r"(?:Phone(?:\s*No\.)?|Telephone|Tel)\s*:\s*([0-9().\-\s]{7,20})",
    re.I,
)


@dataclass
class Notice:
    case_number: str
    decedent: str
    petitioner: str
    court_county: str
    hearing: str
    attorney: str
    attorney_phone: str
    newspaper: str
    post_date: str
    publication_line: str
    will_offered: bool
    iaea_requested: bool
    refcode: str
    advert_id: str
    notice_url: str
    snippet: str
    raw_text: str
    extra_flag: str = ""
    source_note: str = ""
    first_seen: bool = False
    status: str = "repeat"  # new | repeat | missing_case

    def sort_key(self) -> tuple:
        return (0 if self.first_seen else 1, self.post_date or "", self.case_number)


def today_local() -> date:
    return datetime.now(get_tz()).date()


def default_window(lookback_days: int, lookahead_days: int) -> tuple[date, date]:
    start = today_local() - timedelta(days=lookback_days)
    end = today_local() + timedelta(days=lookahead_days)
    return start, end


def search_url(
    start: date,
    end: date,
    page: int = 0,
    size: int = 24,
    county: str | None = None,
    keywords: str | None = None,
) -> str:
    params = {
        "page": page,
        "size": size,
        "view": "list",
        "showExtended": "false",
        "startRange": "",
        "keywords": keywords
        or os.environ.get(
            "PROBATE_KEYWORDS", '"NOTICE OF PETITION TO ADMINISTER ESTATE"'
        ),
        "firstDate": start.strftime("%m/%d/%Y"),
        "lastDate": end.strftime("%m/%d/%Y"),
        "_categories": "1",
        "ordering": "BY_DATE_DEC",
    }
    # county="" omits CNPA's newspaper-county filter. None uses PROBATE_COUNTY.
    if county is None:
        params["county"] = os.environ.get("PROBATE_COUNTY", "Placer")
    elif county != "":
        params["county"] = county
    return f"{BASE_SEARCH}?{urlencode(params)}"


def cnpa_page_sequence(max_fetch: int) -> list[int]:
    """Unique CNPA query pages.

    The site treats ``page=0`` and ``page=1`` as the same first result page.
    Later unique pages are 2, 3, … matching ``loadMore()`` (hidden #page + 1).
    """
    fetch = max(1, int(max_fetch))
    if fetch == 1:
        return [0]
    return [0] + list(range(2, fetch + 1))


def parse_cnpa_max_pages(html_text: str) -> int | None:
    match = re.search(r"var maxPages = ['\"](\d+)['\"]", html_text or "")
    if not match:
        return None
    return max(1, int(match.group(1)))


def fetch_page(url: str, timeout: int = 45) -> str:
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" ,;.")
    value = re.sub(r"\s+\d+\.\s*$", "", value)
    return value.strip(" ,;.")


def normalize_post_date(value: str) -> str:
    """Store publication dates as YYYY-MM-DD so they sort across years."""
    raw = re.sub(r"\s+", " ", value or "").strip()
    if not raw:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def http_url(value: str) -> str:
    text = (value or "").strip()
    if re.match(r"^https?://", text, re.I):
        return text
    return ""


def first_match(pattern: re.Pattern, text: str, group: str | int = 0) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    if isinstance(group, str):
        return clean_name(m.group(group))
    return clean_name(m.group(group))


def extract_decedent(text: str) -> str:
    aka = first_match(AKA_LINE_RE, text, "name")
    if aka:
        return aka.rstrip(",")
    header = first_match(ESTATE_RE, text, "name")
    return header


def extract_case(text: str) -> str:
    matches = CASE_RE.findall(text or "")
    if not matches:
        return ""
    return f"S-PR-{int(matches[-1]):07d}"


def is_placer_court_notice(notice: Notice) -> bool:
    """True when the published notice names Placer Superior Court."""
    court = re.sub(r"\s+", " ", str(notice.court_county or "")).strip().upper()
    if court.startswith("PLACER"):
        return True
    blob = " ".join(
        part for part in (notice.raw_text, notice.snippet, notice.court_county) if part
    )
    return bool(PLACER_COURT_RE.search(blob))


def keep_placer_notices(notices: list[Notice]) -> list[Notice]:
    """Drop ads that name a different superior court (Nevada source is removed)."""
    kept: list[Notice] = []
    for notice in notices:
        case = str(notice.case_number or "").strip().upper()
        if case.startswith("S-PR-") or is_placer_court_notice(notice):
            kept.append(notice)
            continue
        blob = " ".join(
            part
            for part in (notice.raw_text, notice.snippet, notice.court_county)
            if part
        )
        court = re.sub(r"\s+", " ", str(notice.court_county or "")).strip().upper()
        if court and not court.startswith("PLACER"):
            continue
        if OTHER_COURT_RE.search(blob):
            continue
        kept.append(notice)
    return kept


def needs_advert(notice: Notice) -> bool:
    raw = notice.raw_text or ""
    return bool(notice.advert_id) and (
        len(raw) < 500 or "IF YOU OBJECT" not in raw.upper() or not notice.case_number
    )


def hydrate_notice(notice: Notice, case_extractor=None) -> str:
    """Read the CNPA advert page when the search card is truncated or has no case #."""
    extractor = case_extractor or extract_case
    if not needs_advert(notice):
        return ""
    try:
        page = fetch_page(notice.notice_url)
    except requests.RequestException as exc:
        return f"CNPA list text was cut off and the advert page did not load ({exc})."
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page, "html.parser")
    chunks = []
    for el in soup.select(".description, .panel-body"):
        text = el.get_text("\n", strip=True)
        fields = notice_fields(text, extractor)
        if fields.get("raw_text"):
            chunks.append(fields["raw_text"])
    full = max(chunks, key=len) if chunks else ""
    if len(full) <= len(notice.raw_text or ""):
        # Still apply extractor to the longer page text even if notice_fields
        # already ran on the card — SPR / dashed case numbers may appear only here.
        page_text = soup.get_text("\n", strip=True)
        case = extractor(page_text)
        if case and not notice.case_number:
            notice.case_number = case
            notice.status = "repeat"
            return "Search card had no court case number; it was read from the CNPA advert page."
        return "CNPA list text was cut off and the advert page had no longer notice."
    fields = notice_fields(full, extractor)
    if not fields:
        case = extractor(full)
        if case and not notice.case_number:
            notice.case_number = case
            notice.status = "repeat"
            return "Search card had no court case number; it was read from the CNPA advert page."
        return "CNPA list text was cut off and the advert page had no longer notice."
    for key, value in fields.items():
        setattr(notice, key, value)
    return "Search card was shortened; full notice text was read from the CNPA advert page."


def normalize_notice_text(raw: str) -> str:
    """Put spaces back into ads whose HTML glues words together."""
    text = raw or ""
    text = re.sub(r"TOADMINISTER", "TO ADMINISTER", text, flags=re.I)
    text = re.sub(r"(\d{2}PR\d{3,8})(?=[A-Za-z])", r"\1 ", text, flags=re.I)
    text = re.sub(r"([,:;])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"([a-z]{2})\.([A-Za-z])", r"\1. \2", text)
    text = re.sub(r"\.(\d)", r". \1", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([a-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)(am|pm)\b", r"\1 \2", text, flags=re.I)
    text = re.sub(r"\b(am|pm)(?=in\b)", r"\1 ", text, flags=re.I)
    text = re.sub(r"(?<![\d])(?<!PR)(\d{3,})([A-Z][a-z]{2,})", r"\1 \2", text)
    text = re.sub(r"([A-Z]{2})([a-z])", r"\1 \2", text)
    text = re.sub(r"\bOF(?!FICE\b|FICIAL\b|TEN\b)([A-Z]{3,})", r"OF \1", text)
    text = re.sub(r"([A-Z])(CASE\s+NO)", r"\1 \2", text)
    return text


def trailing_publication(raw: str) -> str:
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    if re.search(r"\b20\d{2}\b", last) and "attorney" not in last.lower() and len(last) < 80:
        return last
    return ""


def notice_fields(raw: str, case_extractor=None) -> dict:
    extractor = case_extractor or extract_case
    raw = normalize_notice_text(raw or "")
    raw_flat = re.sub(r"[ \t]+", " ", raw)
    if "PETITION TO ADMINISTER ESTATE" not in raw_flat.upper():
        return {}
    atty = first_match(ATTORNEY_RE, raw, "atty")
    phone = first_match(PHONE_RE, raw, 1)
    if not phone:
        phone_m = re.search(r"(\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4})", atty)
        phone = phone_m.group(1) if phone_m else ""
    case_number = extractor(raw_flat)
    publication = first_match(PUBLISHED_RE, raw_flat, "pub") or trailing_publication(raw)
    try:
        from .petition_parse import clean_person_name
    except ImportError:
        from petition_parse import clean_person_name

    petitioner = clean_person_name(first_match(PETITIONER_RE, raw_flat, "name"))
    return {
        "case_number": case_number,
        "decedent": extract_decedent(raw_flat),
        "petitioner": petitioner,
        "court_county": first_match(COURT_RE, raw_flat, "county"),
        "hearing": first_match(HEARING_RE, raw, "when"),
        "attorney": re.sub(r"\s+", " ", atty),
        "attorney_phone": phone,
        "publication_line": publication,
        "will_offered": bool(WILL_RE.search(raw_flat)),
        "iaea_requested": bool(IAEA_RE.search(raw_flat)),
        "snippet": raw_flat[:280],
        "raw_text": raw,
        "status": "missing_case" if not case_number else "repeat",
    }


def stub_notice_fields(raw: str, case_extractor=None) -> dict:
    """Keep truncated NOTICE OF PETITION search cards so hydrate can read the advert."""
    text = normalize_notice_text(raw or "")
    blob = text.upper()
    if "NOTICE OF PETITION" not in blob:
        return {}
    extractor = case_extractor or extract_case
    raw_flat = re.sub(r"[ \t]+", " ", text)
    case_number = extractor(raw_flat)
    return {
        "case_number": case_number,
        "decedent": "",
        "petitioner": "",
        "court_county": "",
        "hearing": "",
        "attorney": "",
        "attorney_phone": "",
        "publication_line": "",
        "will_offered": False,
        "iaea_requested": False,
        "snippet": raw_flat[:280],
        "raw_text": text,
        "status": "missing_case" if not case_number else "repeat",
    }


def parse_card(card, case_extractor=None) -> Notice | None:
    desc = card.select_one(".description")
    if not desc:
        return None
    raw = desc.get_text("\n", strip=True)
    fields = notice_fields(raw, case_extractor)
    if not fields:
        fields = stub_notice_fields(raw, case_extractor)
    if not fields:
        return None

    heading = card.select_one(".panel-heading h4")
    newspaper = heading.get_text(strip=True) if heading else ""
    time_el = card.select_one("time")
    post_date = ""
    if time_el is not None:
        raw_date = (time_el.get("datetime") or time_el.get_text(strip=True))[:10]
        if "Post Date" in (time_el.get_text() or ""):
            raw_date = time_el.get_text(strip=True).replace("Post Date:", "").strip()
        post_date = normalize_post_date(raw_date)

    ref = card.select_one(".refcode")
    refcode = re.sub(r"^Refcode:\s*", "", ref.get_text(strip=True) if ref else "")
    advert_inputs = card.select("input[id^=advertId_]")
    advert_id = advert_inputs[0]["value"] if advert_inputs else ""
    notice_url = (
        f"{NOTICE_HOME}/advert/-{advert_id}"
        if advert_id
        else search_url(*default_window(21, 21))
    )

    notice = Notice(
        newspaper=newspaper,
        post_date=post_date,
        refcode=refcode,
        advert_id=advert_id,
        notice_url=notice_url,
        **fields,
    )
    return notice


def parse_html(page_html: str, case_extractor=None) -> list[Notice]:
    soup = BeautifulSoup(page_html, "html.parser")
    cards = soup.select("div.panel.panel-result")
    notices: list[Notice] = []
    for card in cards:
        parsed = parse_card(card, case_extractor=case_extractor)
        if parsed:
            notices.append(parsed)
    return notices


def paginate(
    start: date,
    end: date,
    max_pages: int | None = None,
    county: str | None = None,
    keywords: str | None = None,
    case_extractor=None,
) -> tuple[list[Notice], list[str]]:
    if max_pages is None:
        max_pages = int(os.environ.get("PROBATE_MAX_PAGES", "10"))
    collected: list[Notice] = []
    urls: list[str] = []
    last_full = False
    site_max: int | None = None
    fetched = 0
    for page in cnpa_page_sequence(max_pages):
        if site_max is not None and page > site_max:
            break
        url = search_url(
            start, end, page=page, county=county, keywords=keywords
        )
        urls.append(url)
        cap = site_max or max_pages
        _progress(
            "cnpa",
            f"Searching CNPA notices (page {fetched + 1} of up to {cap})…",
            cnpa_page=fetched + 1,
            cnpa_max_pages=cap,
        )
        html_text = fetch_page(url)
        if site_max is None:
            site_max = parse_cnpa_max_pages(html_text)
        batch = parse_html(html_text, case_extractor=case_extractor)
        collected.extend(batch)
        soup = BeautifulSoup(html_text, "html.parser")
        card_count = len(soup.select("div.panel.panel-result"))
        last_full = card_count >= 24
        fetched += 1
        if card_count == 0:
            break
        # Load More stays enabled in HTML until JS runs; honor CNPA maxPages.
        if site_max is not None and page >= site_max:
            break
        if site_max is None and card_count < 24:
            break
    if last_full and site_max and fetched < min(max_pages, site_max):
        print(
            f"Warning: hit {max_pages}-page cap; later notices may be missing.",
            file=sys.stderr,
        )
    elif last_full and site_max is None and fetched >= max_pages:
        print(
            f"Warning: hit {max_pages}-page cap; later notices may be missing.",
            file=sys.stderr,
        )
    return collected, urls


def dedupe(notices: Iterable[Notice]) -> list[Notice]:
    """Keep the newest publication of each case number."""
    by_case: dict[str, Notice] = {}
    for notice in notices:
        key = notice.case_number or f"NOCASE:{notice.advert_id or notice.refcode}"
        existing = by_case.get(key)
        if existing is None or (notice.post_date or "") > (existing.post_date or ""):
            by_case[key] = notice
    unique = list(by_case.values())
    unique.sort(key=lambda n: (n.post_date or "", n.case_number), reverse=True)
    return unique


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"cases": {}}
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        backup = path.with_name(path.name + ".corrupt")
        backup.write_text(raw, encoding="utf-8")
        raise SystemExit(
            f"State file {path} is not valid JSON ({exc}). "
            f"A copy was written to {backup}. Fix or restore {path} before re-running "
            "so existing cases are not re-flagged as new."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("cases", {}), dict):
        raise SystemExit(
            f"State file {path} does not contain a JSON object with a 'cases' map."
        )
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, sort_keys=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _stored_money(value) -> str:
    """Persist parsed GMV including $0. Empty/missing stays empty."""
    if value is None or value is True or value is False:
        return ""
    if value in ("", [], {}):
        return ""
    if isinstance(value, (int, float)):
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value).strip()


def _gmv_export_value(value) -> str:
    """Sheet cell for GMV: empty if missing, '0' if $0, else a plain number."""
    stored = _stored_money(value)
    if not stored:
        return ""
    cleaned = stored.replace("$", "").replace(",", "").strip()
    try:
        amount = float(cleaned)
        if amount == int(amount):
            return str(int(amount))
        return f"{amount:.2f}".rstrip("0").rstrip(".")
    except ValueError:
        return stored


def listing_from_row(row: dict, run_date: str) -> dict:
    try:
        from .petition_parse import stored_person_name
    except ImportError:
        from petition_parse import stored_person_name

    case = str(row.get("case_number") or row.get("advert_id") or "").strip()
    petitioner = stored_person_name(
        str(row.get("petitioner") or "").strip()
        or str(row.get("petitioner_name") or "").strip()
    )
    decedent = stored_person_name(
        str(row.get("decedent") or "").strip()
        or str(row.get("decedent_name") or "").strip()
    )
    rec = {
        "case_number": case,
        "date": str(row.get("post_date") or row.get("filed") or "").strip(),
        "filed": str(row.get("filed") or row.get("filed_from_docket") or "").strip(),
        "source": (
            "Sacramento County"
            if str(row.get("source_id") or "").lower() == "sacramento"
            else "Placer County"
        ),
        "source_id": str(row.get("source_id") or "placer").lower() or "placer",
        "petitioner": petitioner,
        "decedent": decedent,
        "decedent_address": str(row.get("decedent_residence") or "").strip(),
        "petitioner_address": str(
            row.get("mailing_address") or ""
        ).strip(),
        "petitioner_phone": str(row.get("petitioner_phone") or "").strip(),
        "hearing": str(row.get("next_event") or row.get("hearing") or "").strip(),
        "newspaper": str(row.get("newspaper") or "").strip(),
        "notice_url": str(row.get("notice_url") or "").strip(),
        "court_url": str(row.get("court_url") or "").strip(),
        "status": str(row.get("status") or "").strip(),
        "last_collected": run_date,
    }
    real = _stored_money(row.get("estate_real"))
    if real:
        rec["estate_real"] = real
    personal = _stored_money(row.get("estate_personal"))
    if personal:
        rec["estate_personal"] = personal
    try:
        from .petition_parse import stamp_row_professional_fiduciary
    except ImportError:
        from petition_parse import stamp_row_professional_fiduciary

    stamp_row_professional_fiduciary(row)
    if row.get("professional_fiduciary"):
        rec["professional_fiduciary"] = True
    if row.get("petition_ocr") or row.get("duties_ocr") or row.get("petition_ocr_gmv"):
        rec["petition_ocr"] = True
    if row.get("petition_ocr_gmv"):
        rec["petition_ocr_gmv"] = True
    engine = str(row.get("ocr_engine") or "").strip().lower()
    if engine in {"tesseract", "rapidocr"}:
        rec["ocr_engine"] = engine
    try:
        from .fub_client import apply_listing_go
    except ImportError:
        from fub_client import apply_listing_go

    apply_listing_go(row)
    rec["go_status"] = str(row.get("go_status") or "")
    rec["nogo_reason"] = str(row.get("nogo_reason") or "")
    return rec


def _read_listings_catalog(path: Path) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    if not path.exists():
        return catalog
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return catalog
    items = payload.get("listings") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return catalog
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("case_number") or "").strip()
        if key:
            catalog[key] = item
    return catalog


def merge_listings(path: Path, rows: list[dict], run_date: str) -> None:
    catalog = _read_listings_catalog(path)
    try:
        from .datasources import overlay_prior_listing
    except ImportError:
        from datasources import overlay_prior_listing

    for row in rows:
        key = str(row.get("case_number") or row.get("advert_id") or "").strip()
        prev = catalog.get(key) or {}
        overlay_prior_listing(row, prev)
        rec = listing_from_row(row, run_date)
        key = rec.get("case_number")
        if not key:
            continue
        prev = catalog.get(key) or {}
        merged = dict(prev)
        try:
            from .petition_parse import stored_person_name
        except ImportError:
            from petition_parse import stored_person_name

        for field, value in rec.items():
            if field in ("petitioner", "decedent"):
                cleaned_new = stored_person_name(value)
                cleaned_old = stored_person_name(merged.get(field))
                merged[field] = cleaned_new or cleaned_old
                continue
            if field in ("go_status", "nogo_reason") or value not in (None, "", [], {}):
                merged[field] = value
            elif field not in merged:
                merged[field] = value
        merged["first_collected"] = prev.get("first_collected") or run_date
        merged["last_collected"] = run_date
        if prev.get("fub_removed") or rec.get("fub_removed") or row.get("fub_removed"):
            merged["fub_removed"] = True
        if merged.get("fub_removed"):
            merged["go_status"] = "NO-GO"
            merged["nogo_reason"] = "fub_removed"
        catalog[key] = merged
    listings = sorted(
        catalog.values(),
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("case_number") or ""),
        ),
        reverse=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated": run_date, "count": len(listings), "listings": listings}, indent=2),
        encoding="utf-8",
    )


FUB_STATUS_NO_ID = "no_id"
FUB_STATUS_ID = "id"
FUB_STATUS_DELETED = "deleted"
_LISTING_DATEISH = re.compile(r"^\d{4}-\d{2}-\d{2}")
_LISTING_DATE_RANGE = re.compile(r"^(\d{4}-\d{2}(?:-\d{2})?)\s*\.\.\s*(\d{4}-\d{2}(?:-\d{2})?)$")
LISTING_TABLE_COLUMNS = (
    ("date", "date"),
    ("added_at", "date"),
    ("source", "text"),
    ("case_number", "text"),
    ("docs", "docs"),
    ("go_status", "go"),
    ("nogo_reason", "text"),
    ("petitioner", "text"),
    ("decedent", "text"),
    ("decedent_address", "text"),
    ("hearing", "text"),
    ("estate_real", "text"),
    ("petition_ocr", "ocr"),
    ("fub_status", "fub"),
)
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

LISTING_EXPORT_COLUMNS = (
    ("added_at", "Added"),
    ("date", "Notice date"),
    ("source", "Source"),
    ("case_number", "Case"),
    ("docs", "Documents"),
    ("de111_url", "DE-111 URL"),
    ("de147_url", "DE-147 URL"),
    ("petitioner", "Petitioner"),
    ("petitioner_address", "Petitioner address"),
    ("decedent", "Decedent"),
    ("decedent_address", "Decedent address"),
    ("hearing", "Hearing"),
    ("estate_real", "estate_real"),
    ("gmv_real", "gmv_real"),
    ("estate_personal", "estate_personal"),
    ("petition_ocr", "petition_ocr"),
    ("petition_ocr_gmv", "petition_ocr_gmv"),
    ("ocr_engine", "ocr_engine"),
    ("newspaper", "Newspaper"),
    ("go_status", "GO/NO-GO"),
    ("nogo_reason", "Status"),
    ("fub_status_label", "Listings Status"),
    ("fub_person_id", "FUB person id"),
    ("fub_removed", "FUB removed"),
    ("notice_url", "Notice URL"),
    ("court_url", "Court URL"),
    ("status", "Status"),
    ("first_seen", "First seen"),
    ("last_seen", "Last seen"),
    ("first_collected", "First collected"),
    ("last_collected", "Last collected"),
)


def _dateish(value) -> str:
    if value in (None, "", False, True):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"true", "false"}:
        return ""
    return text


def listing_fub_fields(record: dict | None) -> tuple[str, int | None, bool]:
    rec = record or {}
    removed = bool(rec.get("fub_removed"))
    raw = rec.get("fub_person_id")
    person_id = None
    if raw not in (None, "", 0, "0"):
        try:
            person_id = int(raw)
        except (TypeError, ValueError):
            person_id = None
    if removed:
        return FUB_STATUS_DELETED, person_id, True
    if person_id is None:
        return FUB_STATUS_NO_ID, None, False
    return FUB_STATUS_ID, person_id, False


def fub_status_label(status: str, person_id: int | None = None) -> str:
    if status == FUB_STATUS_DELETED:
        return "deleted"
    if status == FUB_STATUS_ID:
        return str(person_id) if person_id is not None else "ID"
    return "no id"


def listing_row_sort_key(item: dict, field: str = "added_at") -> tuple[str, str]:
    row = item or {}
    if field == "added_at":
        stamp = str(
            row.get("added_at")
            or row.get("first_seen")
            or row.get("first_collected")
            or row.get("date")
            or row.get("filed")
            or ""
        )
    elif field == "date":
        stamp = str(row.get("date") or row.get("filed") or "")
    else:
        stamp = str(row.get(field) or "")
    return (stamp, str(row.get("case_number") or ""))


def listing_column_value(row: dict | None, key: str) -> str:
    rec = row or {}
    if key == "added_at":
        return listing_row_sort_key(rec, "added_at")[0]
    if key == "date":
        return str(rec.get("date") or rec.get("filed") or "")
    if key == "fub_status":
        if rec.get("fub_status") == FUB_STATUS_DELETED or rec.get("fub_removed"):
            return "deleted"
        return fub_status_label(str(rec.get("fub_status") or ""), rec.get("fub_person_id"))
    if key == "go_status":
        return str(rec.get("go_status") or "")
    if key == "petition_ocr":
        return "Yes" if rec.get("petition_ocr") else "—"
    if key == "nogo_reason":
        try:
            from .fub_client import listing_go_reason_label
        except ImportError:
            from fub_client import listing_go_reason_label

        return listing_go_reason_label(rec.get("nogo_reason"))
    if key == "petitioner":
        return " ".join(
            str(part) for part in (rec.get("petitioner"), rec.get("petitioner_address")) if part
        )
    if key == "docs":
        return listing_docs_label(rec)
    value = rec.get(key)
    return "" if value is None else str(value)


def listing_docs(row: dict | None) -> list[dict]:
    rec = row or {}
    items = rec.get("docs")
    if isinstance(items, list) and items:
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            url = str(item.get("url") or "").strip()
            if label and url:
                out.append({"label": label, "url": url})
        if out:
            return out
    docs = []
    for label, key in (("DE-111", "de111_url"), ("DE-147", "de147_url")):
        url = str(rec.get(key) or "").strip()
        if url:
            docs.append({"label": label, "url": url})
    return docs


def listing_docs_label(row: dict | None) -> str:
    labels = [item["label"] for item in listing_docs(row)]
    return " ".join(labels)


def _listing_date_bound(text: str, end: bool = False) -> str:
    raw = str(text or "")
    if len(raw) == 7:
        return f"{raw}-31" if end else f"{raw}-01"
    return raw


def listing_match_column_filter(row: dict | None, key: str, text: str, kind: str = "text") -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    rec = row or {}
    if kind == "go":
        wanted = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
        status = str(rec.get("go_status") or "").lower().replace(" ", "").replace("_", "").replace("-", "")
        if wanted == "nogo":
            return status == "nogo"
        if wanted == "go":
            return status == "go"
        return raw.lower() in str(rec.get("go_status") or "").lower()
    if kind == "fub":
        wanted = raw.lower().replace(" ", "_")
        status = str(rec.get("fub_status") or "").lower()
        label = listing_column_value(rec, "fub_status").lower()
        if wanted in {"no_id", "noid"}:
            return status == FUB_STATUS_NO_ID or label == "no id"
        if wanted == "deleted":
            return status == FUB_STATUS_DELETED or bool(rec.get("fub_removed"))
        if wanted == "id":
            return status == FUB_STATUS_ID
        return raw.lower() in label or wanted in status
    if kind == "ocr" or key == "petition_ocr":
        wanted = raw.lower().replace(" ", "")
        flagged = bool(rec.get("petition_ocr"))
        if wanted in {"yes", "true", "y", "ocr"}:
            return flagged
        if wanted in {"—", "-", "no", "false", "none"}:
            return not flagged
        return wanted in listing_column_value(rec, "petition_ocr").lower()
    if key == "nogo_reason":
        code = str(rec.get("nogo_reason") or "").lower()
        label = listing_column_value(rec, "nogo_reason").lower()
        needle = raw.lower()
        compact = needle.replace(" ", "_")
        return needle in label or needle in code or compact in code
    value = listing_column_value(rec, key)
    if kind == "date":
        match = _LISTING_DATE_RANGE.match(raw)
        if match:
            stamp = _listing_date_bound(value) if len(value) == 7 else value
            return _listing_date_bound(match.group(1)) <= stamp <= _listing_date_bound(match.group(2), True)
    return raw.lower() in value.lower()


def listings_visible_rows(
    rows: list[dict] | None,
    *,
    sort_key: str = "added_at",
    sort_dir: str = "desc",
    filters: dict | None = None,
) -> list[dict]:
    kinds = dict(LISTING_TABLE_COLUMNS)
    items = list(rows or [])
    for key, value in (filters or {}).items():
        if not str(value or "").strip():
            continue
        items = [
            row
            for row in items
            if listing_match_column_filter(row, key, value, kinds.get(key, "text"))
        ]
    items.sort(key=lambda row: str(row.get("case_number") or ""))
    items.sort(
        key=lambda row: listing_column_value(row, sort_key or "added_at").lower(),
        reverse=str(sort_dir or "desc").lower() != "asc",
    )
    return items


def listing_added_at(listing: dict, seen: dict | None = None) -> str:
    sources = (seen or {}, listing or {})
    for key in ("first_seen", "first_collected", "added_at"):
        for source in sources:
            text = _dateish(source.get(key))
            if text:
                return text[:10] if _LISTING_DATEISH.match(text) else text
    for key in ("last_seen", "last_collected", "date", "filed"):
        for source in sources:
            text = _dateish(source.get(key))
            if text:
                return text[:10] if _LISTING_DATEISH.match(text) else text
    return ""


def load_seen_case_index(data_dir: Path) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for name in ("seen_cases.json", "seen_cases_sacramento.json"):
        path = data_dir / name
        if not path.exists():
            continue
        cases = load_state(path).get("cases") or {}
        if not isinstance(cases, dict):
            continue
        for key, rec in cases.items():
            if not key or not isinstance(rec, dict):
                continue
            case = str(key).strip()
            prev = index.get(case)
            if prev is None:
                index[case] = dict(rec)
                continue
            merged = dict(prev)
            for field, value in rec.items():
                if value not in (None, "", [], {}):
                    merged[field] = value
            if prev.get("fub_removed") or rec.get("fub_removed"):
                merged["fub_removed"] = True
            if prev.get("fub_person_id") and not merged.get("fub_person_id"):
                merged["fub_person_id"] = prev.get("fub_person_id")
            first_prev = _dateish(prev.get("first_seen"))
            first_new = _dateish(rec.get("first_seen"))
            if first_prev and (not first_new or first_prev < first_new):
                merged["first_seen"] = first_prev
            index[case] = merged
    return index


def enrich_listing(item: dict, seen_index: dict | None = None) -> dict:
    row = dict(item or {})
    key = str(row.get("case_number") or "").strip()
    seen = dict((seen_index or {}).get(key) or {})
    status, person_id, removed = listing_fub_fields(seen or row)
    row["added_at"] = listing_added_at(row, seen)
    row["first_seen"] = _dateish(seen.get("first_seen")) or _dateish(row.get("first_collected"))
    row["last_seen"] = _dateish(seen.get("last_seen")) or _dateish(row.get("last_collected"))
    row["fub_status"] = status
    row["fub_person_id"] = person_id
    row["fub_removed"] = removed
    row["fub_status_label"] = fub_status_label(status, person_id)
    if not str(row.get("go_status") or "").strip() or not str(row.get("nogo_reason") or "").strip():
        try:
            from .fub_client import apply_listing_go
        except ImportError:
            from fub_client import apply_listing_go

        apply_listing_go(row)
    if removed:
        row["go_status"] = "NO-GO"
        row["nogo_reason"] = "fub_removed"
    try:
        from .fub_client import listing_go_reason_label
    except ImportError:
        from fub_client import listing_go_reason_label

    row["nogo_reason_label"] = listing_go_reason_label(row.get("nogo_reason"))
    return row


def stamp_listing_doc_urls(row: dict, data_dir: Path | None = None) -> dict:
    """Attach DE-111 / DE-147 API download links when those PDFs are on disk."""
    try:
        from .datasources import local_de111_pdf, local_de147_pdf, petition_docs_dir
        from .fub_client import form_api_uri
    except ImportError:
        from datasources import local_de111_pdf, local_de147_pdf, petition_docs_dir
        from fub_client import form_api_uri

    case = str(row.get("case_number") or "").strip()
    source = str(row.get("source_id") or "").strip().lower()
    primary = petition_docs_dir(source or "placer", data_dir=data_dir)
    other_id = "placer" if source == "sacramento" else "sacramento"
    other = petition_docs_dir(other_id, data_dir=data_dir)
    has_de111 = bool(local_de111_pdf(primary, case) or local_de111_pdf(other, case))
    has_de147 = bool(local_de147_pdf(primary, case) or local_de147_pdf(other, case))
    docs = []
    de111_url = form_api_uri(case, "de111") if has_de111 else ""
    de147_url = form_api_uri(case, "de147") if has_de147 else ""
    if de111_url:
        docs.append({"label": "DE-111", "url": de111_url})
    if de147_url:
        docs.append({"label": "DE-147", "url": de147_url})
    row["has_de111"] = has_de111
    row["has_de147"] = has_de147
    row["de111_url"] = de111_url
    row["de147_url"] = de147_url
    row["docs"] = docs
    return row


def filter_listings(
    listings: list[dict],
    *,
    query: str = "",
    source_id: str = "",
    fub_status: str = "",
) -> list[dict]:
    wanted_source = str(source_id or "").strip().lower()
    wanted_fub = str(fub_status or "").strip().lower().replace(" ", "_")
    if wanted_fub in {"noid", "no-id"}:
        wanted_fub = FUB_STATUS_NO_ID
    q = str(query or "").strip().lower()
    out: list[dict] = []
    for row in listings:
        if wanted_source and str(row.get("source_id") or "").lower() != wanted_source:
            continue
        if wanted_fub and str(row.get("fub_status") or "") != wanted_fub:
            continue
        if q:
            blob = " ".join(
                str(row.get(key) or "")
                for key in (
                    "case_number",
                    "date",
                    "added_at",
                    "source",
                    "petitioner",
                    "decedent",
                    "decedent_address",
                    "petitioner_address",
                    "newspaper",
                    "filed",
                    "hearing",
                    "go_status",
                    "nogo_reason",
                    "nogo_reason_label",
                    "petition_ocr",
                    "ocr_engine",
                    "docs",
                    "de111_url",
                    "de147_url",
                    "fub_status",
                    "fub_status_label",
                    "fub_person_id",
                )
            ).lower()
            if q not in blob:
                continue
        out.append(row)
    return out


def _listing_export_value(row: dict, key: str) -> str:
    if key == "fub_status_label":
        return fub_status_label(str(row.get("fub_status") or ""), row.get("fub_person_id"))
    if key == "nogo_reason":
        try:
            from .fub_client import listing_go_reason_label
        except ImportError:
            from fub_client import listing_go_reason_label

        return listing_go_reason_label(row.get("nogo_reason"))
    if key == "docs":
        return listing_docs_label(row)
    if key == "fub_removed":
        return "true" if row.get("fub_removed") else "false"
    if key in {"estate_real", "gmv_real", "estate_personal"}:
        source = "estate_real" if key == "gmv_real" else key
        return _gmv_export_value(row.get(source))
    value = row.get(key)
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    return str(value)


def listings_csv_bytes(listings: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for _key, header in LISTING_EXPORT_COLUMNS])
    for row in listings:
        writer.writerow(
            [_listing_export_value(row, key) for key, _header in LISTING_EXPORT_COLUMNS]
        )
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def table_csv_bytes(rows: list[dict], columns: list[tuple[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for _key, header in columns])
    for row in rows:
        writer.writerow(["" if row.get(key) is None else str(row.get(key)) for key, _header in columns])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _xlsx_escape(text: str) -> str:
    cleaned = _ILLEGAL_XML.sub("", str(text or ""))
    return (
        cleaned.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def listings_xlsx_bytes(listings: list[dict]) -> bytes:
    rows_xml = []
    header_cells = "".join(
        f'<c t="inlineStr"><is><t>{_xlsx_escape(header)}</t></is></c>'
        for _key, header in LISTING_EXPORT_COLUMNS
    )
    rows_xml.append(f'<row r="1">{header_cells}</row>')
    for index, row in enumerate(listings, start=2):
        cells = "".join(
            f'<c t="inlineStr"><is><t xml:space="preserve">{_xlsx_escape(_listing_export_value(row, key))}</t></is></c>'
            for key, _header in LISTING_EXPORT_COLUMNS
        )
        rows_xml.append(f'<row r="{index}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows_xml)}</sheetData></worksheet>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Listings" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return blob.getvalue()


def table_xlsx_bytes(
    rows: list[dict],
    columns: list[tuple[str, str]],
    *,
    sheet_name: str = "Sheet1",
) -> bytes:
    rows_xml = []
    header_cells = "".join(
        f'<c t="inlineStr"><is><t>{_xlsx_escape(header)}</t></is></c>'
        for _key, header in columns
    )
    rows_xml.append(f'<row r="1">{header_cells}</row>')
    for index, row in enumerate(rows, start=2):
        cells = "".join(
            f'<c t="inlineStr"><is><t xml:space="preserve">{_xlsx_escape("" if row.get(key) is None else str(row.get(key)))}</t></is></c>'
            for key, _header in columns
        )
        rows_xml.append(f'<row r="{index}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows_xml)}</sheetData></worksheet>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    safe_name = _xlsx_escape(sheet_name or "Sheet1")[:31] or "Sheet1"
    workbook = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="{safe_name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return blob.getvalue()


def fub_review_csv_bytes(
    listings: list[dict],
    *,
    mapping_path: Path | None = None,
    mapping: dict | None = None,
) -> bytes:
    try:
        from .fub_client import build_fub_review_table
    except ImportError:
        from fub_client import build_fub_review_table

    columns, rows = build_fub_review_table(
        listings, mapping=mapping, mapping_path=mapping_path
    )
    return table_csv_bytes(rows, columns)


def fub_review_xlsx_bytes(
    listings: list[dict],
    *,
    mapping_path: Path | None = None,
    mapping: dict | None = None,
) -> bytes:
    try:
        from .fub_client import build_fub_review_table
    except ImportError:
        from fub_client import build_fub_review_table

    columns, rows = build_fub_review_table(
        listings, mapping=mapping, mapping_path=mapping_path
    )
    return table_xlsx_bytes(rows, columns, sheet_name="FUB review")


def write_fub_review_files(
    data_dir: Path,
    listings: list[dict] | None = None,
    *,
    mapping_path: Path | None = None,
) -> tuple[Path, Path, int]:
    """Write data/fub_review.csv and .xlsx from stored listings. No FUB API."""
    root = Path(data_dir)
    if listings is None:
        listings = build_listings_payload(root).get("listings") or []
    map_path = Path(mapping_path) if mapping_path else root / "fub_mapping.yaml"
    csv_path = root / "fub_review.csv"
    xlsx_path = root / "fub_review.xlsx"
    csv_path.write_bytes(fub_review_csv_bytes(listings, mapping_path=map_path))
    xlsx_path.write_bytes(fub_review_xlsx_bytes(listings, mapping_path=map_path))
    return csv_path, xlsx_path, len(listings)


def build_listings_payload(data_dir: Path) -> dict:
    path = data_dir / "listings.json"
    catalog = _read_listings_catalog(path)
    catalog.update(_read_listings_catalog(data_dir / "listings_sacramento.json"))
    reports = data_dir / "reports"
    if not catalog and reports.is_dir():
        rows: list[dict] = []
        for dossier in list(sorted(reports.glob("dossiers-*.json"))) + list(
            sorted((reports / "sacramento").glob("sacramento-dossiers-*.json"))
        ):
            try:
                payload = json.loads(dossier.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, list):
                rows.extend(item for item in payload if isinstance(item, dict))
        if rows:
            stamp = max(
                (str(item.get("post_date") or item.get("filed") or "") for item in rows),
                default="",
            ) or datetime.now().date().isoformat()
            merge_listings(path, rows, stamp)
            catalog = _read_listings_catalog(path)
            catalog.update(_read_listings_catalog(data_dir / "listings_sacramento.json"))
    seen = load_seen_case_index(data_dir)
    listings = sorted(
        (
            stamp_listing_doc_urls(enrich_listing(item, seen), data_dir)
            for item in catalog.values()
        ),
        key=listing_row_sort_key,
        reverse=True,
    )
    return {"count": len(listings), "listings": listings}


def mark_new(notices: list[Notice], state: dict, run_date: str) -> list[Notice]:
    cases = state.setdefault("cases", {})
    for notice in notices:
        key = notice.case_number or notice.advert_id
        if not key:
            notice.first_seen = True
            notice.status = "missing_case"
            continue
        if key not in cases:
            notice.first_seen = True
            notice.status = "new"
            cases[key] = {
                "first_seen": run_date,
                "decedent": notice.decedent,
                "last_seen": run_date,
                "newspaper": notice.newspaper,
            }
        else:
            notice.first_seen = False
            notice.status = "repeat"
            cases[key]["last_seen"] = run_date
    state["last_run"] = run_date
    return notices


def yesno(flag: bool) -> str:
    return "Yes" if flag else "No"


def _email_money(value) -> str:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text:
        return "—"
    try:
        amount = float(text)
    except ValueError:
        return str(value)
    if amount == int(amount):
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def new_go_contact_rows(rows: list[dict], catalog: dict | None = None) -> list[dict]:
    """Harvest rows that became GO contacts on this run (not already-GO repeats)."""
    try:
        from .fub_client import GO_STATUS_GO, apply_listing_go, is_new_row
    except ImportError:
        from fub_client import GO_STATUS_GO, apply_listing_go, is_new_row

    prior = catalog or {}
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows or []:
        apply_listing_go(row)
        if str(row.get("go_status") or "") != GO_STATUS_GO:
            continue
        key = str(row.get("case_number") or row.get("advert_id") or "").strip()
        was_go = str((prior.get(key) or {}).get("go_status") or "") == GO_STATUS_GO
        if was_go and not is_new_row(row):
            continue
        if key:
            if key in seen:
                continue
            seen.add(key)
        out.append(row)
    out.sort(key=lambda item: str(item.get("case_number") or ""))
    return out


def _go_contact_lines(row: dict) -> list[str]:
    case = str(row.get("case_number") or row.get("advert_id") or "—").strip() or "—"
    return [
        f"[GO] {row.get('decedent') or '(name not parsed)'}  {case}",
        f"  Petitioner: {row.get('petitioner') or row.get('petitioner_name') or '—'}",
        f"  Mailing:    {row.get('mailing_address') or row.get('petitioner_address') or '—'}",
        f"  Phone:      {row.get('petitioner_phone') or '—'}",
        f"  GMV real:   {_email_money(row.get('estate_real'))}",
        f"  Hearing:    {row.get('next_event') or row.get('hearing') or '—'}",
        f"  Court:      {row.get('court_url') or '—'}",
        f"  Notice:     {row.get('notice_url') or '—'}",
        "",
    ]


def go_contact_row_html(row: dict) -> str:
    case = str(row.get("case_number") or row.get("advert_id") or "—").strip() or "—"
    notice = html.escape(str(row.get("notice_url") or ""))
    court = html.escape(str(row.get("court_url") or ""))
    case_html = html.escape(case)
    if notice:
        case_html = f'<a href="{notice}">{html.escape(case)}</a>'
    court_html = "—"
    if court:
        court_html = f'<a href="{court}">Court</a>'
    return f"""
    <tr>
      <td><span style="background:#0b6;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">GO</span></td>
      <td><strong>{html.escape(str(row.get("decedent") or "—"))}</strong><br>{case_html}</td>
      <td>{html.escape(str(row.get("petitioner") or row.get("petitioner_name") or "—"))}</td>
      <td>{html.escape(str(row.get("mailing_address") or row.get("petitioner_address") or "—"))}</td>
      <td>{html.escape(str(row.get("petitioner_phone") or "—"))}</td>
      <td>{html.escape(_email_money(row.get("estate_real")))}</td>
      <td>{html.escape(str(row.get("next_event") or row.get("hearing") or "—"))}<br>{court_html}</td>
    </tr>
    """


def build_go_contact_text(
    rows: list[dict],
    start: date,
    end: date,
    urls: list[str],
    county: str,
    *,
    fub_posted: int | None = None,
    fub_updated: int | None = None,
    fub_skipped: int | None = None,
) -> str:
    fub_text, _ = fub_digest_suffix(
        fub_posted=fub_posted, fub_updated=fub_updated, fub_skipped=fub_skipped
    )
    lines = [
        "Hammond IT Consulting — Blake Hammond Realty",
        f"{county} County — new GO contacts",
        f"Window: {start.isoformat()} to {end.isoformat()}",
        f"New GO contacts: {len(rows)}{fub_text}",
        "",
    ]
    if not rows:
        lines.append("No new GO contacts in this window.")
        lines.append("Query:")
        lines.extend(urls)
        return "\n".join(lines)
    for row in rows:
        lines += _go_contact_lines(row)
    lines += [
        "A published petition does not prove a house is in the estate.",
        "Match the decedent name to title before treating it as a property lead.",
    ]
    return "\n".join(lines)


def build_go_contact_html(
    rows: list[dict],
    start: date,
    end: date,
    urls: list[str],
    county: str,
    *,
    fub_posted: int | None = None,
    fub_updated: int | None = None,
    fub_skipped: int | None = None,
) -> str:
    _, fub_html = fub_digest_suffix(
        fub_posted=fub_posted, fub_updated=fub_updated, fub_skipped=fub_skipped
    )
    body_rows = "\n".join(go_contact_row_html(row) for row in rows)
    empty = "<p>No new GO contacts in this window.</p>" if not rows else ""
    query = "<br>".join(html.escape(u) for u in urls)
    return f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;color:#222;max-width:960px;">
  <p style="letter-spacing:.08em;font-size:12px;color:#8a6d2b;margin:0 0 4px;">HAMMOND IT CONSULTING · BLAKE HAMMOND REALTY</p>
  <h2>{html.escape(county)} County — new GO contacts</h2>
  <p>Window {start.isoformat()} → {end.isoformat()} &nbsp;|&nbsp;
     New GO contacts: <strong>{len(rows)}</strong>{fub_html}</p>
  {empty}
  <table cellpadding="8" cellspacing="0" border="1" style="border-collapse:collapse;width:100%;font-size:14px;">
    <thead style="background:#f3f3f3;">
      <tr>
        <th>Status</th><th>Decedent / case</th><th>Petitioner</th>
        <th>Mailing</th><th>Phone</th><th>GMV real</th><th>Hearing / court</th>
      </tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>
  <p>A published petition does not prove a house is in the estate. Match the decedent name to title before treating it as a property lead.</p>
  <p style="color:#666;font-size:12px;">Query used:<br>{query}</p>
</body></html>
"""


def go_contact_email_subject(county: str, run_date: str, count: int) -> str:
    return f"{county} probate GO contacts — {run_date} — {count} new"


def finalize_job_go_email(
    args,
    *,
    rows: list[dict],
    catalog: dict | None,
    start: date,
    end: date,
    urls: list[str],
    county: str,
    run_date: str,
    out_dir: Path,
    posted: int = 0,
    updated: int = 0,
    skipped: int = 0,
) -> tuple[list[dict], str, str, str, bool]:
    """Write the GO email preview and send it when there is at least one new GO."""
    go_rows = new_go_contact_rows(rows, catalog)
    subject = go_contact_email_subject(county, run_date, len(go_rows))
    text_body = build_go_contact_text(
        go_rows,
        start,
        end,
        urls,
        county,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    html_body = build_go_contact_html(
        go_rows,
        start,
        end,
        urls,
        county,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    stamp = datetime.now(get_tz()).strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"report-{stamp}.txt").write_text(text_body, encoding="utf-8")
    (out_dir / f"report-{stamp}.html").write_text(html_body, encoding="utf-8")
    sent = False
    if getattr(args, "no_email", False):
        print("Email skipped (--no-email).")
        return go_rows, subject, text_body, html_body, sent
    if not go_rows:
        print("No new GO contacts; email skipped.")
        return go_rows, subject, text_body, html_body, sent
    _progress("email", f"Sending {county} GO contact email ({len(go_rows)} new)…")
    send_email(subject, text_body, html_body)
    print("\nEmail sent.")
    sent = True
    return go_rows, subject, text_body, html_body, sent


def fub_digest_suffix(
    *,
    fub_posted: int | None = None,
    fub_updated: int | None = None,
    fub_skipped: int | None = None,
) -> tuple[str, str]:
    """CNPA 'new' is first-seen only; Follow Up Boss counts are separate."""
    if fub_posted is None and fub_updated is None and fub_skipped is None:
        return "", ""
    posted = int(fub_posted or 0)
    updated = int(fub_updated or 0)
    skipped = int(fub_skipped or 0)
    text = f"  |  Follow Up Boss: posted {posted}, updated {updated}, skipped {skipped}"
    html = (
        f" &nbsp;|&nbsp; Follow Up Boss: posted <strong>{posted}</strong>, "
        f"updated <strong>{updated}</strong>, skipped <strong>{skipped}</strong>"
    )
    return text, html


def build_text(
    notices: list[Notice],
    start: date,
    end: date,
    urls: list[str],
    county: str = "Placer",
    *,
    fub_posted: int | None = None,
    fub_updated: int | None = None,
    fub_skipped: int | None = None,
) -> str:
    new_items = [n for n in notices if n.first_seen]
    fub_text, _ = fub_digest_suffix(
        fub_posted=fub_posted, fub_updated=fub_updated, fub_skipped=fub_skipped
    )
    lines = [
        f"Hammond IT Consulting — Blake Hammond Realty",
        f"{county} County probate petition notices",
        f"Window: {start.isoformat()} to {end.isoformat()}",
        f"Unique estates: {len(notices)}  |  New today: {len(new_items)}{fub_text}",
        "",
    ]
    if not notices:
        lines.append("No matching notices in this window.")
        lines.append("Query:")
        lines.extend(urls)
        return "\n".join(lines)

    for n in sorted(notices, key=lambda x: x.sort_key()):
        tag = "NEW" if n.first_seen else "SEEN"
        lines += [
            f"[{tag}] {n.decedent or '(name not parsed)'}  {n.case_number}",
            f"  Petitioner: {n.petitioner or '—'}",
            f"  Hearing:    {n.hearing or '—'}",
            f"  Court:      {n.court_county or '—'}",
            f"  Will: {yesno(n.will_offered)}   IAEA: {yesno(n.iaea_requested)}",
            f"  Attorney:   {n.attorney or '—'}",
            f"  Phone:      {n.attorney_phone or '—'}",
            f"  Paper:      {n.newspaper}  posted {n.post_date}",
            f"  Pub line:   {n.publication_line or '—'}",
            f"  Notice:     {n.notice_url}",
            "",
        ]
    lines += [
        f"Watchlist (look up in {county} Assessor / Recorder):",
        *[f"  - {n.decedent} ({n.case_number})" for n in notices if n.decedent],
        "",
        "A published petition does not prove a house is in the estate.",
        "Match the decedent name to title before treating it as a property lead.",
    ]
    return "\n".join(lines)


def row_html(n: Notice) -> str:
    badge = (
        '<span style="background:#0b6;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">NEW</span>'
        if n.first_seen
        else '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">SEEN</span>'
    )
    return f"""
    <tr>
      <td>{badge}</td>
      <td><strong>{html.escape(n.decedent or "—")}</strong><br>
          <a href="{html.escape(http_url(n.notice_url) or "#")}">{html.escape(n.case_number or "no case #")}</a></td>
      <td>{html.escape(n.petitioner or "—")}</td>
      <td>{html.escape(n.hearing or "—")}</td>
      <td>{yesno(n.will_offered)} / {yesno(n.iaea_requested)}</td>
      <td>{html.escape(n.attorney or "—")}<br>{html.escape(n.attorney_phone or "")}</td>
      <td>{html.escape(n.newspaper or "—")}<br>{html.escape(n.post_date or "")}</td>
    </tr>
    """


def build_html(
    notices: list[Notice],
    start: date,
    end: date,
    urls: list[str],
    county: str = "Placer",
    *,
    fub_posted: int | None = None,
    fub_updated: int | None = None,
    fub_skipped: int | None = None,
) -> str:
    new_count = sum(1 for n in notices if n.first_seen)
    _, fub_html = fub_digest_suffix(
        fub_posted=fub_posted, fub_updated=fub_updated, fub_skipped=fub_skipped
    )
    rows = "\n".join(row_html(n) for n in sorted(notices, key=lambda x: x.sort_key()))
    watch = "".join(
        f"<li>{html.escape(n.decedent)} — {html.escape(n.case_number)}</li>"
        for n in notices
        if n.decedent
    )
    empty = "<p>No matching notices in this window.</p>" if not notices else ""
    query = "<br>".join(html.escape(u) for u in urls)
    return f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;color:#222;max-width:960px;">
  <p style="letter-spacing:.08em;font-size:12px;color:#8a6d2b;margin:0 0 4px;">HAMMOND IT CONSULTING · BLAKE HAMMOND REALTY</p>
  <h2>{html.escape(county)} County probate petition notices</h2>
  <p>Window {start.isoformat()} → {end.isoformat()} &nbsp;|&nbsp;
     Unique estates: <strong>{len(notices)}</strong> &nbsp;|&nbsp;
     New since last run: <strong>{new_count}</strong>{fub_html}</p>
  {empty}
  <table cellpadding="8" cellspacing="0" border="1" style="border-collapse:collapse;width:100%;font-size:14px;">
    <thead style="background:#f3f3f3;">
      <tr>
        <th>Status</th><th>Decedent / case</th><th>Petitioner</th>
        <th>Hearing</th><th>Will / IAEA</th><th>Attorney</th><th>Source</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <h3>Assessor watchlist</h3>
  <p>Look these names up in the {html.escape(county)} Assessor and Recorder. A petition is not proof of a house.</p>
  <ul>{watch or "<li>None</li>"}</ul>
  <p style="color:#666;font-size:12px;">Query used:<br>{query}</p>
</body></html>
"""


def guess_petition(portal: dict, notice: Notice) -> str:
    for doc in portal.get("documents") or []:
        if doc.lower().startswith("20") or "petition" in doc.lower():
            if "petition" in doc.lower():
                return doc
    if notice.will_offered:
        return "Will offered in the published notice"
    return "Letters / administration (see notice)"


def enrich_notices(
    notices: list[Notice],
    year: int,
    docs_dir: Path | None = None,
    *,
    reuse_local: bool = True,
    refresh_cases: list[str] | None = None,
    listings_catalog: dict | None = None,
) -> list[dict]:
    try:
        from .datasources import (
            apply_stored_petitions,
            download_missing_public_pdfs,
            overlay_prior_listing,
            should_reuse_local_case,
        )
        from .ecourt_client import ECourtClient
    except ImportError:
        from datasources import (
            apply_stored_petitions,
            download_missing_public_pdfs,
            overlay_prior_listing,
            should_reuse_local_case,
        )
        from ecourt_client import ECourtClient

    client = None

    def _client() -> ECourtClient:
        nonlocal client
        if client is None:
            client = ECourtClient(pause=float(os.environ.get("ECOURT_PAUSE", "1.2")))
        return client

    rows = []
    total = len(notices)
    catalog = listings_catalog or {}
    for index, notice in enumerate(notices, 1):
        listing = catalog.get(notice.case_number) or {}
        prior_addr = str(
            listing.get("decedent_address")
            or listing.get("decedent_residence")
            or ""
        ).strip()
        reuse = should_reuse_local_case(
            docs_dir,
            notice.case_number,
            reuse_local=reuse_local,
            refresh_cases=refresh_cases,
            decedent_address=prior_addr,
        )
        _progress(
            "ecourt",
            (
                f"Reusing on-disk {notice.case_number} (skip court)"
                if reuse
                else f"eCourt {index}/{total}: {notice.case_number or 'no case number'}"
            ),
            ecourt_index=index,
            ecourt_total=total,
            case_number=notice.case_number,
        )
        portal: dict = {"found": False}
        if reuse:
            portal = {
                "found": True,
                "reused_local": True,
                "court_fetch": False,
                "case_number": notice.case_number,
            }
            overlay_prior_listing(portal, catalog.get(notice.case_number))
            print(f"Skipping court portal {notice.case_number}: complete local copy", flush=True)
        elif notice.case_number:
            try:
                portal = _client().enrich(notice.case_number, year=year)
            except requests.RequestException as exc:
                portal = {"found": False, "error": str(exc), "case_number": notice.case_number}
            if not isinstance(portal, dict):
                portal = {
                    "found": False,
                    "case_number": notice.case_number,
                    "error": "empty_portal",
                }
            portal["court_fetch"] = True
        if docs_dir and notice.case_number and not reuse:
            download_missing_public_pdfs(
                portal,
                docs_dir=docs_dir,
                case_number=notice.case_number,
                download=_client().download,
                pause=float(_client().pause),
                skip_download=portal.get("error") == "ecourt_view_limit",
            )
        if docs_dir and notice.case_number:
            apply_stored_petitions(
                portal,
                docs_dir=docs_dir,
                case_number=notice.case_number,
                petitioner=notice.petitioner,
                verbose=True,
                listing=listing,
            )
        overlay_prior_listing(portal, listing)
        row = asdict(notice)
        merged = {k: v for k, v in portal.items() if v not in (None, "", [], {})}
        if "status" in merged and "court_status" not in merged:
            merged["court_status"] = merged.pop("status")
        else:
            merged.pop("status", None)
        row.update(merged)
        row["status"] = notice.status
        row["first_seen"] = notice.first_seen
        row["found"] = bool(portal.get("found"))
        row["petition_guess"] = guess_petition(portal, notice)
        row["court_fetch"] = bool(portal.get("court_fetch"))
        row["reused_local"] = bool(portal.get("reused_local"))
        if not row.get("filed"):
            row["filed"] = portal.get("filed") or portal.get("filed_from_docket")
        rows.append(row)
    limit_cases = sorted(
        {
            str(row.get("case_number") or "")
            for row in rows
            if row.get("error") == "ecourt_view_limit" or row.get("ecourt_view_limit")
        }
        - {""}
    )
    if limit_cases:
        print(
            "ECOURT_VIEW_LIMIT source=placer source_name=Placer County "
            f"cases={','.join(limit_cases)}",
            flush=True,
        )
    return rows


def write_ecourt_alerts(path: Path, rows: list[dict]) -> dict:
    cases = sorted(
        {
            str(row.get("case_number") or "")
            for row in rows
            if row.get("error") == "ecourt_view_limit" or row.get("ecourt_view_limit")
        }
        - {""}
    )
    payload = {
        "error": "ecourt_view_limit" if cases else None,
        "source": "placer",
        "source_name": "Placer County",
        "cases": cases,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def send_email(subject: str, text_body: str, html_body: str, pdf_path: Path | None = None) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    mail_from = os.environ.get("MAIL_FROM", user)
    mail_to = [addr.strip() for addr in os.environ.get("MAIL_TO", "").split(",") if addr.strip()]

    if not mail_to:
        raise SystemExit("MAIL_TO is not set. Put recipient addresses in .env or the environment.")
    if not user or not password:
        raise SystemExit("SMTP_USER / SMTP_PASSWORD are not set.")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    if pdf_path and pdf_path.exists():
        part = MIMEApplication(pdf_path.read_bytes(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(mail_from, mail_to, msg.as_string())


def write_outputs(out_dir: Path, text_body: str, html_body: str, notices: list[Notice]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(get_tz()).strftime("%Y-%m-%d")
    (out_dir / f"report-{stamp}.txt").write_text(text_body, encoding="utf-8")
    (out_dir / f"report-{stamp}.html").write_text(html_body, encoding="utf-8")
    payload = [asdict(n) for n in notices]
    (out_dir / f"notices-{stamp}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def refresh_digest_with_fub(
    notices: list[Notice],
    start: date,
    end: date,
    urls: list[str],
    out_dir: Path,
    *,
    county: str = "Placer",
    posted: int = 0,
    updated: int = 0,
    skipped: int = 0,
) -> tuple[str, str]:
    text_body = build_text(
        notices,
        start,
        end,
        urls,
        county,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    html_body = build_html(
        notices,
        start,
        end,
        urls,
        county,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    write_outputs(out_dir, text_body, html_body, notices)
    return text_body, html_body


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily Placer probate notice digest")
    p.add_argument("--lookback-days", type=int, default=21)
    p.add_argument("--lookahead-days", type=int, default=21)
    p.add_argument("--state-file", default="data/seen_cases.json")
    p.add_argument("--out-dir", default="data/reports")
    p.add_argument("--no-email", action="store_true", help="Parse and save files only")
    p.add_argument("--dry-run", action="store_true", help="Print and write report files; do not update state or email")
    p.add_argument("--skip-portal", action="store_true", help="CNPA only; skip eCourt lookups")
    p.add_argument("--no-pdf", action="store_true", help="Do not write the dossier PDF")
    p.add_argument(
        "--fub-verify-one",
        action="store_true",
        help="Create at most one new Follow Up Boss person, then skip remaining go-cases",
    )
    p.add_argument(
        "--fub-preview-one",
        action="store_true",
        help="Show one mapped go-case from stored PDFs without posting to Follow Up Boss or updating seen state",
    )
    p.add_argument(
        "--rescan-local",
        action="store_true",
        help="Re-parse on-disk DE-111/DE-147 PDFs only; no CNPA search and no court portal",
    )
    p.add_argument(
        "--test-stored",
        action="store_true",
        help="Parse on-disk PDFs and score the Go checklist. No CNPA, court, email, or Follow Up Boss",
    )
    p.add_argument(
        "--rescan-go",
        action="store_true",
        help="Re-evaluate GO/NO-GO on stored listings and PDFs. Updates listings.json only. No Follow Up Boss",
    )
    p.add_argument(
        "--fub-review-export",
        action="store_true",
        help="Write fub_review.csv and fub_review.xlsx from stored listings. Does not call Follow Up Boss",
    )
    p.add_argument(
        "--refresh-case",
        action="append",
        default=[],
        help="Force a court portal fetch for this case even if a local copy exists",
    )
    p.add_argument("--env-file", default=".env")
    return p.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _finish_fub(
    args: argparse.Namespace,
    rows: list[dict],
    state: dict,
    state_path: Path,
    *,
    source_id: str = "placer",
) -> int:
    if args.fub_preview_one:
        try:
            from .fub_client import preview_one_record
        except ImportError:
            from fub_client import preview_one_record

        _progress("preview", "Previewing one stored extract (not posting to Follow Up Boss)…")
        preview = preview_one_record(
            rows, mapping_path=state_path.parent / "fub_mapping.yaml"
        )
        payload = {
            "posted": 0,
            "updated": 0,
            "skipped": len(preview.get("skips") or []),
            "error": None,
            "preview": True,
            "verify_record": preview.get("verify_record"),
            "verify_note": preview.get("verify_note"),
        }
        if source_id == "sacramento":
            payload["source_id"] = "sacramento"
        payload["skips"] = preview.get("skips") or []
        (state_path.parent / "fub_last.json").write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        print("\nPreview only: Follow Up Boss not updated, seen-cases not updated.")
        _progress(
            "done",
            "Preview finished (Follow Up Boss not updated).",
            fub_posted=0,
            fub_updated=0,
            fub_skipped=len(preview.get("skips") or []),
        )
        return 0
    if args.dry_run:
        print("\nDry run: state and email not written.")
        return 0
    save_state(state_path, state)
    try:
        from .fub_client import export_new_leads
    except ImportError:
        from fub_client import export_new_leads

    _progress("fub", "Importing go-cases into Follow Up Boss…")
    fub_summary = export_new_leads(
        rows, state, mapping_path=state_path.parent / "fub_mapping.yaml"
    )
    posted = int(fub_summary.get("posted") or 0)
    updated = int(fub_summary.get("updated") or 0)
    skipped = int(fub_summary.get("skipped") or 0)
    _progress(
        "fub_done",
        f"Follow Up Boss: posted {posted}, updated {updated}, skipped {skipped}.",
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    save_state(state_path, state)
    sidecar = {
        "posted": fub_summary.get("posted"),
        "updated": fub_summary.get("updated"),
        "skipped": fub_summary.get("skipped"),
        "error": fub_summary.get("error"),
        "verify_case": fub_summary.get("verify_case"),
        "verify_person_id": fub_summary.get("verify_person_id"),
        "verify_record": fub_summary.get("verify_record"),
        "verify_note": fub_summary.get("verify_note"),
        "skips": fub_summary.get("skips") or [],
    }
    if source_id == "sacramento":
        sidecar["source_id"] = "sacramento"
    (state_path.parent / "fub_last.json").write_text(
        json.dumps(sidecar, indent=2),
        encoding="utf-8",
    )
    return 1  # continue to email unless caller stops


def _listing_rows_for_go_rescan(
    rows: list[dict],
    catalog: dict,
    source_id: str,
    state: dict | None = None,
) -> list[dict]:
    """PDF-rescanned rows plus catalog-only listings, without Follow Up Boss."""
    seen = {str(row.get("case_number") or "").strip() for row in rows}
    extras: list[dict] = []
    for key, listing in (catalog or {}).items():
        case = str(key or "").strip()
        if not case or case in seen:
            continue
        rec_source = str((listing or {}).get("source_id") or "").lower()
        if rec_source and rec_source != source_id:
            continue
        extra = dict(listing or {})
        extra["case_number"] = case
        extra["source_id"] = rec_source or source_id
        extra.setdefault("mailing_address", extra.get("petitioner_address") or "")
        extra.setdefault("decedent_residence", extra.get("decedent_address") or "")
        extras.append(extra)
    combined = list(rows) + extras
    try:
        from .fub_client import apply_listing_go
    except ImportError:
        from fub_client import apply_listing_go

    for row in combined:
        apply_listing_go(row, state=state)
    return combined


def _finish_rescan_go(
    rows: list[dict],
    state_path: Path,
    *,
    source_id: str = "placer",
) -> int:
    go = sum(1 for row in rows if str(row.get("go_status") or "") == "GO")
    nogo = len(rows) - go
    summary = {
        "ok": True,
        "posted": 0,
        "updated": 0,
        "skipped": nogo,
        "error": None,
        "rescan_go": True,
        "preview": False,
        "go_count": go,
        "nogo_count": nogo,
        "cases": [
            {
                "case": row.get("case_number"),
                "gate": row.get("go_status"),
                "reason": row.get("nogo_reason") or "",
            }
            for row in rows
        ],
    }
    if source_id == "sacramento":
        summary["source_id"] = "sacramento"
    (state_path.parent / "fub_last.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(
        f"GO rescan: {go} GO / {nogo} no-go. Listings updated. Follow Up Boss not updated.",
        flush=True,
    )
    _progress(
        "done",
        f"GO rescan finished. {go} GO / {nogo} no-go. No Follow Up Boss.",
        fub_posted=0,
        fub_updated=0,
        fub_skipped=nogo,
        go_count=go,
        nogo_count=nogo,
        notice_count=len(rows),
        new_count=0,
    )
    return 0


def _finish_stored_test(
    rows: list[dict],
    state_path: Path,
    *,
    source_id: str = "placer",
) -> int:
    try:
        from .fub_client import score_stored_rows
    except ImportError:
        from fub_client import score_stored_rows

    summary = score_stored_rows(
        rows, mapping_path=state_path.parent / "fub_mapping.yaml"
    )
    if source_id == "sacramento":
        summary["source_id"] = "sacramento"
    (state_path.parent / "fub_last.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    go = int(summary.get("go_count") or 0)
    nogo = int(summary.get("nogo_count") or 0)
    print(
        f"Stored test: {go} GO / {nogo} no-go. Follow Up Boss not updated.",
        flush=True,
    )
    _progress(
        "done",
        f"Stored test finished. {go} GO / {nogo} no-go. No scrape, no Follow Up Boss.",
        fub_posted=0,
        fub_updated=0,
        fub_skipped=nogo,
        go_count=go,
        nogo_count=nogo,
        notice_count=len(rows),
        new_count=0,
    )
    return 0


def _run_fub_review_export(args: argparse.Namespace, root: Path) -> int:
    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = (root / args.state_file).resolve()
    else:
        state_path = state_path.resolve()
    data_dir = state_path.parent
    csv_path, xlsx_path, count = write_fub_review_files(data_dir)
    print(
        f"FUB review export: {count} stored listing{'' if count == 1 else 's'} → "
        f"{csv_path} and {xlsx_path}. Follow Up Boss not updated.",
        flush=True,
    )
    return 0


def _run_rescan_local(args: argparse.Namespace, root: Path) -> int:
    try:
        from .datasources import rescan_local_rows, stamp_fub_tags
    except ImportError:
        from datasources import rescan_local_rows, stamp_fub_tags

    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = (root / args.state_file).resolve()
    else:
        state_path = state_path.resolve()
    state = load_state(state_path)
    os.environ.setdefault("PPM_PROGRESS_PATH", str(state_path.parent / "job_progress.json"))
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / args.out_dir
    docs_dir = out_dir / "docs"
    run_date = today_local().isoformat()
    listings_path = state_path.parent / "listings.json"
    catalog = _read_listings_catalog(listings_path)
    test_stored = bool(getattr(args, "test_stored", False))
    rescan_go = bool(getattr(args, "rescan_go", False))
    kind = "GO rescan" if rescan_go else ("stored test" if test_stored else "local rescan")
    _progress(
        "rescan",
        f"Re-parsing on-disk Placer PDFs in {docs_dir} (no CNPA, no court)…",
    )
    rows = rescan_local_rows("placer", docs_dir, listings_catalog=catalog)
    rows = stamp_fub_tags(rows, "Placer")
    if rescan_go:
        rows = _listing_rows_for_go_rescan(rows, catalog, "placer", state)
    if not test_stored and not bool(getattr(args, "fub_preview_one", False)):
        merge_listings(listings_path, rows, run_date)
    print(
        f"Placer {kind} — {run_date} — 0 new / {len(rows)} unique",
        flush=True,
    )
    _progress(
        "cnpa_done",
        f"Local {kind} found {len(rows)} on-disk cases.",
        notices=len(rows),
        notice_count=len(rows),
        new_count=0,
    )
    if test_stored:
        stored_rc = _finish_stored_test(rows, state_path, source_id="placer")
        if os.environ.get("FUB_ENABLED", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return stored_rc
    elif rescan_go and os.environ.get("FUB_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return _finish_rescan_go(rows, state_path, source_id="placer")
    result = _finish_fub(args, rows, state, state_path, source_id="placer")
    if result == 0:
        return 0
    _progress("done", f"Placer local rescan finished. Cases {len(rows)}.")
    print(f"\nSaved state to {state_path}. Email skipped (local rescan).")
    return 0


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    root = Path(__file__).resolve().parent
    load_env_file(root / args.env_file)
    os.environ.setdefault("FUB_DATA_SOURCE", "placer")
    if args.fub_preview_one:
        os.environ["FUB_PREVIEW_ONE"] = "1"
    if args.fub_verify_one:
        os.environ["FUB_VERIFY_ONLY"] = "1"
    if args.fub_review_export:
        return _run_fub_review_export(args, root)
    if args.test_stored or args.rescan_local or args.rescan_go:
        return _run_rescan_local(args, root)

    start, end = default_window(args.lookback_days, args.lookahead_days)
    try:
        notices, urls = paginate(start, end)
    except requests.RequestException as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 2

    unique = dedupe(notices)
    missing_case = [n for n in unique if needs_advert(n) and not n.case_number]
    if missing_case:
        print(
            f"Opening full advert pages for {len(missing_case)} cards with no court case number…",
            flush=True,
        )
        for notice in missing_case:
            notice.source_note = hydrate_notice(notice)
    unique = keep_placer_notices(unique)
    unique = dedupe(unique)
    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = (root / args.state_file).resolve()
    else:
        state_path = state_path.resolve()
    state = load_state(state_path)
    run_date = today_local().isoformat()
    unique = mark_new(unique, state, run_date)
    os.environ.setdefault("PPM_PROGRESS_PATH", str(state_path.parent / "job_progress.json"))
    new_count = sum(1 for n in unique if n.first_seen)
    _progress(
        "cnpa_done",
        f"CNPA found {len(unique)} unique notices ({new_count} new in this window).",
        notices=len(unique),
        notice_count=len(unique),
        new_count=new_count,
    )

    text_body = build_text(unique, start, end, urls)
    html_body = build_html(unique, start, end, urls)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / args.out_dir
    write_outputs(out_dir, text_body, html_body, unique)

    stamp = datetime.now(get_tz()).strftime("%Y-%m-%d")
    pdf_path = out_dir / f"Placer-Probate-Daily-Feed-{stamp}.pdf"
    rows = [asdict(n) for n in unique]
    catalog: dict = {}
    if not args.skip_portal:
        print("Looking up each case on Placer eCourt Public…")
        _progress(
            "ecourt",
            f"Looking up {len(unique)} cases on Placer eCourt Public…",
            ecourt_total=len(unique),
        )
        try:
            from .datasources import (
                log_missing_form_retry,
                missing_petition_forms,
                preview_refresh_case,
                retry_missing_petition_rows,
                saved_petition_form_count,
            )
        except ImportError:
            from datasources import (
                log_missing_form_retry,
                missing_petition_forms,
                preview_refresh_case,
                retry_missing_petition_rows,
                saved_petition_form_count,
            )

        docs_dir = out_dir / "docs"
        refresh_cases = [str(item).strip() for item in (args.refresh_case or []) if str(item).strip()]
        if args.fub_preview_one:
            pick = preview_refresh_case(unique, docs_dir)
            if pick and pick not in refresh_cases:
                refresh_cases.append(pick)
        catalog = _read_listings_catalog(state_path.parent / "listings.json")
        window_incomplete = [
            notice.case_number
            for notice in unique
            if notice.case_number and missing_petition_forms(docs_dir, notice.case_number)
        ]
        rows = enrich_notices(
            unique,
            year=start.year,
            docs_dir=docs_dir,
            reuse_local=True,
            refresh_cases=refresh_cases,
            listings_catalog=catalog,
        )
        extra = retry_missing_petition_rows(
            catalog=catalog,
            docs_dir=docs_dir,
            source_id="placer",
            exclude_cases=[notice.case_number for notice in unique],
            enrich_fn=lambda notices: enrich_notices(
                notices,
                year=start.year,
                docs_dir=docs_dir,
                reuse_local=True,
                refresh_cases=refresh_cases,
                listings_catalog=catalog,
            ),
        )
        rows.extend(extra)
        log_missing_form_retry(
            len(window_incomplete) + len(extra),
            saved_petition_form_count(rows),
        )
        (out_dir / f"dossiers-{stamp}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    else:
        _progress("ecourt_skip", "Skipping eCourt lookups.")
    try:
        from .datasources import stamp_fub_tags
    except ImportError:
        from datasources import stamp_fub_tags

    rows = stamp_fub_tags(rows, "Placer")
    write_ecourt_alerts(state_path.parent / "ecourt_alerts.json", rows)
    merge_listings(state_path.parent / "listings.json", rows, run_date)
    if not args.no_pdf:
        try:
            from .pdf_report import build_pdf
        except ImportError:
            from pdf_report import build_pdf

        _progress("pdf", "Building the daily PDF…")
        build_pdf(rows, pdf_path, today_local(), start, end)
        print(f"Wrote PDF {pdf_path}")
    else:
        pdf_path = None

    print(text_body)

    if args.fub_preview_one:
        try:
            from .fub_client import preview_one_record
        except ImportError:
            from fub_client import preview_one_record

        _progress("preview", "Previewing one stored extract (not posting to Follow Up Boss)…")
        preview = preview_one_record(
            rows, mapping_path=state_path.parent / "fub_mapping.yaml"
        )
        (state_path.parent / "fub_last.json").write_text(
            json.dumps(
                {
                    "posted": 0,
                    "updated": 0,
                    "skipped": len(preview.get("skips") or []),
                    "error": None,
                    "preview": True,
                    "verify_record": preview.get("verify_record"),
                    "verify_note": preview.get("verify_note"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("\nPreview only: Follow Up Boss not updated, seen-cases not updated.")
        _progress(
            "done",
            "Preview finished (Follow Up Boss not updated).",
            fub_posted=0,
            fub_updated=0,
            fub_skipped=len(preview.get("skips") or []),
        )
        return 0

    if args.dry_run:
        print("\nDry run: state and email not written.")
        return 0
    save_state(state_path, state)
    try:
        from .fub_client import export_new_leads
    except ImportError:
        from fub_client import export_new_leads

    _progress("fub", "Importing go-cases into Follow Up Boss…")
    fub_summary = export_new_leads(
        rows, state, mapping_path=state_path.parent / "fub_mapping.yaml"
    )
    posted = int(fub_summary.get("posted") or 0)
    updated = int(fub_summary.get("updated") or 0)
    skipped = int(fub_summary.get("skipped") or 0)
    _progress(
        "fub_done",
        f"Follow Up Boss: posted {posted}, updated {updated}, skipped {skipped}.",
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    save_state(state_path, state)
    go_rows, subject, text_body, html_body, emailed = finalize_job_go_email(
        args,
        rows=rows,
        catalog=catalog,
        start=start,
        end=end,
        urls=urls,
        county="Placer",
        run_date=run_date,
        out_dir=out_dir,
        posted=posted,
        updated=updated,
        skipped=skipped,
    )
    (state_path.parent / "fub_last.json").write_text(
        json.dumps(
            {
                "posted": fub_summary.get("posted"),
                "updated": fub_summary.get("updated"),
                "skipped": fub_summary.get("skipped"),
                "error": fub_summary.get("error"),
                "verify_case": fub_summary.get("verify_case"),
                "verify_person_id": fub_summary.get("verify_person_id"),
                "verify_record": fub_summary.get("verify_record"),
                "verify_note": fub_summary.get("verify_note"),
                "skips": fub_summary.get("skips") or [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    note = (
        f"Job finished. {len(go_rows)} new GO. "
        f"FUB posted {posted}, updated {updated}, skipped {skipped}."
        + ("" if emailed else " Email skipped.")
    )
    print(f"\nSaved state to {state_path}.")
    _progress(
        "done",
        note,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
