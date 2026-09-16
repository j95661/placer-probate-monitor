#!/usr/bin/env python3
"""Placer eCourt Public lookups. Requires a search-then-open session."""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PORTAL_SEARCH = "https://webportal.placerco.org/eCourtPublic/?q=node/48"
PORTAL_HOME = "https://webportal.placerco.org/eCourtPublic/"
USER_AGENT = (
    "Mozilla/5.0 (compatible; HammondProbateMonitor/1.0; "
    "+local research digest)"
)


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def _section(text: str, start: str, *ends: str) -> str:
    low = text.lower()
    i = low.find(start.lower())
    if i < 0:
        return ""
    rest = text[i + len(start) :]
    cut = len(rest)
    low_rest = rest.lower()
    for end in ends:
        j = low_rest.find(end.lower())
        if j >= 0:
            cut = min(cut, j)
    return rest[:cut].strip()


class ECourtClient:
    def __init__(self, pause: float = 1.0) -> None:
        self.pause = pause
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _form_payload(self) -> tuple[str, dict]:
        resp = self.session.get(PORTAL_SEARCH, timeout=45)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.find("form")
        if not form:
            raise RuntimeError("eCourt search form not found")
        data = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                data[name] = inp.get("value") or ""
        action = urljoin(PORTAL_HOME, form.get("action") or "?q=node/48")
        return action, data

    def search_case(
        self,
        case_number: str,
        filed_from: str = "01/01/2026",
        filed_to: str = "12/31/2026",
    ) -> dict | None:
        action, data = self._form_payload()
        data["data(110131)"] = ""
        data["data(110132)"] = ""
        data["data(110133)"] = ""
        data["data(110134)"] = case_number
        data["data(110135)"] = filed_from
        data["data(110135_right)"] = filed_to
        data["op"] = "Search"
        resp = self.session.post(action, data=data, timeout=45)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            headers = [td.get_text(" ", strip=True) for td in rows[0].find_all(["th", "td"])]
            if "Case Number" not in headers:
                continue
            for tr in rows[1:]:
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(cells) < 4 or case_number.upper() not in cells[0].upper():
                    continue
                link = tr.find("a", href=True)
                href = urljoin(PORTAL_HOME, link["href"]) if link else ""
                return {
                    "case_number": cells[0],
                    "caption": cells[1] if len(cells) > 1 else "",
                    "filed": cells[2] if len(cells) > 2 else "",
                    "case_type": cells[3] if len(cells) > 3 else "",
                    "category": cells[4] if len(cells) > 4 else "",
                    "next_event": cells[5] if len(cells) > 5 else "",
                    "previous_event": cells[6] if len(cells) > 6 else "",
                    "status": cells[7] if len(cells) > 7 else "",
                    "court_url": href,
                }
        return None

    def fetch_summary(self, court_url: str) -> dict:
        resp = self.session.get(court_url, timeout=45)
        resp.raise_for_status()
        if "Page not found" in resp.text:
            return {"raw_text": "", "error": "case summary 404"}
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text("\n", strip=True)
        return parse_summary(text)

    def enrich(self, case_number: str, year: int = 2026) -> dict:
        time.sleep(self.pause)
        hit = self.search_case(
            case_number,
            filed_from=f"01/01/{year}",
            filed_to=f"12/31/{year}",
        )
        if not hit:
            # try prior year in case filing lagged the notice year
            time.sleep(self.pause)
            hit = self.search_case(
                case_number,
                filed_from=f"01/01/{year - 1}",
                filed_to=f"12/31/{year}",
            )
        if not hit:
            return {"found": False, "case_number": case_number}
        detail = {}
        if hit.get("court_url"):
            time.sleep(self.pause)
            detail = self.fetch_summary(hit["court_url"])
        return {"found": True, **hit, **detail}


def parse_summary(text: str) -> dict:
    parties_blk = _section(text, "Parties", "Future Court Hearings", "All Court Hearings")
    parties = []
    for line in parties_blk.splitlines():
        line = _clean(line)
        if " - " in line and not line.startswith("Add Item"):
            parties.append(re.sub(r"\s+-\s+", " — ", line))
    # unique preserve order
    seen = set()
    uniq_parties = []
    for p in parties:
        if p not in seen:
            seen.add(p)
            uniq_parties.append(p)

    future_blk = _section(text, "Future Court Hearings", "All Court Hearings", "Document Register")
    hearings = []
    # date-like lines followed by type / location in nearby lines
    future_lines = [_clean(x) for x in future_blk.splitlines() if _clean(x)]
    skip = {
        "next hearing date & time",
        "hearing type",
        "courtroom location",
        "future court hearings",
    }
    future_lines = [x for x in future_lines if x.lower() not in skip]
    # group roughly every 3 meaningful lines
    buf = []
    for line in future_lines:
        if re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4}", line) and buf:
            hearings.append(" — ".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        hearings.append(" — ".join(buf))

    all_blk = _section(text, "All Court Hearings", "Document Register")
    filed = ""
    m = re.search(r"filed on\s+(\d{2}/\d{2}/\d{4})", all_blk, re.I)
    if m:
        filed = m.group(1)
    past = []
    for line in all_blk.splitlines():
        line = _clean(line)
        if re.match(r"^\d{2}/\d{2}/\d{4}", line):
            past.append(line)

    docs_blk = _section(text, "Document Register", "Attorney", "Invoices and Payments")
    docs = []
    doc_lines = [_clean(x) for x in docs_blk.splitlines() if _clean(x)]
    ignore = {
        "documents",
        "name",
        "date",
        "download",
        "download:",
        "document register",
    }
    i = 0
    while i < len(doc_lines):
        line = doc_lines[i]
        if line.lower() in ignore or line.lower().startswith("to view unavailable"):
            i += 1
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}$", line):
            i += 1
            continue
        date = ""
        if i + 1 < len(doc_lines) and re.match(r"^\d{2}/\d{2}/\d{4}$", doc_lines[i + 1]):
            date = doc_lines[i + 1]
            i += 2
        else:
            i += 1
        if line.lower() not in ignore:
            docs.append(f"{date} {line}".strip() if date else line)

    atty_blk = _section(text, "Attorney", "Invoices and Payments", "Back to Top")
    attorneys = []
    atty_lines = [_clean(x) for x in atty_blk.splitlines() if _clean(x)]
    skip_atty = {
        "date assigned",
        "assignment type",
        "name",
        "status",
        "representing/on behalf of",
        "attorney",
        "current",
    }
    for line in atty_lines:
        if line.lower() in skip_atty or re.match(r"^\d{2}/\d{2}/\d{4}$", line):
            continue
        attorneys.append(line)

    fees_blk = _section(text, "Invoices and Payments", "Back to Top", "Copyright")
    fees = [_clean(x) for x in fees_blk.splitlines() if _clean(x) and "add item" not in x.lower()]

    caption = ""
    m = re.search(r"(In [Rr]e the Estate of[^\n]+)", text)
    if m:
        caption = _clean(m.group(1))

    return {
        "caption": caption,
        "parties": uniq_parties,
        "hearings": hearings,
        "hearing_history": past,
        "filed_from_docket": filed,
        "documents": docs,
        "court_attorneys": attorneys,
        "fees": fees,
        "raw_text": text,
    }
