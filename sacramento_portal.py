#!/usr/bin/env python3
"""Sacramento Superior Court public-portal lookups.

Journal Technologies eCourt, not Placer's Tyler eCourt Public site.
Case-number search is node/429. The result link (node/430/id) is a
documents-only page and 404s if it is opened without the search session.
The full case summary is the same id on node/397 and can be opened directly.

The public summary (parties, hearings, register of actions, document
titles) works logged out. Document images are not downloaded. Rows
marked Not Viewable are confidential and are omitted. No portal
password is stored or sent.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PORTAL_BASE = "https://prod-portal-sacramento-ca.journaltech.com/public-portal/"
PORTAL_SEARCH = PORTAL_BASE + "?q=node/429"
SUMMARY_NODE = "397"
USER_AGENT = (
    "Mozilla/5.0 (compatible; HammondProbateMonitor/1.0; "
    "+local research digest)"
)
CASE_ID_RE = re.compile(r"node/(?:397|430)/(\d+)")
CONFIDENTIAL_TITLES = {"not viewable", "confidential", "sealed"}


def _clean(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _is_confidential_title(name: str) -> bool:
    low = _clean(name).lower()
    return low in CONFIDENTIAL_TITLES or "not viewable" in low


class SacramentoPortal:
    def __init__(self, pause: float = 1.2) -> None:
        self.pause = pause
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _form_payload(self) -> tuple[str, dict]:
        resp = self.session.get(PORTAL_SEARCH, timeout=45)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.find("form", id="ecp-searchform-form") or soup.find("form")
        if not form:
            raise RuntimeError("Sacramento case-search form not found")
        data = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name and name != "op":
                data[name] = inp.get("value") or ""
        action = urljoin(PORTAL_BASE, form.get("action") or "?q=node/429")
        return action, data

    def search_case(self, case_number: str) -> dict | None:
        for operator in ("EQUALS", "CONTAINS"):
            action, data = self._form_payload()
            data["data(82311)"] = case_number
            data["data(82311_op)"] = operator
            data["op"] = "Search"
            resp = self.session.post(action, data=data, timeout=45)
            resp.raise_for_status()
            hit = _parse_search(resp.text, case_number)
            if hit:
                return hit
            time.sleep(self.pause)
        return None

    def fetch_summary(self, summary_id: str) -> dict:
        url = f"{PORTAL_BASE}?q=node/{SUMMARY_NODE}/{summary_id}"
        resp = self.session.get(url, timeout=45)
        resp.raise_for_status()
        if "could not be found" in resp.text or "Page not found" in resp.text:
            return {"error": "case summary 404", "court_url": url}
        parsed = parse_summary(resp.text)
        parsed["court_url"] = url
        return parsed

    def enrich(self, case_number: str) -> dict:
        time.sleep(self.pause)
        hit = self.search_case(case_number)
        if not hit:
            return {"found": False, "case_number": case_number}
        detail = {}
        if hit.get("summary_id"):
            time.sleep(self.pause)
            detail = self.fetch_summary(hit["summary_id"])
        merged = {"found": True, **hit, **detail}
        if detail.get("error"):
            merged["found"] = False
        return merged


def _parse_search(html: str, case_number: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    by_id: dict[str, list[str]] = {}
    for link in soup.find_all("a", href=True):
        match = CASE_ID_RE.search(link["href"])
        if not match:
            continue
        text = _clean(link.get_text(" ", strip=True))
        if not text or text.lower() in {"case number", "case name"}:
            continue
        by_id.setdefault(match.group(1), []).append(text)
    wanted = case_number.upper()
    for summary_id, labels in by_id.items():
        if not any(wanted in label.upper() for label in labels):
            continue
        caption = next((label for label in labels if wanted not in label.upper()), "")
        return {
            "case_number": case_number,
            "caption": caption,
            "summary_id": summary_id,
            "court_url": f"{PORTAL_BASE}?q=node/{SUMMARY_NODE}/{summary_id}",
        }
    return None


def _pane_rows(soup: BeautifulSoup, pane_index: int) -> list[list[str]]:
    panes = soup.select("div.tabpane")
    if pane_index >= len(panes):
        return []
    table = panes[pane_index].select_one("table.table")
    if not table:
        return []
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        cells = [cell for cell in cells if cell]
        if not cells:
            continue
        head = cells[0].lower()
        if head in {"name", "filed / status date", "date", "filter rows"}:
            continue
        if head.startswith("view document") or "loading" in head:
            continue
        rows.append(cells)
    return rows


def _uniq(items: list[str]) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _party_line(name: str, role: str) -> str:
    """Match the Placer dossier shape ``Role — Name`` that FUB already reads."""
    trimmed = re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip()
    role = _clean(role)
    if role and not re.match(r"\d{2}/\d{2}/\d{4}", role):
        return f"{role} — {trimmed or name}"
    return trimmed or name


def parse_summary(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one("table.caseHeader")
    caption = ""
    case_type = ""
    category = ""
    courthouse = ""
    filed = ""
    next_event = ""
    department = ""
    if header:
        title_cell = header.select_one("td.caseheaderXLtext") or header.find("td")
        bolds = [_clean(b.get_text(" ", strip=True)) for b in header.find_all("b")]
        case_no = bolds[0] if bolds else ""
        if len(bolds) > 1:
            case_type = bolds[1]
        if title_cell:
            caption = _clean(title_cell.get_text(" ", strip=True))
            if case_no:
                caption = _clean(re.sub(rf"^{re.escape(case_no)}\s*", "", caption))
        for span in header.find_all("span"):
            title = _clean(span.get("title") or "")
            visible = _clean(span.get_text(" ", strip=True))
            if not title:
                continue
            if title.lower() == "date filed":
                match = re.search(r"(\d{2}/\d{2}/\d{4})", visible)
                filed = match.group(1) if match else filed
            elif title.lower().startswith("next event"):
                next_event = re.sub(r"^Next Event\s*", "", title, flags=re.I).strip()
            elif "courthouse" in title.lower() or "family relations" in title.lower():
                courthouse = title
            elif title.lower() not in {"date filed"} and len(title) > 12 and not category:
                category = title
        dept = re.search(r"DEPT\.?\s*\d+[^/\n]{0,40}", header.get_text(" ", strip=True), re.I)
        if dept:
            department = _clean(dept.group(0))

    documents = []
    filers = []
    for cells in _pane_rows(soup, 0):
        if len(cells) < 2 or not re.match(r"\d{2}/\d{2}/\d{4}", cells[0]):
            continue
        title = cells[1]
        if _is_confidential_title(title):
            continue
        documents.append(f"{cells[0]} {title}".strip())
        if len(cells) > 2 and cells[2] and cells[2].lower() not in {"clerk", "image"}:
            filers.append(cells[2])

    parties = []
    for cells in _pane_rows(soup, 2):
        name = cells[0]
        role = cells[2] if len(cells) > 2 else (cells[1] if len(cells) > 1 else "")
        if name.lower() == "aka/dba":
            continue
        parties.append(_party_line(name, role))

    hearings = []
    history = []
    for cells in _pane_rows(soup, 3):
        if len(cells) < 3:
            continue
        name, when, status = cells[0], cells[1], cells[2]
        place = cells[3] if len(cells) > 3 else ""
        line = " — ".join(part for part in (when, name, status, place) if part)
        if status.lower() == "scheduled":
            hearings.append(line)
        else:
            history.append(line)

    parties = _uniq(parties)
    hearings = _uniq(hearings)
    history = _uniq(history)
    documents = _uniq(documents)
    if not next_event and hearings:
        next_event = hearings[0]
    previous_event = history[0] if history else ""

    attorneys = []
    for party in parties:
        if "attorney" in party.lower():
            attorneys.append(party)
    if not attorneys:
        for filer in filers:
            if re.search(r"\bSBN\b|attorney", filer, re.I):
                attorneys.append(filer)
    attorneys = _uniq(attorneys)

    return {
        "caption": caption,
        "case_type": case_type,
        "category": category,
        "courthouse": " — ".join(part for part in (courthouse, department) if part),
        "filed": filed,
        "filed_from_docket": filed,
        "next_event": next_event,
        "previous_event": previous_event,
        "parties": parties,
        "hearings": hearings,
        "hearing_history": history,
        "documents": documents,
        "court_attorneys": attorneys,
        "fees": [],
    }
