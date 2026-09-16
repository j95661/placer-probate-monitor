#!/usr/bin/env python3
"""Build the Hammond / Blake Hammond Realty daily probate PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#1B2A4A")
STEEL = colors.HexColor("#2F4F6F")
GOLD = colors.HexColor("#C4A35A")
CREAM = colors.HexColor("#F6F1E6")
PALE = colors.HexColor("#EEF3F8")
GRAY = colors.HexColor("#5C6570")
LINE = colors.HexColor("#D5D0C6")
ALERT = colors.HexColor("#8B2E2E")


def _esc(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, list):
        return "<br/>".join(_esc(x) for x in val if x) or "—"
    text = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("\n", "<br/>")


def _styles():
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle("kicker", parent=base["Normal"], fontName="Times-Bold", fontSize=8, textColor=GOLD, spaceAfter=2),
        "title": ParagraphStyle("title", parent=base["Normal"], fontName="Times-Bold", fontSize=18, textColor=NAVY, leading=22, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=base["Normal"], fontName="Times-Italic", fontSize=9.5, textColor=STEEL, spaceAfter=8),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Times-Roman", fontSize=9, leading=12, textColor=NAVY),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName="Times-Roman", fontSize=8, leading=10.5, textColor=GRAY),
        "h": ParagraphStyle("h", parent=base["Normal"], fontName="Times-Bold", fontSize=12, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "case": ParagraphStyle("case", parent=base["Normal"], fontName="Times-Bold", fontSize=11, textColor=NAVY, leading=14),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Times-Bold", fontSize=8, textColor=STEEL, leading=10),
        "td": ParagraphStyle("td", parent=base["Normal"], fontName="Times-Roman", fontSize=8, leading=10.5, textColor=NAVY),
        "th": ParagraphStyle("th", parent=base["Normal"], fontName="Times-Bold", fontSize=7.5, leading=10, textColor=colors.white),
        "flag": ParagraphStyle("flag", parent=base["Normal"], fontName="Times-Italic", fontSize=8.5, leading=11, textColor=ALERT),
        "foot": ParagraphStyle("foot", parent=base["Normal"], fontName="Times-Italic", fontSize=8, textColor=GRAY, leading=11),
        "kpi_n": ParagraphStyle("kpi_n", parent=base["Normal"], alignment=1, fontName="Times-Bold", fontSize=14, textColor=NAVY),
        "kpi_l": ParagraphStyle("kpi_l", parent=base["Normal"], alignment=1, fontName="Times-Roman", fontSize=7, textColor=STEEL, leading=9),
    }


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, letter[1] - 16, letter[0], 16, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(36, letter[1] - 11, "Hammond IT Consulting — Blake Hammond Realty  ·  Placer probate feed")
    canvas.drawRightString(letter[0] - 36, letter[1] - 11, "CONFIDENTIAL")
    canvas.setFillColor(GOLD)
    canvas.rect(0, 0, letter[0], 20, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.setFont("Times-Roman", 7.5)
    canvas.drawString(36, 7, "Public notices + eCourt public index. Documents are not downloadable. Not a title search.")
    canvas.drawRightString(letter[0] - 36, 7, f"Page {doc.page}")
    canvas.restoreState()


def _badge(row: dict) -> str:
    if row.get("first_seen"):
        return "NEW"
    parties = " ".join(row.get("parties") or []).lower()
    docs = " ".join(row.get("documents") or []).lower()
    if "objector" in parties or "objection" in docs:
        return "CONTESTED"
    if "public administrator" in parties:
        return "PUBLIC ADMIN"
    return "OPEN"


def _flags(row: dict) -> str:
    bits = []
    if row.get("first_seen"):
        bits.append("First time this case number appeared in the local tracker.")
    parties = " ".join(row.get("parties") or []).lower()
    docs = " ".join(row.get("documents") or []).lower()
    if "objector" in parties or "objection" in docs:
        bits.append("Contested or an objection is on the public register.")
    if "public administrator" in parties:
        bits.append("Public Administrator is a petitioner.")
    notice_pet = (row.get("petitioner") or "").lower()
    portal_parties = parties
    if notice_pet and notice_pet.split()[-1] and notice_pet.split()[-1] not in portal_parties:
        bits.append("Published petitioner name may not match the portal party list.")
    if not row.get("found"):
        bits.append("No eCourt hit for this case number in the filing-year window.")
    if not bits:
        bits.append("Uncontested on the public register so far. Confirm property separately.")
    return " ".join(bits)


def build_pdf(rows: list[dict], out_path: Path, run_date: date, start: date, end: date) -> Path:
    s = _styles()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    contested = sum(
        1
        for r in rows
        if "objector" in " ".join(r.get("parties") or []).lower()
        or "objection" in " ".join(r.get("documents") or []).lower()
    )
    new_n = sum(1 for r in rows if r.get("first_seen"))
    found_n = sum(1 for r in rows if r.get("found"))

    kpis = Table([[
        [Paragraph(str(len(rows)), s["kpi_n"]), Paragraph("UNIQUE ESTATES", s["kpi_l"])],
        [Paragraph(str(new_n), s["kpi_n"]), Paragraph("NEW TO TRACKER", s["kpi_l"])],
        [Paragraph(str(contested), s["kpi_n"]), Paragraph("CONTESTED SIGNALS", s["kpi_l"])],
        [Paragraph(str(found_n), s["kpi_n"]), Paragraph("ECOURT HITS", s["kpi_l"])],
    ]], colWidths=[1.8 * inch] * 4)
    kpis.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREAM),
        ("BOX", (0, 0), (-1, -1), 0.4, GOLD),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    header = [Paragraph(h, s["th"]) for h in ["Case", "Decedent", "Filed", "Next event", "Watch"]]
    table_rows = [header]
    for r in rows:
        url = r.get("court_url") or ""
        case = r.get("case_number") or "—"
        case_cell = (
            f'<link href="{url}" color="#1A4F8B"><u>{_esc(case)}</u></link>' if url else _esc(case)
        )
        table_rows.append([
            Paragraph(case_cell, s["td"]),
            Paragraph(_esc(r.get("decedent")), s["td"]),
            Paragraph(_esc(r.get("filed") or r.get("filed_from_docket")), s["td"]),
            Paragraph(_esc(r.get("next_event") or (r.get("hearings") or ["—"])[0]), s["td"]),
            Paragraph(_badge(r), s["td"]),
        ])
    roster = Table(table_rows, colWidths=[1.15*inch, 1.7*inch, 1.1*inch, 2.45*inch, 1.0*inch])
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, r in enumerate(rows, 1):
        bg = colors.HexColor("#F8E8E8") if _badge(r) in {"CONTESTED", "PUBLIC ADMIN"} else (PALE if i % 2 else colors.white)
        cmds.append(("BACKGROUND", (0, i), (-1, i), bg))
    roster.setStyle(TableStyle(cmds))

    story = [
        Paragraph("HAMMOND IT CONSULTING  ·  BLAKE HAMMOND REALTY", s["kicker"]),
        Paragraph("Daily Probate Petition Feed — Case Dossiers", s["title"]),
        Paragraph(
            f"{run_date.strftime('%A, %B %-d, %Y')}  ·  Placer County  ·  "
            f"CNPA window {start.isoformat()} to {end.isoformat()}",
            s["sub"],
        ),
        Paragraph(
            "Each estate merges the published Notice of Petition to Administer Estate with the "
            "public eCourt Case Summary. Register PDFs are titles only — the public portal does not allow download. "
            "A petition is not proof that real property is in the estate.",
            s["body"],
        ),
        Spacer(1, 8),
        kpis,
        Paragraph("Roster — case numbers link to the court Case Summary", s["h"]),
        roster,
        PageBreak(),
        Paragraph("Case dossiers", s["h"]),
    ]

    for r in rows:
        url = r.get("court_url") or ""
        notice = r.get("notice_url") or ""
        head = Paragraph(
            f'{_esc(r.get("case_number"))}  ·  {_esc(r.get("caption") or r.get("decedent"))}<br/>'
            f'<font size="8" color="#2F4F6F">{_badge(r)}  ·  {_esc(r.get("case_type") or r.get("status") or "Placer probate")}</font>',
            s["case"],
        )
        links = []
        if url:
            links.append(f'Court file: <link href="{url}" color="#1A4F8B"><u>{_esc(url)}</u></link>')
        if notice:
            links.append(f'Published notice: <link href="{notice}" color="#1A4F8B"><u>{_esc(notice)}</u></link>')
        pairs = [
            ("Filed", r.get("filed") or r.get("filed_from_docket") or "—"),
            ("Petition / will", f'{_esc(r.get("petition_guess"))}  ·  will {_esc("Yes" if r.get("will_offered") else "No")}  ·  IAEA {_esc("Yes" if r.get("iaea_requested") else "No")}'),
            ("Parties", r.get("parties") or [f'Notice petitioner — {r.get("petitioner") or "—"}']),
            ("Hearings", r.get("hearings") or [r.get("hearing") or r.get("next_event") or "—"]),
            ("Hearing history", r.get("hearing_history") or ["—"]),
            ("Documents", r.get("documents") or ["None listed on the public register"]),
            ("Counsel", r.get("court_attorneys") or [r.get("attorney") or "—"]),
            ("Notice counsel", r.get("attorney") or "—"),
            ("Publication", f'{_esc(r.get("newspaper"))}  ·  {_esc(r.get("publication_line") or r.get("post_date"))}'),
            ("Fees", r.get("fees") or ["—"]),
        ]
        data = [[Paragraph(k, s["label"]), Paragraph(_esc(v) if not isinstance(v, str) or "<br" in str(v) else _esc(v), s["td"])] for k, v in pairs]
        body = Table(data, colWidths=[1.25 * inch, 6.15 * inch])
        body.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("BACKGROUND", (0, 0), (0, -1), CREAM),
        ]))
        bar = Table([[""]], colWidths=[7.4 * inch], rowHeights=[4])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
        story.append(KeepTogether([
            bar,
            Spacer(1, 6),
            head,
            Spacer(1, 3),
            Paragraph("<br/>".join(links), s["small"]),
            Spacer(1, 6),
            body,
            Spacer(1, 4),
            Paragraph(_flags(r), s["flag"]),
            Spacer(1, 12),
        ]))

    story.append(Paragraph(
        "Sources: capublicnotice.com keyword search in Placer County; "
        "webportal.placerco.org/eCourtPublic case search with a full-year Filed range. "
        "Run once per day. Do not scrape the court portal in a tight loop.",
        s["foot"],
    ))

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.42 * inch,
        title=f"Placer County Daily Probate Feed — {run_date.isoformat()}",
        author="Hammond IT Consulting — Blake Hammond Realty",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return out_path
