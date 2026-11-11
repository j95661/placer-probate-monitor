#!/usr/bin/env python3
"""Daily Sacramento County probate-notice monitor.

CNPA keyword is NOTICE OF PETITION; cards are kept only when the body
contains PETITION TO ADMINISTER ESTATE. Case numbers are YYPR######.
Court summaries are Journal Technologies node/397. After newspaper CNPA,
a logged-in node/415 Public Reports filing search (Case Type Probate,
1-day slices over public_reports_lookback_days, default 2, lookahead 0)
adds estate-style 25PR/26PR cases not already kept from CNPA. CNPA uses
its own lookback/lookahead (default 60/0) and is not applied to 415.
Public petition, duties, and DE-160 inventory PDFs are downloaded after
portal login. Confidential Not Viewable filings, including DE-147S, are
not downloaded.

Placer's seen_cases.json, keywords, and eCourt path are not used here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import requests

try:
    from .datasources import petition_docs_dir, rescan_local_rows, stamp_fub_tags
    from .placer_probate_monitor import (
        Notice,
        build_html,
        build_text,
        dedupe,
        default_window,
        fetch_page,
        finalize_job_go_email,
        guess_petition,
        load_env_file,
        load_state,
        mark_new,
        merge_listings,
        notice_fields,
        paginate,
        parse_cnpa_max_pages,
        save_state,
        search_url,
        today_local,
        write_outputs,
        _finish_fub,
        _finish_rescan_go,
        _finish_stored_test,
        _listing_rows_for_go_rescan,
        _progress,
        _read_listings_catalog,
        get_tz,
    )
except ImportError:
    from datasources import petition_docs_dir, rescan_local_rows, stamp_fub_tags
    from placer_probate_monitor import (
        Notice,
        build_html,
        build_text,
        dedupe,
        default_window,
        fetch_page,
        finalize_job_go_email,
        guess_petition,
        load_env_file,
        load_state,
        mark_new,
        merge_listings,
        notice_fields,
        paginate,
        parse_cnpa_max_pages,
        save_state,
        search_url,
        today_local,
        write_outputs,
        _finish_fub,
        _finish_rescan_go,
        _finish_stored_test,
        _listing_rows_for_go_rescan,
        _progress,
        _read_listings_catalog,
        get_tz,
    )

COUNTY = "Sacramento"
UNSCOPED_CNPA_SKIP_PAGES = 100
KEYWORDS = '"NOTICE OF PETITION"'
SAC_CASE_RE = re.compile(r"\b(\d{2})[\s\-]*PR[\s\-]*(\d{3,8})\b", re.I)
SAC_COURT_RE = re.compile(r"COUNTY OF\s+SACRAMENTO", re.I)
LEGACY_CASE_RE = re.compile(r"\b34-\d{4}-\d{5,8}\b")
SOURCE_NOTE = (
    "Sources: capublicnotice.com keyword search in Sacramento County "
    "(NOTICE OF PETITION, kept only when the ad is a petition to administer an estate); "
    "Journal Technologies node/415 Public Reports (Case Type Probate, 1-day filing slices) "
    "for estate-style 25PR/26PR captions not already in CNPA; "
    "prod-portal-sacramento-ca.journaltech.com public case search, then the node/397 case summary. "
    "Public DE-111 and DE-147 PDFs are downloaded after portal login. "
    "Confidential Not Viewable documents including DE-147S are not downloaded. "
    "List cards from the Sacramento Bee and the Observer are shortened; the full ad is read from the advert page."
)
YYPR_LEAD_RE = re.compile(r"^(25|26)PR\d{6}$")
ESTATE_FILING_KEEP_RE = re.compile(
    r"\bestate of\b|petition for probate|\bletters?\b",
    re.I,
)
NON_ESTATE_FILING_RE = re.compile(
    r"\bconservatorship of\b|\bguardianship of\b",
    re.I,
)
PUBLIC_REPORTS_SOURCE_NOTE = (
    "Journal Technologies node/415 Public Reports (Case Type Probate)."
)
INTRO = (
    "Each estate merges the published Notice of Petition to Administer Estate with the "
    "Sacramento Superior Court public case summary and public petition/duties PDFs. "
    "Confidential Not Viewable filings are skipped. "
    "A petition is not proof that real property is in the estate."
)


def portal_pause_seconds() -> float:
    raw = os.environ.get("SACRAMENTO_PORTAL_PAUSE") or os.environ.get("ECOURT_PAUSE") or "1.2"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 1.2


def is_sacramento_court_notice(notice: Notice) -> bool:
    """True when the published notice names Sacramento Superior Court."""
    court = re.sub(r"\s+", " ", str(notice.court_county or "")).strip().upper()
    if court.startswith("SACRAMENTO"):
        return True
    blob = " ".join(
        part for part in (notice.raw_text, notice.snippet, notice.court_county) if part
    )
    return bool(SAC_COURT_RE.search(blob))


def skip_unscoped_cnpa(max_pages: int | None) -> bool:
    """Skip statewide CNPA when the site reports 100+ result pages."""
    return max_pages is not None and int(max_pages) >= UNSCOPED_CNPA_SKIP_PAGES


def collect_sacramento_cnpa_notices(
    start,
    end,
    *,
    max_pages: int | None = None,
) -> tuple[list[Notice], list[str], set[str]]:
    """Newspaper-county search plus an unscoped CNPA pass.

    CNPA ``county=Sacramento`` is the *newspaper's* county, not the court.
    That query is only one page of ads. A second pass omits ``county`` so
    Sacramento court petitions printed in other papers are not dropped, then
    callers keep those after hydrate via ``keep_sacramento_notices``.
    Statewide unscoped pagination is skipped when CNPA reports 100+ pages.
    """
    if max_pages is None:
        max_pages = int(os.environ.get("PROBATE_MAX_PAGES", "10"))
    scoped, urls_a = paginate(
        start,
        end,
        county=COUNTY,
        keywords=KEYWORDS,
        case_extractor=extract_sacramento_case,
        max_pages=max_pages,
    )
    scoped_keys = {notice.case_number or notice.advert_id for notice in scoped}
    peek_url = search_url(start, end, county="", keywords=KEYWORDS)
    peek_html = fetch_page(peek_url)
    statewide_pages = parse_cnpa_max_pages(peek_html)
    if skip_unscoped_cnpa(statewide_pages):
        print(
            f"CNPA Sacramento newspaper-county ads {len(scoped)}; "
            f"unscoped extra cards 0 "
            f"(skipped statewide pass, {statewide_pages} pages).",
            flush=True,
        )
        return scoped, urls_a + [peek_url], scoped_keys
    open_cap = max(int(max_pages), 80)
    unscoped, urls_b = paginate(
        start,
        end,
        county="",
        keywords=KEYWORDS,
        case_extractor=extract_sacramento_case,
        max_pages=open_cap,
    )
    merged = list(scoped)
    seen = set(scoped_keys)
    for notice in unscoped:
        key = notice.case_number or notice.advert_id
        if key in seen:
            continue
        seen.add(key)
        merged.append(notice)
    print(
        f"CNPA Sacramento newspaper-county ads {len(scoped)}; "
        f"unscoped extra cards {len(unscoped)}.",
        flush=True,
    )
    return merged, urls_a + urls_b, scoped_keys


def in_sacramento_scoped_keys(notice: Notice, scoped_keys: set[str]) -> bool:
    """Match newspaper-county ads by case or advert id after hydrate fills the case."""
    if notice.case_number and notice.case_number in scoped_keys:
        return True
    if notice.advert_id and notice.advert_id in scoped_keys:
        return True
    return False


def is_sacramento_cnpa_candidate(notice: Notice, scoped_keys: set[str]) -> bool:
    """Cheap pre-hydrate keep: scoped paper, court/case signal, or Sacramento in the card."""
    if in_sacramento_scoped_keys(notice, scoped_keys):
        return True
    if is_sacramento_court_notice(notice):
        return True
    blob = f"{notice.raw_text} {notice.snippet} {notice.newspaper} {notice.court_county}"
    if "SACRAMENTO" in blob.upper():
        return True
    return bool(extract_sacramento_case(blob))


def sacramento_cnpa_candidates(
    notices: list[Notice], scoped_keys: set[str]
) -> list[Notice]:
    return [notice for notice in notices if is_sacramento_cnpa_candidate(notice, scoped_keys)]


def keep_sacramento_notices(
    notices: list[Notice], scoped_keys: set[str]
) -> list[Notice]:
    kept: list[Notice] = []
    for notice in notices:
        if in_sacramento_scoped_keys(notice, scoped_keys) or is_sacramento_court_notice(
            notice
        ):
            kept.append(notice)
    return kept


def is_estate_style_filing(hit: dict) -> bool:
    """Keep 25PR/26PR estate captions; drop conservatorship/guardianship-only."""
    case = (hit.get("case_number") or "").upper()
    if not YYPR_LEAD_RE.match(case):
        return False
    blob = " ".join(part for part in (hit.get("caption"), hit.get("extra")) if part)
    if NON_ESTATE_FILING_RE.search(blob) and not re.search(r"\bestate of\b", blob, re.I):
        return False
    return bool(ESTATE_FILING_KEEP_RE.search(blob))


def decedent_from_filing_caption(caption: str) -> str:
    try:
        from .petition_parse import stored_person_name
    except ImportError:
        from petition_parse import stored_person_name

    text = re.sub(r"\s+", " ", caption or "").strip()
    match = re.search(r"ESTATE OF:\s*(.+)$", text, re.I)
    if match:
        return stored_person_name(match.group(1).strip(" -"))
    return stored_person_name(text)


def filing_hit_to_notice(hit: dict) -> Notice:
    case = (hit.get("case_number") or "").upper()
    caption = hit.get("caption") or ""
    extra = hit.get("extra") or ""
    href = hit.get("href") or ""
    blob = " ".join(part for part in (caption, extra) if part)
    court_url = ""
    if href:
        try:
            from .sacramento_portal import PORTAL_BASE
        except ImportError:
            from sacramento_portal import PORTAL_BASE

        court_url = href if href.startswith("http") else (PORTAL_BASE.rstrip("/") + "/" + href.lstrip("/"))
    return Notice(
        case_number=case,
        decedent=decedent_from_filing_caption(caption),
        petitioner="",
        court_county="SACRAMENTO",
        hearing="",
        attorney="",
        attorney_phone="",
        newspaper="Sacramento Superior Court Public Reports",
        post_date="",
        publication_line="",
        will_offered=False,
        iaea_requested=False,
        refcode="",
        advert_id="",
        notice_url=court_url,
        snippet=blob[:280],
        raw_text=blob,
        extra_flag=PUBLIC_REPORTS_SOURCE_NOTE,
        source_note=PUBLIC_REPORTS_SOURCE_NOTE,
        status="missing_case" if not case else "repeat",
    )


def merge_filings_with_cnpa(
    cnpa_notices: list[Notice], filing_hits: list[dict]
) -> list[Notice]:
    """Append estate-style Public Reports cases not already kept from CNPA."""
    seen = {notice.case_number for notice in cnpa_notices if notice.case_number}
    merged = list(cnpa_notices)
    for hit in filing_hits:
        if not is_estate_style_filing(hit):
            continue
        case = (hit.get("case_number") or "").upper()
        if not case or case in seen:
            continue
        seen.add(case)
        merged.append(filing_hit_to_notice(hit))
    return merged


def public_reports_filing_window(lookback_days: int) -> tuple[date, date]:
    """Node/415 window: inclusive lookback days ending today, lookahead always 0.

    Default 2 → 2 one-day 415 queries (yesterday..today). Skip-if-DE-111-on-disk
    is the later enrich path.
    """
    try:
        from .sacramento_portal import public_reports_window
    except ImportError:
        from sacramento_portal import public_reports_window

    return public_reports_window(lookback_days, today_local())


def collect_public_report_notices(
    existing: list[Notice],
    start: date,
    end: date,
) -> list[Notice]:
    """Login and search node/415; merge unique estate filings into CNPA-kept notices.

    start/end must be the 415 filing window, not the CNPA harvest window.
    """
    try:
        from .sacramento_portal import SacramentoPortal
    except ImportError:
        from sacramento_portal import SacramentoPortal

    client = SacramentoPortal(pause=portal_pause_seconds())
    if not client.ensure_login():
        err = client.login_error or "Sacramento portal login failed."
        print(f"Public Reports (node/415) skipped: {err}", flush=True)
        return existing
    hits = client.search_public_reports(start, end)
    estate_hits = [hit for hit in hits if is_estate_style_filing(hit)]
    merged = merge_filings_with_cnpa(existing, hits)
    added = len(merged) - len(existing)
    print(
        f"Public Reports (node/415) {len(hits)} PR hits, {len(estate_hits)} estate-style; "
        f"added {added} not already in CNPA.",
        flush=True,
    )
    return merged


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
        fields = notice_fields(text, extract_sacramento_case)
        if fields.get("raw_text"):
            chunks.append(fields["raw_text"])
    if not chunks:
        return ""
    return max(chunks, key=len)


def needs_advert(notice: Notice) -> bool:
    raw = notice.raw_text or ""
    return bool(notice.advert_id) and (
        len(raw) < 500 or "IF YOU OBJECT" not in raw.upper() or not notice.case_number
    )


def hydrate_notice(notice: Notice) -> str:
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
    if not fields:
        return "CNPA list text was cut off and the advert page had no longer notice."
    for key, value in fields.items():
        setattr(notice, key, value)
    return "Search card was shortened; full notice text was read from the CNPA advert page."


def _petition_docs_dir(out_dir: Path | None = None) -> Path:
    return petition_docs_dir("sacramento", out_dir=out_dir)


def enrich_notices(
    notices: list[Notice],
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
        from .petition_parse import stamp_row_professional_fiduciary
        from .sacramento_portal import SacramentoPortal
    except ImportError:
        from datasources import (
            apply_stored_petitions,
            download_missing_public_pdfs,
            overlay_prior_listing,
            should_reuse_local_case,
        )
        from petition_parse import stamp_row_professional_fiduciary
        from sacramento_portal import SacramentoPortal

    client = None

    def _client() -> SacramentoPortal:
        nonlocal client
        if client is None:
            client = SacramentoPortal(pause=portal_pause_seconds())
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
                else f"Sacramento portal {index} of {total}: {notice.case_number or 'no case'}…"
            ),
            ecourt_total=total,
            ecourt_index=index,
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
                portal = _client().enrich(notice.case_number)
            except requests.RequestException as exc:
                portal = {
                    "found": False,
                    "error": str(exc),
                    "case_number": notice.case_number,
                }
            portal["court_fetch"] = True
        if docs_dir and notice.case_number and not reuse:
            download_missing_public_pdfs(
                portal,
                docs_dir=docs_dir,
                case_number=notice.case_number,
                download=_client().download,
                pause=float(_client().pause),
                skip_download=not _client().logged_in,
            )
        if docs_dir and notice.case_number:
            apply_stored_petitions(
                portal,
                docs_dir=docs_dir,
                case_number=notice.case_number,
                petitioner=notice.petitioner,
                verbose=False,
                listing=listing,
            )
        overlay_prior_listing(portal, listing)
        row = asdict(notice)
        note = getattr(notice, "source_note", "") or getattr(notice, "extra_flag", "")
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
        row["source_id"] = "sacramento"
        row["court_fetch"] = bool(portal.get("court_fetch"))
        row["reused_local"] = bool(portal.get("reused_local"))
        if not row.get("filed"):
            row["filed"] = portal.get("filed") or portal.get("filed_from_docket")
        if note:
            row["extra_flag"] = note
        stamp_row_professional_fiduciary(row)
        rows.append(row)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Sacramento probate notice digest")
    parser.add_argument("--lookback-days", type=int, default=60)
    parser.add_argument("--lookahead-days", type=int, default=0)
    parser.add_argument(
        "--public-reports-lookback-days",
        type=int,
        default=2,
        help=(
            "Node/415 filing lookback in inclusive calendar days ending today "
            "(default 2 → today + yesterday, 2 one-day queries). Lookahead is always 0; not CNPA's window."
        ),
    )
    parser.add_argument("--state-file", default="data/seen_cases_sacramento.json")
    parser.add_argument("--out-dir", default="data/reports/sacramento")
    parser.add_argument("--no-email", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-portal", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--fub-verify-one", action="store_true")
    parser.add_argument("--fub-preview-one", action="store_true")
    parser.add_argument(
        "--rescan-local",
        action="store_true",
        help="Re-parse on-disk DE-111/DE-147 PDFs only; no CNPA search and no court portal",
    )
    parser.add_argument(
        "--test-stored",
        action="store_true",
        help="Parse on-disk PDFs and score the Go checklist. No CNPA, court, email, or Follow Up Boss",
    )
    parser.add_argument(
        "--rescan-go",
        action="store_true",
        help="Re-evaluate GO/NO-GO on stored listings and PDFs. Updates listings only. No Follow Up Boss",
    )
    parser.add_argument(
        "--refresh-case",
        action="append",
        default=[],
        help="Force a court portal fetch for this case even if a local copy exists",
    )
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args()


def _run_rescan_local(args: argparse.Namespace, root: Path) -> int:
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
    docs_dir = _petition_docs_dir(out_dir)
    run_date = today_local().isoformat()
    listings_path = state_path.parent / "listings.json"
    sac_listings = state_path.parent / "listings_sacramento.json"
    catalog = _read_listings_catalog(listings_path)
    catalog.update(_read_listings_catalog(sac_listings))
    test_stored = bool(getattr(args, "test_stored", False))
    rescan_go = bool(getattr(args, "rescan_go", False))
    kind = "GO rescan" if rescan_go else ("stored test" if test_stored else "local rescan")
    _progress(
        "rescan",
        f"Re-parsing on-disk Sacramento PDFs in {docs_dir} (no CNPA, no court)…",
    )
    rows = rescan_local_rows("sacramento", docs_dir, listings_catalog=catalog)
    rows = stamp_fub_tags(rows, COUNTY)
    if rescan_go:
        rows = _listing_rows_for_go_rescan(rows, catalog, "sacramento", state)
    if not test_stored and not bool(getattr(args, "fub_preview_one", False)):
        merge_listings(listings_path, rows, run_date)
        merge_listings(sac_listings, rows, run_date)
    print(
        f"Sacramento {kind} — {run_date} — 0 new / {len(rows)} unique",
        flush=True,
    )
    _progress(
        "cnpa_done",
        f"Local {kind} found {len(rows)} on-disk Sacramento cases.",
        notices=len(rows),
        notice_count=len(rows),
        new_count=0,
    )
    if test_stored:
        stored_rc = _finish_stored_test(rows, state_path, source_id="sacramento")
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
        return _finish_rescan_go(rows, state_path, source_id="sacramento")
    result = _finish_fub(args, rows, state, state_path, source_id="sacramento")
    if result == 0:
        return 0
    _progress("done", f"Sacramento local rescan finished. Cases {len(rows)}.")
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
    os.environ["FUB_DATA_SOURCE"] = "sacramento"
    os.environ["PROBATE_COUNTY"] = COUNTY
    os.environ["PROBATE_KEYWORDS"] = KEYWORDS
    if args.fub_preview_one:
        os.environ["FUB_PREVIEW_ONE"] = "1"
    if args.fub_verify_one:
        os.environ["FUB_VERIFY_ONLY"] = "1"
    if args.test_stored or args.rescan_local or args.rescan_go:
        return _run_rescan_local(args, root)

    start, end = default_window(args.lookback_days, args.lookahead_days)
    try:
        notices, urls, scoped_keys = collect_sacramento_cnpa_notices(start, end)
    except requests.RequestException as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 2

    unique = dedupe(notices)
    candidates = sacramento_cnpa_candidates(unique, scoped_keys)
    print(
        f"Opening full advert pages for {sum(1 for n in candidates if needs_advert(n))} shortened cards…",
        flush=True,
    )
    for notice in candidates:
        notice.source_note = hydrate_notice(notice)
        notice.extra_flag = notice.source_note
    unique = keep_sacramento_notices(candidates, scoped_keys)
    if not args.skip_portal:
        _progress(
            "public_reports",
            "Searching Journal Technologies Public Reports (node/415)…",
        )
        unique = collect_public_report_notices(
            unique,
            *public_reports_filing_window(args.public_reports_lookback_days),
        )

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
        f"CNPA + Public Reports found {len(unique)} unique Sacramento notices "
        f"({new_count} new in this window).",
        notices=len(unique),
        notice_count=len(unique),
        new_count=new_count,
    )

    text_body = build_text(unique, start, end, urls, county=COUNTY)
    html_body = build_html(unique, start, end, urls, county=COUNTY)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / args.out_dir
    write_outputs(out_dir, text_body, html_body, unique)

    stamp = datetime.now(get_tz()).strftime("%Y-%m-%d")
    pdf_path = out_dir / f"Sacramento-Probate-Daily-Feed-{stamp}.pdf"
    rows = [asdict(n) for n in unique]
    catalog: dict = {}
    for row, notice in zip(rows, unique):
        note = getattr(notice, "source_note", "")
        if note:
            row["extra_flag"] = note
        row["source_id"] = "sacramento"
    if not args.skip_portal:
        print("Looking up each case on the Sacramento public portal…", flush=True)
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

        docs_dir = _petition_docs_dir(out_dir)
        refresh_cases = [str(item).strip() for item in (args.refresh_case or []) if str(item).strip()]
        if args.fub_preview_one:
            pick = preview_refresh_case(unique, docs_dir)
            if pick and pick not in refresh_cases:
                refresh_cases.append(pick)
        catalog = _read_listings_catalog(state_path.parent / "listings.json")
        catalog.update(_read_listings_catalog(state_path.parent / "listings_sacramento.json"))
        window_incomplete = [
            notice.case_number
            for notice in unique
            if notice.case_number and missing_petition_forms(docs_dir, notice.case_number)
        ]
        rows = enrich_notices(
            unique,
            docs_dir=docs_dir,
            reuse_local=True,
            refresh_cases=refresh_cases,
            listings_catalog=catalog,
        )
        extra = retry_missing_petition_rows(
            catalog=catalog,
            docs_dir=docs_dir,
            source_id="sacramento",
            exclude_cases=[notice.case_number for notice in unique],
            enrich_fn=lambda notices: enrich_notices(
                notices,
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
        (out_dir / f"sacramento-dossiers-{stamp}.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
    else:
        _progress("ecourt_skip", "Skipping Sacramento portal lookups.")
    rows = stamp_fub_tags(rows, COUNTY)
    merge_listings(state_path.parent / "listings.json", rows, run_date)
    merge_listings(state_path.parent / "listings_sacramento.json", rows, run_date)
    if not args.no_pdf:
        try:
            from .pdf_report import build_pdf
        except ImportError:
            from pdf_report import build_pdf

        _progress("pdf", "Building the Sacramento daily PDF…")
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

    print(text_body)

    if args.fub_preview_one:
        try:
            from .fub_client import preview_one_record
        except ImportError:
            from fub_client import preview_one_record

        _progress("preview", "Previewing one Sacramento extract (not posting to Follow Up Boss)…")
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
                    "source_id": "sacramento",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("\nPreview only: Follow Up Boss not updated, seen-cases not updated.")
        _progress(
            "done",
            "Sacramento preview finished (Follow Up Boss not updated).",
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

    _progress("fub", "Importing Sacramento go-cases into Follow Up Boss…")
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
        county=COUNTY,
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
                "source_id": "sacramento",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    note = (
        f"Sacramento job finished. {len(go_rows)} new GO. "
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
