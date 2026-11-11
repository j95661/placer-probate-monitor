"""Read-only weekly audit of stored listings and petition PDFs.

Does not search CNPA, open court portals, or write Follow Up Boss.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .datasources import (
        listing_source_id,
        local_de111_pdf,
        local_de147_pdf,
        missing_petition_forms,
        petition_docs_dir,
    )
    from .fub_client import listing_go_fields
    from .job_progress import report_progress
    from .petition_parse import _pdf_field_pairs, parse_de111_pdf
except ImportError:
    from datasources import (  # type: ignore
        listing_source_id,
        local_de111_pdf,
        local_de147_pdf,
        missing_petition_forms,
        petition_docs_dir,
    )
    from fub_client import listing_go_fields  # type: ignore
    from job_progress import report_progress  # type: ignore
    from petition_parse import _pdf_field_pairs, parse_de111_pdf  # type: ignore

FORM_LABEL_RE = re.compile(
    r"(?i)\b(case number|name and relationship|street address|"
    r"item\s*\d|[0-9]+\.\s*name and relationship)\b"
)
ATTORNEY_PETITIONER_RE = re.compile(
    r"(?i)\b(esq\.?|sbn\s*\d|law office|professional law|attorney at law|"
    r"a professional corporation)\b"
)
JUNK_CITY_RE = re.compile(
    r"(?i)\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
    r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    r"mississippi|missouri|montana|nebraska|nevada|hampshire|jersey|mexico|"
    r"york|carolina|dakota|ohio|oklahoma|oregon|pennsylvania|rhode|tennessee|"
    r"texas|utah|vermont|virginia|washington|wisconsin|wyoming)\b"
)
KNOWN_FORM_BITS = (
    "atty",
    "attorney",
    "bar",
    "caption",
    "citizen",
    "counsel",
    "death",
    "decedent",
    "died",
    "email",
    "estate",
    "firm",
    "iaea",
    "inproper",
    "item",
    "mailing",
    "nameeach",
    "party",
    "permanentaddress",
    "personal",
    "petitioner",
    "phone",
    "real",
    "residence",
    "sbn",
    "streetaddress",
    "will",
    "3a",
    "3c",
    "3h",
    "attachment",
)
NOTICES_RE = re.compile(r"(?i)^notices[_-]")

# Each flag is one issue with one recommended solution.
ISSUE_SOLUTIONS = {
    "missing_case_number": (
        "No court case number; the listing is still a CNPA advert id (Notices_*).",
        "Do not scrape the court calendar. The harvest already opens truncated advert pages; leftover ads usually never printed an S-PR / 26PR number. Leave them NO-GO until a later notice prints the case.",
    ),
    "missing_de111": (
        "No valid DE-111 PDF is stored for this case.",
        "Keep the existing harvest retry. If it is still missing after retry, the docket has no public petition. Do not add a daily 21-day calendar job.",
    ),
    "missing_de147": (
        "No valid DE-147 PDF is stored for this case.",
        "Keep the existing harvest retry. Confidential DE-147S is skipped on purpose. Do not download Not Viewable files.",
    ),
    "decedent_looks_like_form_label": (
        "Decedent name is form chrome (for example “Name and relationship” or “CASE NUMBER”), not a person.",
        "Tighten estate-of / item-1 name extraction so checkbox labels cannot become the decedent. Then Rescan local files. Do not post this name to Follow Up Boss.",
    ),
    "petitioner_looks_like_form_label": (
        "Petitioner name is form chrome, not a person.",
        "Stop item-2 parsing at attorney/party captions. Then Rescan local files. Do not post this name to Follow Up Boss.",
    ),
    "petitioner_looks_like_attorney": (
        "Petitioner looks like the caption lawyer (Esq., SBN, law office), not the client.",
        "Use item 2 / Attorney for (name) as the client. Do not use the caption NAME/FIRM/SBN line as the Follow Up Boss person.",
    ),
    "digit_last_name": (
        "Petitioner last name is a stray digit token, usually a State Bar number glued to the name.",
        "Keep dropping trailing digit tokens in split_person_name. Rescan local files, then update Follow Up Boss only if Path A is GO.",
    ),
    "junk_mailing_city": (
        "Mailing city looks glued or swapped with a state name (for example “South Dakota. Deadwood”).",
        "Clean city/state in the address parser. Do not widen the CNPA search to fix this.",
    ),
    "de111_parse_error": (
        "The stored DE-111 could not be parsed.",
        "Open that PDF on disk and treat it as a parser sample. Do not re-download from court unless the file is corrupt.",
    ),
    "unknown_pdf_fields": (
        "The DE-111 has filled AcroForm fields this extract does not map.",
        "Review the field names in the audit report before adding extractors. Skip attorney caption / firm / SBN keys so lawyers do not become the petitioner.",
    ),
    "pdf_present_mailing_empty": (
        "DE-111 is on disk, but petitioner mailing is still empty.",
        "Use this PDF as the next parser sample for item 2 / 3h / 8. Rescan local files after the parser change. Do not hit eCourt again for a complete local copy.",
    ),
    "listing_mailing_differs_from_pdf": (
        "Listings mailing address does not match the DE-111 parse.",
        "Run Rescan local files for that county so listings pick up the current parser. No CNPA or court.",
    ),
    "listing_petitioner_differs_from_pdf": (
        "Listings petitioner does not match the DE-111 parse.",
        "Run Rescan local files for that county. If the PDF name is the client and the listing is the lawyer, the Attorney-for rule still needs a pass on this form.",
    ),
    "listing_missing_address_pdf_has_it": (
        "Follow Up Boss is NO-GO for missing petitioner address, but the local DE-111 parse has a mailing street.",
        "Run Rescan local files, then Follow Up Boss will see the address on the next GO pass. Do not create a second person.",
    ),
    "nogo_missing_petitioner_address": (
        "NO-GO: petitioner mailing address is missing, so Follow Up Boss will not create/update.",
        "If a DE-111 exists, rescan local files. If not, wait for the harvest form retry. Do not post a partial person.",
    ),
    "nogo_petitioner_name_incomplete": (
        "NO-GO: petitioner first/last name is incomplete.",
        "If the PDF has item 2 or Attorney for (name), rescan local files. If the notice never named a person, leave it NO-GO.",
    ),
    "nogo_missing_petitioner_phone": (
        "NO-GO: petitioner phone is required on the current Path B checklist and is missing.",
        "Take phone from DE-147 or in-pro-per caption only. Do not copy the attorney caption phone.",
    ),
}


def issue_for_flag(code: str) -> dict[str, str]:
    issue, solution = ISSUE_SOLUTIONS.get(
        code,
        (
            f"Unexpected extract flag: {code}.",
            "Inspect the listing and local PDF before changing harvest or Follow Up Boss.",
        ),
    )
    return {"code": code, "issue": issue, "solution": solution}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _load_listings(data_dir: Path) -> list[dict]:
    path = Path(data_dir) / "listings.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("listings") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _unknown_form_fields(pairs: list[tuple[str, str]]) -> list[str]:
    unknown: list[str] = []
    for name, value in pairs:
        if not _norm(value):
            continue
        low = str(name or "").lower()
        if any(bit in low for bit in KNOWN_FORM_BITS):
            continue
        unknown.append(f"{name}={_norm(value)[:80]}")
        if len(unknown) >= 8:
            break
    return unknown


def _name_mismatch(left: str, right: str) -> bool:
    a = re.sub(r"[^a-z ]", "", _norm(left).lower())
    b = re.sub(r"[^a-z ]", "", _norm(right).lower())
    if not a or not b or a == b:
        return False
    aset = set(a.split())
    bset = set(b.split())
    if aset and bset and (aset <= bset or bset <= aset):
        return False
    return True


def audit_case(
    listing: dict,
    *,
    docs_dir: Path | None,
    source_id: str,
) -> dict[str, Any]:
    case = _norm(listing.get("case_number"))
    flags: list[str] = []
    parsed: dict[str, Any] = {}
    unknown: list[str] = []
    go_status, nogo = listing_go_fields(listing)
    if NOTICES_RE.match(case) or not case:
        flags.append("missing_case_number")
    missing = missing_petition_forms(docs_dir, case) if case else ["DE-111", "DE-147"]
    for form in missing:
        flags.append(f"missing_{form.lower().replace('-', '')}")
    decedent = _norm(listing.get("decedent"))
    petitioner = _norm(listing.get("petitioner"))
    if decedent and FORM_LABEL_RE.search(decedent):
        flags.append("decedent_looks_like_form_label")
    if petitioner and FORM_LABEL_RE.search(petitioner):
        flags.append("petitioner_looks_like_form_label")
    if petitioner and ATTORNEY_PETITIONER_RE.search(petitioner):
        flags.append("petitioner_looks_like_attorney")
    tokens = [part for part in petitioner.split() if part]
    if tokens and re.fullmatch(r"\d+", tokens[-1].rstrip(".,")):
        flags.append("digit_last_name")
    mailing = _norm(listing.get("petitioner_address") or listing.get("mailing_address"))
    if mailing:
        city = mailing.split(",")[-2].strip() if mailing.count(",") >= 2 else ""
        if city and ("." in city or (len(city.split()) >= 2 and JUNK_CITY_RE.search(city))):
            flags.append("junk_mailing_city")
    dest111 = local_de111_pdf(docs_dir, case) if case else None
    if dest111 is not None:
        try:
            parsed = parse_de111_pdf(dest111, petitioner)
            unknown = _unknown_form_fields(_pdf_field_pairs(dest111))
        except Exception as exc:  # noqa: BLE001
            flags.append("de111_parse_error")
            parsed = {"parse_error": str(exc)[:200]}
        if unknown:
            flags.append("unknown_pdf_fields")
        parsed_mail = _norm(parsed.get("mailing_address"))
        parsed_name = _norm(parsed.get("petitioner_name") or parsed.get("item2b_name"))
        if dest111 is not None and not mailing and not parsed_mail:
            flags.append("pdf_present_mailing_empty")
        if parsed_mail and mailing and _name_mismatch(mailing, parsed_mail):
            flags.append("listing_mailing_differs_from_pdf")
        if parsed_name and petitioner and _name_mismatch(petitioner, parsed_name):
            flags.append("listing_petitioner_differs_from_pdf")
        if go_status == "NO-GO" and nogo == "missing_petitioner_address" and parsed_mail:
            flags.append("listing_missing_address_pdf_has_it")
    if go_status == "NO-GO" and nogo in {
        "missing_petitioner_address",
        "petitioner_name_incomplete",
        "missing_petitioner_phone",
    }:
        flags.append(f"nogo_{nogo}")
    de147 = local_de147_pdf(docs_dir, case) if case else None
    unique_flags = sorted(set(flags))
    issues = [issue_for_flag(code) for code in unique_flags]
    return {
        "case_number": case,
        "source_id": source_id,
        "decedent": decedent,
        "petitioner": petitioner,
        "go_status": go_status,
        "nogo_reason": nogo,
        "has_de111": dest111 is not None,
        "has_de147": de147 is not None,
        "flags": unique_flags,
        "issues": issues,
        "unknown_pdf_fields": unknown,
        "parsed_petitioner": parsed.get("petitioner_name") or "",
        "parsed_mailing": parsed.get("mailing_address") or "",
    }


def aggregate_issues(rows: list[dict]) -> list[dict[str, Any]]:
    """One row per issue type: issue, recommended solution, cases."""
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        case = _norm(row.get("case_number"))
        for item in row.get("issues") or []:
            code = str(item.get("code") or "")
            if not code:
                continue
            bucket = grouped.get(code)
            if bucket is None:
                bucket = {
                    "code": code,
                    "issue": item.get("issue") or "",
                    "solution": item.get("solution") or "",
                    "count": 0,
                    "cases": [],
                }
                grouped[code] = bucket
                order.append(code)
            bucket["count"] += 1
            if case and case not in bucket["cases"]:
                bucket["cases"].append(case)
    return [grouped[code] for code in order]


def issue_solution_lines(issues: list[dict]) -> list[str]:
    lines: list[str] = []
    for item in issues:
        count = item.get("count")
        suffix = f" ({count} case{'s' if count != 1 else ''})" if count else ""
        lines.append(f"ISSUE{suffix}: {item.get('issue') or ''}")
        lines.append(f"SOLUTION: {item.get('solution') or ''}")
    return lines


def _audit_html(report: dict) -> str:
    issue_rows = []
    for item in report.get("issues") or []:
        cases = ", ".join(str(case) for case in (item.get("cases") or [])[:12])
        extra = int(item.get("count") or 0) - min(12, len(item.get("cases") or []))
        if extra > 0:
            cases = f"{cases} (+{extra} more)"
        issue_rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('issue') or ''))}</td>"
            f"<td>{html.escape(str(item.get('solution') or ''))}</td>"
            f"<td>{html.escape(str(item.get('count') or 0))}</td>"
            f"<td>{html.escape(cases or '—')}</td>"
            "</tr>"
        )
    issues_body = "".join(issue_rows) or (
        "<tr><td colspan='4'>No issues. Keep the daily harvest as-is.</td></tr>"
    )
    case_rows = []
    for item in report.get("cases") or []:
        for issue in item.get("issues") or []:
            case_rows.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('source_id') or ''))}</td>"
                f"<td>{html.escape(str(item.get('case_number') or ''))}</td>"
                f"<td>{html.escape(str(issue.get('issue') or ''))}</td>"
                f"<td>{html.escape(str(issue.get('solution') or ''))}</td>"
                "</tr>"
            )
    cases_body = "".join(case_rows) or "<tr><td colspan='4'>No flagged cases.</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Local probate audit</title>
<style>
body {{ font: 15px/1.45 Segoe UI, sans-serif; background:#f7f3ec; color:#1c1915; margin:0; }}
header {{ background:#1b2a4a; color:#f7f3ec; padding:20px 24px; }}
main {{ padding:20px; max-width:1200px; }}
.card {{ background:#fffdf8; border:1px solid #ddd6cc; border-radius:10px; padding:16px 18px; margin-bottom:16px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 6px; border-bottom:1px solid #ddd6cc; vertical-align:top; }}
th {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#6b645b; }}
</style></head><body>
<header><h1>Local probate audit</h1>
<p>{html.escape(str(report.get('run_date') or ''))} · {html.escape(str(report.get('summary') or ''))}</p>
<p>Each row is one issue and the recommended solution. This job does not search CNPA or court sites and does not update Follow Up Boss.</p>
</header>
<main>
<section class="card"><h2>Issues and recommended solutions</h2>
<table><thead><tr><th>Issue</th><th>Recommended solution</th><th>Count</th><th>Example cases</th></tr></thead>
<tbody>{issues_body}</tbody></table>
</section>
<section class="card"><h2>By case</h2>
<table><thead><tr><th>Source</th><th>Case</th><th>Issue</th><th>Recommended solution</th></tr></thead>
<tbody>{cases_body}</tbody></table>
</section>
</main></body></html>
"""


def run_local_audit(
    data_dir: Path,
    *,
    source_id: str | None = None,
    run_date: date | None = None,
) -> dict[str, Any]:
    """Audit stored listings/PDFs. Writes JSON+HTML under reports/."""
    root = Path(data_dir)
    wanted = str(source_id or "").strip().lower()
    sources = [wanted] if wanted in {"placer", "sacramento"} else ["placer", "sacramento"]
    listings = _load_listings(root)
    stamp = (run_date or date.today()).isoformat()
    rows: list[dict[str, Any]] = []
    counts: Counter = Counter()
    selected = [
        rec
        for rec in listings
        if listing_source_id(rec) in sources
    ]
    total = len(selected)
    report_progress("audit", f"Auditing {total} stored listings…", notice_count=total)
    for index, rec in enumerate(selected, start=1):
        src = listing_source_id(rec)
        docs = petition_docs_dir(src, data_dir=root)
        row = audit_case(rec, docs_dir=docs, source_id=src)
        rows.append(row)
        for flag in row.get("flags") or []:
            counts[flag] += 1
        if index == total or index % 10 == 0:
            report_progress(
                "audit",
                f"Auditing {index} of {total}…",
                notice_count=total,
                ecourt_index=index,
                ecourt_total=total,
                case_number=row.get("case_number"),
            )
            print(f"PROGRESS Local audit {index} of {total}: {row.get('case_number')}", flush=True)
    flagged_rows = [row for row in rows if row.get("flags")]
    issues = aggregate_issues(flagged_rows)
    recs = issue_solution_lines(issues)
    summary = (
        f"{total} stored cases, {len(flagged_rows)} flagged, "
        f"{len(issues)} issue type{'s' if len(issues) != 1 else ''}"
    )
    report = {
        "run_date": stamp,
        "sources": sources,
        "court_fetch": False,
        "cnpa": False,
        "fub": False,
        "summary": summary,
        "counts": dict(counts),
        "issues": issues,
        "recommendations": recs,
        "cases": flagged_rows,
        "case_count": total,
        "flagged_count": len(flagged_rows),
    }
    out_dir = root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"local-audit-{stamp}.json"
    html_path = out_dir / f"local-audit-{stamp}.html"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    html_path.write_text(_audit_html(report), encoding="utf-8")
    print(f"Local audit: {summary}", flush=True)
    for line in recs:
        print(f"AUDIT {line}", flush=True)
    print(f"Wrote {html_path}", flush=True)
    report_progress("done", f"Local audit finished. {summary}", notice_count=total, new_count=len(flagged_rows))
    report["html_path"] = str(html_path)
    report["json_path"] = str(json_path)
    return report


def run_local_audit_job(data_dir: Path, settings: dict | None = None) -> dict[str, Any]:
    """HA job wrapper. Never enables Follow Up Boss, email, or court."""
    settings = settings or {}
    source_id = str(settings.get("source_id") or "").strip().lower() or None
    if source_id not in {"placer", "sacramento"}:
        source_id = None
    report = run_local_audit(data_dir, source_id=source_id)
    flagged = int(report.get("flagged_count") or 0)
    total = int(report.get("case_count") or 0)
    log_lines = [
        "===== audit =====",
        f"Local audit: {report.get('summary')}",
        *(report.get("recommendations") or []),
        f"Wrote {report.get('html_path')}",
    ]
    return {
        "ok": True,
        "last_result": "ok",
        "last_error": None,
        "pdf": report.get("html_path"),
        "new_count": flagged,
        "notice_count": total,
        "fub_posted": 0,
        "fub_updated": 0,
        "fub_skipped": 0,
        "fub_error": None,
        "local_audit": True,
        "go_count": total - flagged,
        "nogo_count": flagged,
        "log_tail": "\n".join(log_lines),
        "audit_issues": report.get("issues") or [],
        "recommendations": report.get("recommendations") or [],
    }
