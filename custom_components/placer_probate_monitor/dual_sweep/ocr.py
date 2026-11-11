"""Stage 2: DE-111 PDF OCR + field extraction."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
MONEY_RE = re.compile(
    r"(?:gross\s+fair\s+market\s+value|real\s+property|estate[_\s-]*real|"
    r"gmv\s*real|character\s+and\s+estimated\s+value)[^\n$]{0,80}"
    r"\$?\s*([\d,]+\.?\d*)",
    re.I,
)
DOD_RE = re.compile(
    r"(?:decedent\s+died\s+on(?:\s*\(date\))?\s*:?\s*|date\s+of\s+death\s*:?\s*)"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})",
    re.I,
)
HEARING_RE = re.compile(
    r"hearing\s+date(?:\s+and\s+time)?\s*:?\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})"
    r"(?:[^\n]{0,40}?dept\.?\s*:?\s*(?P<dept>[A-Za-z0-9\-]+))?",
    re.I,
)
_NAME_TOKEN = r"[A-Z][A-Za-z.'\-]+"
_NAME_STOP = (
    r"(?=\s+(?:heir|devisee|beneficiary|located|residence|petitioner|relationship|"
    r"died|deceased|predeceased|spouse|hearing|form|character|gross|item)\b|,|\s*$)"
)
SPOUSE_DECEASED_RE = re.compile(
    # Avoid the "Spouse name:" label (re.I makes [A-Z] match "name").
    # Word-boundary before death keyword so "pre"+"deceased" ≠ name+keyword.
    r"(?:spouse|surviving\s+spouse|husband|wife)\s+"
    r"(?!(?:name|names|predeceased|deceased|died)\b)"
    rf"(?P<name>{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})"
    r"[^\n]{0,80}?\b(?:died|deceased|predeceased)\b(?:\s+on)?"
    r"\s*(?P<date>\d{1,2}/\d{1,2}/\d{2,4})?",
    re.I,
)
SPOUSE_NAME_RE = re.compile(
    r"(?:name\s+of\s+spouse|spouse(?:'s)?\s+name)\s*:?\s*"
    rf"(?P<name>{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}}?){_NAME_STOP}",
    re.I,
)
HEIR_LINE_RE = re.compile(
    r"(?:heir|devisee|beneficiary)\s*:?\s*"
    rf"(?P<name>{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}}?){_NAME_STOP}",
    re.I,
)
ADDR_RE = re.compile(
    r"\b(\d{1,6}\s+[A-Za-z0-9.'\-]+(?:\s+[A-Za-z0-9.'\-]+){0,5}\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Way|Court|Ct|"
    r"Boulevard|Blvd|Circle|Cir|Place|Pl)\.?)"
    r"(?:\s*,\s*([A-Za-z][A-Za-z .'-]{1,40}?))"
    r"(?="
    r"\s*,\s*(?:[A-Za-z][A-Za-z .'-]*\s+County|[A-Za-z]{2}\b|California|\d{5})"
    r")"
    r"(?:\s*,\s*(?:([A-Za-z][A-Za-z .'-]*)\s+County))?"
    r"(?:\s*,\s*(CA|California))?"
    r"(?:\s+(\d{5}(?:-\d{4})?))?",
    re.I,
)


@dataclass
class De111Fields:
    case_number: str
    date_of_death: str = ""
    estate_real: str = ""
    hearing_date: str = ""
    hearing_dept: str = ""
    spouse_name: str = ""
    spouse_deceased: bool = False
    spouse_dod: str = ""
    heirs: list[str] = field(default_factory=list)
    property_address: str = ""
    residence_address: str = ""
    ocr_text_path: str = ""
    confidence: str = "typed"  # typed | low (checkbox OCR)
    raw_excerpt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _sort_ocr_lines(boxes: list) -> list[str]:
    """Sort RapidOCR boxes by (y/12, x) then join into lines."""
    rows: list[tuple[float, float, str]] = []
    for item in boxes:
        # rapidocr_onnxruntime: [box, text, score]
        if not item or len(item) < 2:
            continue
        box, text = item[0], item[1]
        if not text:
            continue
        try:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x = min(xs)
            y = min(ys)
        except (TypeError, IndexError, KeyError):
            continue
        rows.append((y / 12.0, x, str(text)))
    rows.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in rows]


def pdf_to_png_pages(pdf_path: Path, out_dir: Path, first: int = 1, last: int = 4) -> list[Path]:
    """Render PDF pages with pdftoppm. Requires poppler-utils."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    cmd = [
        "pdftoppm",
        "-r",
        "150",
        "-f",
        str(first),
        "-l",
        str(last),
        "-png",
        str(pdf_path),
        str(prefix),
    ]
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm not found; install poppler-utils")
    subprocess.run(cmd, check=True, capture_output=True)
    pages = sorted(out_dir.glob("page-*.png"))
    if not pages:
        pages = sorted(out_dir.glob("page*.png"))
    return pages


def ocr_png(path: Path) -> list[str]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "rapidocr_onnxruntime is required for live OCR; "
            "use cached .ocr.txt fixtures in tests"
        ) from exc
    engine = RapidOCR()
    result, _ = engine(str(path))
    if not result:
        return []
    return _sort_ocr_lines(result)


def ocr_pdf(
    pdf_path: Path,
    text_cache: Path,
    *,
    refresh: bool = False,
    max_pages: int = 4,
) -> str:
    """OCR pages 1–max_pages; cache plaintext at text_cache."""
    if text_cache.exists() and text_cache.stat().st_size > 0 and not refresh:
        return text_cache.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="de111-ocr-") as tmp:
        pages = pdf_to_png_pages(pdf_path, Path(tmp), first=1, last=max_pages)
        lines: list[str] = []
        for page in pages:
            lines.extend(ocr_png(page))
            lines.append("")  # page break
        text = "\n".join(lines)
    text_cache.parent.mkdir(parents=True, exist_ok=True)
    text_cache.write_text(text, encoding="utf-8")
    return text


def _norm_date(raw: str) -> str:
    m = DATE_RE.search(raw or "")
    if not m:
        return ""
    parts = m.group(1).split("/")
    if len(parts) != 3:
        return m.group(1)
    mm, dd, yy = parts
    if len(yy) == 2:
        yy = ("20" if int(yy) < 70 else "19") + yy
    return f"{int(mm):02d}/{int(dd):02d}/{yy}"


def extract_de111_fields(case_number: str, text: str) -> De111Fields:
    """Pull typed name/date lines from OCR or native text. Checkbox OCR = low confidence."""
    fields = De111Fields(case_number=case_number, raw_excerpt=text[:2000])
    flat = re.sub(r"[ \t]+", " ", text)

    dod = DOD_RE.search(flat)
    if dod:
        fields.date_of_death = _norm_date(dod.group("date"))

    money = MONEY_RE.search(flat)
    if money:
        fields.estate_real = money.group(1).replace(",", "")

    hearing = HEARING_RE.search(flat)
    if hearing:
        fields.hearing_date = _norm_date(hearing.group("date"))
        fields.hearing_dept = (hearing.group("dept") or "").upper()

    spouse_dead = SPOUSE_DECEASED_RE.search(flat)
    if spouse_dead:
        fields.spouse_name = re.sub(r"\s+", " ", spouse_dead.group("name")).strip().upper()
        fields.spouse_deceased = True
        fields.spouse_dod = _norm_date(spouse_dead.group("date") or "")
    else:
        spouse = SPOUSE_NAME_RE.search(flat)
        if spouse:
            fields.spouse_name = re.sub(r"\s+", " ", spouse.group("name")).strip().upper()
        if re.search(r"\b(?:spouse\s+predeceased|predeceased\s+spouse)\b", flat, re.I):
            fields.spouse_deceased = True

    heirs: list[str] = []
    for m in HEIR_LINE_RE.finditer(flat):
        name = re.sub(r"\s+", " ", m.group("name")).strip().upper()
        if name and name not in heirs:
            heirs.append(name)
    fields.heirs = heirs

    # Prefer an address near "located at" / estate / real property over residence.
    property_hint = re.search(
        r"(?:located\s+at|real\s+property|estate\s+located|property\s+address)\s*:?\s*"
        r"([^\n]{10,120})",
        flat,
        re.I,
    )
    if property_hint:
        am = ADDR_RE.search(property_hint.group(1))
        if am:
            fields.property_address = _format_addr(am)

    residence_hint = re.search(
        r"residence\s+at\s+time\s+of\s+death[^\n]{0,40}:?\s*([^\n]{10,120})",
        flat,
        re.I,
    )
    if residence_hint:
        am = ADDR_RE.search(residence_hint.group(1))
        if am:
            fields.residence_address = _format_addr(am)

    if not fields.property_address:
        # Fall back to first street-looking address in the body.
        for am in ADDR_RE.finditer(flat):
            fields.property_address = _format_addr(am)
            break

    # Checkbox regions are unreliable; mark low when we only have marks without typed spouse death.
    if re.search(r"\[\s*[xX✓✔]\s*\].{0,40}spouse", flat) and not fields.spouse_deceased:
        fields.confidence = "low"

    return fields


def _format_addr(am: re.Match) -> str:
    street = re.sub(r"\s+", " ", am.group(1)).strip()
    city = re.sub(r"\s+", " ", (am.group(2) or "")).strip(" ,")
    # Guard against non-greedy city collapsing to a single letter.
    if len(city) <= 1:
        city = ""
    county = re.sub(r"\s+", " ", (am.group(3) or "")).strip(" ,")
    state = (am.group(4) or "CA").strip()
    if state.lower() == "california":
        state = "CA"
    z = (am.group(5) or "").strip()
    parts = [street]
    if city:
        parts.append(city.title() if city.isupper() else city)
    if county and "placer" in county.lower():
        parts.append("Placer County")
    parts.append(state.upper() if len(state) <= 2 else state)
    if z:
        parts.append(z)
    return ", ".join(parts)


def load_or_ocr(
    case_number: str,
    pdf_path: Path | None,
    cache_dir: Path,
    *,
    refresh: bool = False,
) -> De111Fields:
    """Prefer cached OCR text; OCR the PDF only when needed."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    text_path = cache_dir / f"{case_number}.ocr.txt"
    text = ""
    if text_path.exists() and not refresh:
        text = text_path.read_text(encoding="utf-8")
    elif pdf_path and pdf_path.exists():
        text = ocr_pdf(pdf_path, text_path, refresh=refresh)
    elif text_path.exists():
        text = text_path.read_text(encoding="utf-8")
    else:
        log.warning("no DE-111 OCR/PDF for %s", case_number)
        return De111Fields(case_number=case_number, confidence="missing")

    fields = extract_de111_fields(case_number, text)
    fields.ocr_text_path = str(text_path)
    return fields
