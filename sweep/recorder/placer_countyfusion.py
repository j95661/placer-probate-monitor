"""Placer CountyFusion guest recorder (Playwright) + HTML/JSON row parsing."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from .base import RecorderRow, RecorderSearchResult, RecorderSource

log = logging.getLogger(__name__)

LOGIN_URL = (
    "https://countyfusion4.kofiletech.us/countyweb/loginDisplay.action"
    "?countyname=Placer"
)
DOC_NUM_RE = re.compile(r"^\d{4}-\d{7}-\d{2}$")
DOC_NUM_FIND_RE = re.compile(r"\b(\d{4}-\d{7}-\d{2})\b")
DEFAULT_TTL_DAYS = 7
DEFAULT_SETTLE_S = 11.0
MAX_PAGES = 6
# Rough CountyFusion page size; ~600 rows ≈ 6 pages.
PAGE_SIZE_HINT = 100


def parse_result_rows(text: str) -> list[RecorderRow]:
    """Parse recorder result rows from saved HTML or TSV-ish text fixtures.

    Rows start with a doc number matching YYYY-#######-##. Captures doc#,
    names, other party, doc type, and record date when present.
    """
    rows: list[RecorderRow] = []
    if not text:
        return rows

    # JSON fixture short-circuit.
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and "rows" in payload:
            for item in payload["rows"]:
                row = _row_from_dict(item)
                if row:
                    rows.append(row)
            return rows
        if isinstance(payload, list):
            for item in payload:
                row = _row_from_dict(item)
                if row:
                    rows.append(row)
            return rows

    # HTML table cells or plain text lines.
    # Prefer line-oriented parse: doc# then tab/pipe/multi-space separated fields.
    for raw_line in text.splitlines():
        line = re.sub(r"<[^>]+>", " ", raw_line)
        line = re.sub(r"&nbsp;", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        m = DOC_NUM_FIND_RE.search(line)
        if not m:
            continue
        doc = m.group(1)
        rest = line[m.end() :].strip(" |-;\t")
        # Split on 2+ spaces or pipes/tabs.
        parts = re.split(r"\s{2,}|\t|\|", rest)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) == 1:
            # Single blob: try to peel a date and leave the middle as names/type.
            date_m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", rest)
            record_date = date_m.group(1) if date_m else ""
            without_date = rest
            if date_m:
                without_date = (rest[: date_m.start()] + " " + rest[date_m.end() :]).strip()
            # Doc type often ALL CAPS words at the end.
            type_m = re.search(
                r"(AFFIDAVIT(?:\s+OF\s+DEATH)?(?:[^A-Z][A-Z /-]*)?|"
                r"SUCCESSOR\s+TRUSTEE[^|]*|"
                r"GRANT\s+DEED|QUITCLAIM\s+DEED|TRUST\s+TRANSFER\s+DEED|"
                r"DEED(?:\s+OF\s+[A-Z ]+)?|"
                r"LIS\s+PENDENS(?:\s+WITHDRAWAL)?|"
                r"DECREE\s+OF\s+DISTRIBUTION|"
                r"SURVIVING\s+SPOUSE[^|]*|"
                r"TRANSFER\s+ON\s+DEATH|"
                r"LEASE)\b",
                without_date,
                re.I,
            )
            doc_type = type_m.group(0).strip().upper() if type_m else ""
            names = without_date
            if type_m:
                names = without_date[: type_m.start()].strip(" -|,")
            rows.append(
                RecorderRow(
                    doc_number=doc,
                    names=names,
                    other_party="",
                    doc_type=doc_type,
                    record_date=record_date,
                    raw={"line": line},
                )
            )
            continue

        names = parts[0] if parts else ""
        other = parts[1] if len(parts) > 1 else ""
        doc_type = parts[2] if len(parts) > 2 else ""
        record_date = parts[3] if len(parts) > 3 else ""
        # If date landed in doc_type slot, reshuffle.
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", doc_type or ""):
            record_date, doc_type = doc_type, other
            other = ""
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", other or ""):
            record_date, other = other, ""
        rows.append(
            RecorderRow(
                doc_number=doc,
                names=names,
                other_party=other,
                doc_type=doc_type.upper(),
                record_date=record_date,
                raw={"line": line, "parts": parts},
            )
        )

    # Deduplicate by doc number, keep first.
    seen: set[str] = set()
    unique: list[RecorderRow] = []
    for row in rows:
        if row.doc_number in seen:
            continue
        seen.add(row.doc_number)
        unique.append(row)
    return unique


def _row_from_dict(item: dict | None) -> RecorderRow | None:
    if not isinstance(item, dict):
        return None
    doc = str(item.get("doc_number") or item.get("doc") or "").strip()
    if not DOC_NUM_RE.match(doc):
        m = DOC_NUM_FIND_RE.search(doc)
        if not m:
            return None
        doc = m.group(1)
    return RecorderRow(
        doc_number=doc,
        names=str(item.get("names") or item.get("name") or "").strip(),
        other_party=str(item.get("other_party") or item.get("other") or "").strip(),
        doc_type=str(item.get("doc_type") or item.get("type") or "").strip().upper(),
        record_date=str(item.get("record_date") or item.get("date") or "").strip(),
        raw=item,
    )


def _safe_query_key(query: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", query.strip().upper())[:120]


class PlacerCountyFusionRecorder(RecorderSource):
    """Guest session against Placer CountyFusion via Playwright Chrome.

    Politeness: one browser session, one search at a time, ~10–12 s settle,
    hard cap per run. Cache raw results under data/recorder/<query>.json.
    """

    name = "placer_countyfusion"

    def __init__(
        self,
        cache_dir: Path,
        *,
        ttl_days: int = DEFAULT_TTL_DAYS,
        settle_s: float = DEFAULT_SETTLE_S,
        max_searches: int = 40,
        max_pages: int = MAX_PAGES,
        headless: bool = True,
        fixture_dir: Path | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self.settle_s = settle_s
        self.max_searches = max_searches
        self.max_pages = max_pages
        self.headless = headless
        self.fixture_dir = Path(fixture_dir) if fixture_dir else None
        self._search_count = 0
        self._pw = None
        self._browser = None
        self._page = None
        self._ready = False

    def _cache_path(self, query: str) -> Path:
        return self.cache_dir / f"{_safe_query_key(query)}.json"

    def _cache_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < timedelta(days=self.ttl_days)

    def _load_cache(self, query: str) -> RecorderSearchResult | None:
        path = self._cache_path(query)
        if not self._cache_fresh(path):
            # Also accept fixture dir as permanent cache.
            if self.fixture_dir:
                fpath = self.fixture_dir / f"{_safe_query_key(query)}.json"
                if fpath.exists():
                    path = fpath
                else:
                    return None
            else:
                return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        rows = parse_result_rows(json.dumps(payload))
        return RecorderSearchResult(
            query=query,
            rows=rows,
            truncated=bool(payload.get("truncated")),
            page_count=int(payload.get("page_count") or 0),
            cached=True,
        )

    def _save_cache(self, result: RecorderSearchResult) -> None:
        path = self._cache_path(result.query)
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    def search_name(
        self,
        name: str,
        *,
        from_date: str = "01/01/1980",
        refresh: bool = False,
    ) -> RecorderSearchResult:
        query = " ".join((name or "").upper().split())
        if not query:
            return RecorderSearchResult(query=query, rows=[])

        # Fixture-only mode (CI): never open a browser, even with --refresh.
        if self.fixture_dir is not None:
            fpath = self.fixture_dir / f"{_safe_query_key(query)}.json"
            if fpath.exists():
                payload = json.loads(fpath.read_text(encoding="utf-8"))
                rows = parse_result_rows(json.dumps(payload))
                result = RecorderSearchResult(
                    query=query,
                    rows=rows,
                    truncated=bool(payload.get("truncated")),
                    page_count=int(payload.get("page_count") or 1),
                    cached=True,
                )
                self._save_cache(result)
                return result
            log.warning("no fixture for recorder query %r", query)
            return RecorderSearchResult(query=query, rows=[], cached=True)

        if not refresh:
            cached = self._load_cache(query)
            if cached is not None:
                log.info("recorder cache hit for %r (%d rows)", query, len(cached.rows))
                return cached

        if self._search_count >= self.max_searches:
            log.warning("recorder search cap (%d) reached; skipping %r", self.max_searches, query)
            return RecorderSearchResult(query=query, rows=[], truncated=True)

        result = self._live_search(query, from_date=from_date)
        self._search_count += 1
        self._save_cache(result)
        return result

    def _ensure_browser(self) -> None:
        if self._ready:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "playwright is required for live CountyFusion searches"
            ) from exc

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        context = self._browser.new_context()
        self._page = context.new_page()
        page = self._page
        log.info("CountyFusion guest login")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.locator("input[value='Login as Guest']").click()
        page.wait_for_timeout(1500)
        body = page.frame_locator("frame[name='bodyframe'], iframe[name='bodyframe']")
        # Accept disclaimer.
        try:
            body.locator("#accept").click(timeout=8000)
        except Exception:
            # Some sessions land already accepted.
            pass
        page.wait_for_timeout(1000)
        # Search Public Records
        try:
            body.get_by_text("Search Public Records", exact=False).click(timeout=8000)
        except Exception:
            page.get_by_text("Search Public Records", exact=False).click(timeout=8000)
        page.wait_for_timeout(2000)
        self._ready = True

    def _live_search(self, query: str, *, from_date: str) -> RecorderSearchResult:
        self._ensure_browser()
        assert self._page is not None
        page = self._page
        body = page.frame_locator("frame[name='bodyframe'], iframe[name='bodyframe']")
        criteria = body.frame_locator(
            "frame[name='criteriaframe'], iframe[name='criteriaframe']"
        )

        log.info("CountyFusion search %r from %s", query, from_date)
        # Name + from-date easyui textboxes (observed indices).
        criteria.locator("#_easyui_textbox_input1").fill(query)
        criteria.locator("#_easyui_textbox_input3").fill(from_date)

        # executeSearchCommand in bodyframe
        page.evaluate(
            """() => {
              const body = document.querySelector("frame[name='bodyframe'], iframe[name='bodyframe']");
              const win = body && (body.contentWindow || body);
              if (win && typeof win.executeSearchCommand === 'function') {
                win.executeSearchCommand('search');
              }
            }"""
        )
        time.sleep(self.settle_s)

        all_rows: list[RecorderRow] = []
        pages_read = 0
        for page_idx in range(self.max_pages):
            pages_read += 1
            html = page.content()
            # Prefer results frames' text.
            try:
                for fr in page.frames:
                    if "result" in (fr.name or "").lower() or "datagrid" in (fr.url or "").lower():
                        html += "\n" + fr.content()
            except Exception:
                pass
            batch = parse_result_rows(html)
            # Also scrape visible text lines.
            try:
                text = page.inner_text("body")
                batch.extend(parse_result_rows(text))
            except Exception:
                pass

            before = {r.doc_number for r in all_rows}
            for row in batch:
                if row.doc_number not in before:
                    all_rows.append(row)
                    before.add(row.doc_number)

            # Try next page.
            moved = False
            try:
                next_btn = body.locator("a:has-text('Next'), .pagination-next, a.l-btn:has-text('>')")
                if next_btn.count() and next_btn.first.is_enabled():
                    next_btn.first.click()
                    time.sleep(self.settle_s)
                    moved = True
            except Exception:
                moved = False
            if not moved:
                break
            if page_idx >= self.max_pages - 1:
                break

        truncated = pages_read >= self.max_pages and len(all_rows) >= PAGE_SIZE_HINT * self.max_pages * 0.8
        # Surname-wide searches that fill ~600 rows are truncated.
        if len(all_rows) >= 550:
            truncated = True

        return RecorderSearchResult(
            query=query,
            rows=all_rows,
            truncated=truncated,
            page_count=pages_read,
            cached=False,
        )

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            self._browser = None
            self._page = None
            self._ready = False
            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None
