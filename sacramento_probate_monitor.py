#!/usr/bin/env python3
"""Sacramento County notice parsing and public-portal enrichment.

Case numbers are YYPR###### (26PR001581), not S-PR-0000000.
CNPA search uses "NOTICE OF PETITION". Cards are kept only when the
body contains PETITION TO ADMINISTER ESTATE. Bee and Observer list
cards are often cut off; the full ad is on the CNPA advert page.

Court enrichment reads the logged-out Journal Technologies summary
(node/397). Document images, including confidential Not Viewable
files, are not downloaded, and no portal password is stored.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict

import requests

COUNTY = "Sacramento"
KEYWORDS = '"NOTICE OF PETITION"'
SAC_CASE_RE = re.compile(r"\b(\d{2})PR(\d{3,8})\b", re.I)
LEGACY_CASE_RE = re.compile(r"\b34-\d{4}-\d{5,8}\b")


def extract_sacramento_case(text: str) -> str:
    matches = SAC_CASE_RE.findall(text or "")
    if matches:
        year, number = matches[-1]
        return f"{year}PR{int(number):06d}"
    legacy = LEGACY_CASE_RE.findall(text or "")
    return legacy[-1] if legacy else ""


def _notice_module():
    try:
        from . import placer_probate_monitor as monitor
    except ImportError:
        import placer_probate_monitor as monitor

    return monitor


def advert_text(page_html: str) -> str:
    from bs4 import BeautifulSoup

    monitor = _notice_module()
    soup = BeautifulSoup(page_html, "html.parser")
    chunks = []
    for el in soup.select(".description, .panel-body"):
        text = el.get_text("\n", strip=True)
        if "PETITION TO ADMINISTER ESTATE" in monitor.normalize_notice_text(text).upper():
            chunks.append(text)
    if not chunks:
        return ""
    return max(chunks, key=len)


def needs_advert(notice) -> bool:
    raw = notice.raw_text or ""
    return bool(notice.advert_id) and (
        len(raw) < 500 or "IF YOU OBJECT" not in raw.upper()
    )


def hydrate_notice(notice) -> str:
    """Fill fields from the advert page when the search card is a snippet.

    Returns a short note for the dossier, or "" when the card was already complete.
    """
    if not needs_advert(notice):
        return ""
    monitor = _notice_module()
    try:
        page = monitor.fetch_page(notice.notice_url)
    except requests.RequestException as exc:
        return f"CNPA list text was cut off and the advert page did not load ({exc})."
    full = advert_text(page)
    if len(full) <= len(notice.raw_text or ""):
        return "CNPA list text was cut off and the advert page had no longer notice."
    fields = monitor.notice_fields(full, extract_sacramento_case)
    for key, value in fields.items():
        setattr(notice, key, value)
    return "Search card was shortened; full notice text was read from the CNPA advert page."


def enrich_notices(notices: list) -> list[dict]:
    """Public summary rows the existing Follow Up Boss export can read.

    Petition PDFs stay on the portal. This does not log in and does not
    download Not Viewable documents.
    """
    try:
        from .sacramento_portal import SacramentoPortal
    except ImportError:
        from sacramento_portal import SacramentoPortal

    monitor = _notice_module()
    client = SacramentoPortal(pause=float(os.environ.get("ECOURT_PAUSE", "1.2")))
    rows = []
    total = len(notices)
    for index, notice in enumerate(notices, 1):
        monitor._progress(
            "ecourt",
            f"Sacramento portal {index}/{total}: {notice.case_number or 'no case number'}",
            ecourt_index=index,
            ecourt_total=total,
            case_number=notice.case_number,
        )
        portal = {"found": False}
        if notice.case_number:
            try:
                portal = client.enrich(notice.case_number)
            except requests.RequestException as exc:
                portal = {"found": False, "error": str(exc), "case_number": notice.case_number}
        if not isinstance(portal, dict):
            portal = {
                "found": False,
                "case_number": notice.case_number,
                "error": "empty_portal",
            }
        portal.pop("document_files", None)
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
        row["petition_guess"] = monitor.guess_petition(portal, notice)
        if not row.get("filed"):
            row["filed"] = portal.get("filed") or portal.get("filed_from_docket")
        note = getattr(notice, "source_note", "")
        if note:
            row["extra_flag"] = note
        rows.append(row)
    return rows
