#!/usr/bin/env python3
"""Daily Sacramento County probate-notice monitor.

Same dossier as the Placer feed: CNPA notice fields plus a court-portal
case summary, then text, HTML, JSON, and PDF.

Sacramento differs from Placer in three places that change the fetch:

- Case numbers are YYPR###### (26PR001581), not S-PR-0000000.
- The exact CNPA phrase "NOTICE OF PETITION TO ADMINISTER ESTATE" misses
  ads that the shorter "NOTICE OF PETITION" search still returns. Cards
  are kept only when the body contains the estate phrase.
- Sacramento Bee and Observer list cards are cut at about 200 characters.
  The full ad is on /advert/-{id}. Placer list cards already include it.
- The court site is the Journal Technologies public portal. Search is a
  case-number form (no filed-date range). The full summary is node/397.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import requests

from placer_probate_monitor import (
    Notice,
    TZ,
    build_html,
    build_text,
    dedupe,
    default_window,
    fetch_page,
    guess_petition,
    load_env_file,
    load_state,
    mark_new,
    normalize_notice_text,
    notice_fields,
    paginate,
    save_state,
    send_email,
    today_local,
    write_outputs,
)

COUNTY = "Sacramento"
KEYWORDS = '"NOTICE OF PETITION"'
SAC_CASE_RE = re.compile(r"\b(\d{2})PR(\d{3,8})\b", re.I)
LEGACY_CASE_RE = re.compile(r"\b34-\d{4}-\d{5,8}\b")
SOURCE_NOTE = (
    "Sources: capublicnotice.com keyword search in Sacramento County "
    "(NOTICE OF PETITION, kept only when the ad is a petition to administer an estate); "
    "prod-portal-sacramento-ca.journaltech.com public case search, then the node/397 case summary. "
    "List cards from the Sacramento Bee and the Observer are shortened; the full ad is read from the advert page. "
    "Run once per day. Do not scrape the court portal in a tight loop."
)
INTRO = (
    "Each estate merges the published Notice of Petition to Administer Estate with the "
    "Sacramento Superior Court public case summary (parties, hearings, and document titles). "
    "Document images are not downloaded. "
    "A petition is not proof that real property is in the estate."
)


def extract_sacramento_case(text: str) -> str:
    matches = SAC_CASE_RE.findall(text or "")
    if matches:
        year, number = matches[-1]
        return f"{year}PR{int(number):06d}"
    legacy = LEGACY_CASE_RE.findall(text or "")
    return legacy[-1] if legacy else ""


def advert_text(page_html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    chunks = []
    for el in soup.select(".description, .panel-body"):
        text = el.get_text("\n", strip=True)
        if "PETITION TO ADMINISTER ESTATE" in normalize_notice_text(text).upper():
            chunks.append(text)
    if not chunks:
        return ""
    return max(chunks, key=len)


def needs_advert(notice: Notice) -> bool:
    raw = notice.raw_text or ""
    return bool(notice.advert_id) and (
        len(raw) < 500 or "IF YOU OBJECT" not in raw.upper()
    )


def hydrate_notice(notice: Notice) -> str:
    """Fill fields from the advert page when the search card is a snippet.

    Returns a short note for the dossier, or "" when the card was already complete.
    """
    if not needs_advert(notice):
        return ""
    try:
        page = fetch_page(notice.notice_url)
    except requests.RequestException as exc:
        return f"CNPA list text was cut off and the advert page did not load ({exc})."
    full = advert_text(page)
    if len(full) <= len(notice.raw_text or ""):
        return "CNPA list text was cut off and the advert page had no longer notice."
    fields = notice_fields(full, extract_sacramento_case)
    for key, value in fields.items():
        setattr(notice, key, value)
    return "Search card was shortened; full notice text was read from the CNPA advert page."


def enrich_notices(notices: list[Notice]) -> list[dict]:
    from sacramento_portal import SacramentoPortal

    client = SacramentoPortal(pause=1.2)
    rows = []
    for notice in notices:
        portal = {"found": False}
        if notice.case_number:
            try:
                portal = client.enrich(notice.case_number)
            except requests.RequestException as exc:
                portal = {"found": False, "error": str(exc), "case_number": notice.case_number}
        row = asdict(notice)
        note = getattr(notice, "source_note", "")
        row.update({k: v for k, v in portal.items() if v not in (None, "", [], {})})
        row["found"] = bool(portal.get("found"))
        row["petition_guess"] = guess_petition(portal, notice)
        if not row.get("filed"):
            row["filed"] = portal.get("filed") or portal.get("filed_from_docket")
        if note:
            row["extra_flag"] = note
        rows.append(row)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Sacramento probate notice digest")
    parser.add_argument("--lookback-days", type=int, default=21)
    parser.add_argument("--lookahead-days", type=int, default=21)
    parser.add_argument("--state-file", default="data/seen_cases_sacramento.json")
    parser.add_argument("--out-dir", default="data/reports/sacramento")
    parser.add_argument("--no-email", action="store_true", help="Parse and save files only")
    parser.add_argument("--dry-run", action="store_true", help="Print report; do not update state or email")
    parser.add_argument("--skip-portal", action="store_true", help="CNPA only; skip the public portal")
    parser.add_argument("--no-pdf", action="store_true", help="Do not write the dossier PDF")
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    load_env_file(root / args.env_file)

    start, end = default_window(args.lookback_days, args.lookahead_days)
    try:
        notices, urls = paginate(
            start,
            end,
            county=COUNTY,
            keywords=KEYWORDS,
            case_extractor=extract_sacramento_case,
        )
    except requests.RequestException as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 2

    unique = dedupe(notices)
    print(f"Opening full advert pages for {sum(1 for n in unique if needs_advert(n))} shortened cards…")
    for notice in unique:
        notice.source_note = hydrate_notice(notice)

    state_path = (root / args.state_file).resolve()
    state = load_state(state_path)
    run_date = today_local().isoformat()
    if not args.dry_run:
        unique = mark_new(unique, state, run_date)

    text_body = build_text(unique, start, end, urls, county=COUNTY)
    html_body = build_html(unique, start, end, urls, county=COUNTY)
    out_dir = root / args.out_dir
    write_outputs(out_dir, text_body, html_body, unique, file_prefix="sacramento-")

    stamp = datetime.now(TZ).strftime("%Y-%m-%d")
    pdf_path = out_dir / f"Sacramento-Probate-Daily-Feed-{stamp}.pdf"
    rows = [asdict(n) for n in unique]
    for row, notice in zip(rows, unique):
        note = getattr(notice, "source_note", "")
        if note:
            row["extra_flag"] = note
    if not args.skip_portal:
        print("Looking up each case on the Sacramento public portal…")
        rows = enrich_notices(unique)
    from datasources import stamp_fub_tags

    rows = stamp_fub_tags(rows, COUNTY)
    if not args.skip_portal:
        (out_dir / f"sacramento-dossiers-{stamp}.json").write_text(json.dumps(rows, indent=2))
    if not args.no_pdf:
        from pdf_report import build_pdf

        build_pdf(
            rows,
            pdf_path,
            today_local(),
            start,
            end,
            county=COUNTY,
            source_note=SOURCE_NOTE,
            intro=INTRO,
        )
        print(f"Wrote PDF {pdf_path}")
    else:
        pdf_path = None

    new_count = sum(1 for n in unique if n.first_seen)
    subject = (
        f"Sacramento probate notices — {run_date} — "
        f"{new_count} new / {len(unique)} unique"
    )
    print(text_body)

    if args.dry_run:
        print("\nDry run: state and email not written.")
        return 0
    save_state(state_path, state)
    if args.no_email:
        print(f"\nSaved state to {state_path}. Email skipped.")
        return 0
    send_email(subject, text_body, html_body, pdf_path=pdf_path)
    print("\nEmail sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
