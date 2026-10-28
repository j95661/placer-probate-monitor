"""OCR fallback for stored petition PDFs with no usable text layer.

Gathers Path A fields we still need after native pypdf/AcroForm: petitioner
mailing, first/last name, decedent residence, estate_real GMV, and DE-147
phone. Email is taken when that duties OCR already runs. Does not OCR
already-complete text-layer GO petitions, fub_removed, or fiduciary.
Does not harvest unbound item-8 heir streets.

RapidOCR is optional on Home Assistant: it is not a manifest requirement
(that blocked the sidebar). Wheels are installed into this Python after
the panel loads, and again at the start of a rescan/harvest if needed.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

OCR_VERSION = 2
NATIVE_TEXT_MIN = 80
OCR_MAX_PAGES = 20
OCR_PAGE_TIMEOUT = 60
OCR_SCALE = 2.0
_MAILING_MIN = 8
_ENGINE = None
_ENGINE_NAME = ""
_ENSURED = False

# Headless stack. Do not use rapidocr-onnxruntime: it pulls opencv-python
# (non-headless) and that is what typically fails on Home Assistant OS.
OCR_PACKAGES = (
    "pypdfium2>=4.30.0",
    "onnxruntime>=1.17.0",
    "rapidocr>=3.0.0",
)

# Home Assistant OS 2026 is CPython 3.14 musllinux: onnxruntime has no wheels
# and RapidOCR cannot build pyclipper. Portable Tesseract still runs.
TESSERACT_RELEASE = "tesseract-5.5.3-rebuild"
TESSERACT_BUILDS = {
    "x86_64": (
        "https://github.com/DanielMYT/tesseract-static/releases/download/"
        f"{TESSERACT_RELEASE}/tesseract.x86_64",
        "3a1f6762075aa88b1a30c588e8520839bc0f647d9bfeed4829a719a08bfc0729",
    ),
    "amd64": (
        "https://github.com/DanielMYT/tesseract-static/releases/download/"
        f"{TESSERACT_RELEASE}/tesseract.x86_64",
        "3a1f6762075aa88b1a30c588e8520839bc0f647d9bfeed4829a719a08bfc0729",
    ),
    "aarch64": (
        "https://github.com/DanielMYT/tesseract-static/releases/download/"
        f"{TESSERACT_RELEASE}/tesseract.aarch64",
        "095a9c3ef2fa7107f1b318e6d59789bd8f14ad28e5d4097dc74f80d1874bdc5e",
    ),
    "arm64": (
        "https://github.com/DanielMYT/tesseract-static/releases/download/"
        f"{TESSERACT_RELEASE}/tesseract.aarch64",
        "095a9c3ef2fa7107f1b318e6d59789bd8f14ad28e5d4097dc74f80d1874bdc5e",
    ),
}
TESSDATA_ENG_URL = (
    "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata"
)

_CHROME_RE = re.compile(
    r"form adopted|judicial council|petition for probate|page \d+ of|"
    r"\bde-?111\b|\bde-?147\b|probate.decedents|superior court of california",
    re.I,
)
_SCRAP_RE = re.compile(
    r"waiver of bond|nomination of(?: the)? personal representative|"
    r"letters (?:of administration|testamentary)|continued on attachment|"
    r"attachment\s*\d+|i as the nominated|confidential attachment",
    re.I,
)
_BODY_HINT_RE = re.compile(
    r"\bitem\s*[238h]\b|gross fair market|estimated value|mailing address|"
    r"name and relationship|decedent died|petitioner is|"
    r"\d{1,6}\s+[A-Za-z].{0,40}\s(?:st|street|ave|avenue|rd|road|dr|drive|"
    r"ln|lane|way|ct|court|blvd|boulevard)\b",
    re.I,
)


def _ocr_max_pages() -> int:
    raw = str(os.environ.get("PPM_OCR_MAX_PAGES") or "").strip()
    try:
        return max(1, min(OCR_MAX_PAGES, int(raw))) if raw else OCR_MAX_PAGES
    except ValueError:
        return OCR_MAX_PAGES


def _ocr_page_timeout() -> int:
    raw = str(os.environ.get("PPM_OCR_PAGE_TIMEOUT") or "").strip()
    try:
        return max(10, min(180, int(raw))) if raw else OCR_PAGE_TIMEOUT
    except ValueError:
        return OCR_PAGE_TIMEOUT


def native_text_usable(text: str) -> bool:
    """True when pypdf extract is enough for the existing DE-111/DE-147 parser."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if len(raw) < NATIVE_TEXT_MIN:
        return False
    stripped = _CHROME_RE.sub(" ", raw)
    stripped = _SCRAP_RE.sub(" ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if len(stripped) < NATIVE_TEXT_MIN:
        return False
    return bool(_BODY_HINT_RE.search(stripped))


def _parse_helpers():
    try:
        from .petition_parse import (
            is_caption_name_part,
            is_junk_mailing_street,
            is_placeholder_estate_real,
            parse_money_amount,
            usable_go_person_name,
        )
    except ImportError:
        from petition_parse import (
            is_caption_name_part,
            is_junk_mailing_street,
            is_placeholder_estate_real,
            parse_money_amount,
            usable_go_person_name,
        )

    return (
        is_junk_mailing_street,
        is_placeholder_estate_real,
        parse_money_amount,
        usable_go_person_name,
        is_caption_name_part,
    )


def _mailing_ok(row: dict | None) -> bool:
    rec = row or {}
    line = str(rec.get("mailing_address") or rec.get("petitioner_address") or "").strip()
    if len(line) < _MAILING_MIN:
        return False
    is_junk_mailing_street, *_rest = _parse_helpers()
    return not is_junk_mailing_street(line)


def _name_ok(row: dict | None) -> bool:
    rec = row or {}
    (
        _junk,
        _placeholder,
        _money,
        usable_go_person_name,
        is_caption_name_part,
    ) = _parse_helpers()
    first = str(rec.get("petitioner_first") or "").strip()
    last = str(rec.get("petitioner_last") or "").strip()
    if (
        len(first) >= 2
        and len(last) >= 2
        and not is_caption_name_part(first)
        and not is_caption_name_part(last)
        and usable_go_person_name(f"{first} {last}")
    ):
        return True
    name = str(
        rec.get("petitioner")
        or rec.get("petitioner_name")
        or rec.get("item2b_name")
        or rec.get("attorney_for_name")
        or ""
    ).strip()
    return usable_go_person_name(name)


def _residence_ok(row: dict | None) -> bool:
    rec = row or {}
    line = str(rec.get("decedent_residence") or rec.get("decedent_address") or "").strip()
    if len(line) < _MAILING_MIN:
        return False
    is_junk_mailing_street, *_rest = _parse_helpers()
    return not is_junk_mailing_street(line)


def _phone_ok(row: dict | None) -> bool:
    rec = row or {}
    digits = re.sub(r"\D", "", str(rec.get("petitioner_phone") or rec.get("phone") or ""))
    return len(digits) >= 10


def _contact_ok(row: dict | None) -> bool:
    return _mailing_ok(row) and _name_ok(row)


def ocr_enabled() -> bool:
    flag = str(os.environ.get("PPM_PETITION_OCR", "1")).strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _gmv_ok(row: dict | None) -> bool:
    raw = (row or {}).get("estate_real")
    try:
        from .petition_parse import estate_real_needs_gmv_ocr
    except ImportError:
        from petition_parse import estate_real_needs_gmv_ocr

    return not estate_real_needs_gmv_ocr(raw)


def should_ocr_petition(
    *,
    listing: dict | None = None,
    parsed: dict | None = None,
    native_text: str = "",
) -> bool:
    """OCR DE-147 when mailing or petitioner phone is still missing.

    Email is filled from that same pass when present. Do not OCR a duties
    PDF only because email is empty (that usually grabs the law firm).
    """
    if not ocr_enabled():
        return False
    listing = listing or {}
    parsed = parsed or {}
    if listing.get("fub_removed") or parsed.get("fub_removed"):
        return False
    if listing.get("professional_fiduciary") or parsed.get("professional_fiduciary"):
        return False
    mailing = _mailing_ok(parsed) or _mailing_ok(listing)
    phone = _phone_ok(parsed) or _phone_ok(listing)
    if mailing and phone:
        return False
    if mailing:
        return True
    if native_text_usable(native_text):
        return False
    return True


def should_ocr_needed(
    *,
    listing: dict | None = None,
    parsed: dict | None = None,
    native_text: str = "",
) -> bool:
    """OCR DE-111 when name, mailing, or decedent residence is still missing.

    GMV has should_ocr_gmv. Skips when name, mailing, and residence are already
    parsed and native text is usable. Attachment/chrome scraps are not usable.
    """
    if not ocr_enabled():
        return False
    listing = listing or {}
    parsed = parsed or {}
    if listing.get("fub_removed") or parsed.get("fub_removed"):
        return False
    if listing.get("professional_fiduciary") or parsed.get("professional_fiduciary"):
        return False
    contact = _contact_ok(parsed) or _contact_ok(listing)
    residence = _residence_ok(parsed) or _residence_ok(listing)
    gmv = _gmv_ok(parsed) or _gmv_ok(listing)
    if contact and residence and gmv:
        return False
    if native_text_usable(native_text) and contact and residence:
        return False
    return True


def should_ocr_gmv(
    *,
    listing: dict | None = None,
    parsed: dict | None = None,
    native_text: str = "",
) -> bool:
    """OCR DE-111 for GMV when estate_real is still empty.

    Runs after mailing OCR, including when mailing is already filled.
    Attachment/chrome native text is not a skip: GMV often lives on a
    scanned item-3 page. Prior listing estate_real including $0 is kept
    (do not OCR it away). Skips fiduciary and fub_removed.
    """
    del native_text
    if not ocr_enabled():
        return False
    listing = listing or {}
    parsed = parsed or {}
    if listing.get("fub_removed") or parsed.get("fub_removed"):
        return False
    if listing.get("professional_fiduciary") or parsed.get("professional_fiduciary"):
        return False
    if _gmv_ok(parsed) or _gmv_ok(listing):
        return False
    return True


def _cache_path(pdf_path: Path) -> Path:
    return Path(str(pdf_path) + ".ocr.txt")


def _cache_key(pdf_path: Path, engine: str = "") -> str:
    stat = pdf_path.stat()
    return (
        f"# ppm-ocr v{OCR_VERSION} engine={engine or 'none'} "
        f"size={stat.st_size} mtime={int(stat.st_mtime)}"
    )


def _read_cache(pdf_path: Path, engine: str = "") -> str | None:
    cache = _cache_path(pdf_path)
    if not cache.is_file():
        return None
    try:
        raw = cache.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    first, _, rest = raw.partition("\n")
    if first.strip() != _cache_key(pdf_path, engine):
        return None
    return rest


def _write_cache(pdf_path: Path, text: str, engine: str = "") -> None:
    cache = _cache_path(pdf_path)
    try:
        cache.write_text(_cache_key(pdf_path, engine) + "\n" + (text or ""), encoding="utf-8")
    except OSError:
        pass


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _renderer_ok() -> bool:
    return _importable("pypdfium2")


def _reset_engine() -> None:
    global _ENGINE, _ENGINE_NAME
    _ENGINE = None
    _ENGINE_NAME = ""


def _skip_install() -> bool:
    flag = str(os.environ.get("PPM_SKIP_OCR_INSTALL") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    # Laptop unit tests import unittest; Home Assistant jobs can import homeassistant.
    if "unittest" in sys.modules and not _importable("homeassistant"):
        return True
    return False


def ocr_dir() -> Path:
    raw = str(os.environ.get("PPM_OCR_DIR") or "").strip()
    if raw:
        path = Path(raw)
    else:
        shared = Path("/config/placer_probate_monitor/ocr")
        path = shared if shared.parent.is_dir() else Path(tempfile.gettempdir()) / "ppm-ocr"
    path.mkdir(parents=True, exist_ok=True)
    (path / "tessdata").mkdir(parents=True, exist_ok=True)
    return path


def _tesseract_cmd() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    local = ocr_dir() / "tesseract"
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    win = Path(os.environ.get("ProgramFiles") or r"C:\Program Files") / "Tesseract-OCR" / "tesseract.exe"
    if win.is_file():
        return str(win)
    return None


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp:
        tmp.write_bytes(resp.read())
    tmp.replace(dest)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bootstrap_tesseract() -> str | None:
    """Download a static Tesseract into PPM_OCR_DIR when RapidOCR cannot install."""
    existing = _tesseract_cmd()
    if existing:
        return existing
    machine = platform.machine().lower()
    spec = TESSERACT_BUILDS.get(machine)
    if spec is None:
        print(f"OCR tesseract: no static binary for {machine}", flush=True)
        return None
    url, expected = spec
    root = ocr_dir()
    binary = root / "tesseract"
    trained = root / "tessdata" / "eng.traineddata"
    try:
        if not binary.is_file() or _sha256(binary) != expected:
            print(f"Downloading portable Tesseract for {machine}…", flush=True)
            _download(url, binary)
            if _sha256(binary) != expected:
                print("OCR tesseract: checksum mismatch, ignoring download", flush=True)
                binary.unlink(missing_ok=True)
                return None
        os.chmod(binary, 0o755)
        if not trained.is_file() or trained.stat().st_size < 1000:
            print("Downloading Tesseract English traineddata…", flush=True)
            _download(TESSDATA_ENG_URL, trained)
    except Exception as exc:  # noqa: BLE001
        print(f"OCR tesseract download failed: {exc}", flush=True)
        return None
    if binary.is_file() and os.access(binary, os.X_OK):
        return str(binary)
    return None


def _progress(step: str, message: str) -> None:
    try:
        from .job_progress import report_progress
    except ImportError:
        try:
            from job_progress import report_progress
        except ImportError:
            print(message, flush=True)
            return
    report_progress(step, message)


def _prefer_tesseract() -> bool:
    return str(os.environ.get("PPM_OCR_ENGINE") or "").strip().lower() in {
        "tesseract",
        "tess",
    }


def _load_engine():
    global _ENGINE, _ENGINE_NAME
    if _ENGINE_NAME:
        return _ENGINE, _ENGINE_NAME
    if _prefer_tesseract():
        tess = _tesseract_cmd()
        if tess:
            _ENGINE = tess
            _ENGINE_NAME = "tesseract"
            return _ENGINE, _ENGINE_NAME
    try:
        from rapidocr import RapidOCR

        _ENGINE = RapidOCR()
        _ENGINE_NAME = "rapidocr"
        return _ENGINE, _ENGINE_NAME
    except Exception:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
        _ENGINE_NAME = "rapidocr"
        return _ENGINE, _ENGINE_NAME
    except Exception:
        pass
    tess = _tesseract_cmd()
    if tess:
        _ENGINE = tess
        _ENGINE_NAME = "tesseract"
        return _ENGINE, _ENGINE_NAME
    _ENGINE_NAME = "none"
    return None, _ENGINE_NAME


def ocr_status() -> dict:
    """Current engine/renderer without installing packages."""
    engine, name = _load_engine()
    ready = bool(
        ocr_enabled()
        and name not in {"", "none"}
        and engine is not None
        and _renderer_ok()
    )
    return {
        "ready": ready,
        "engine": name or "none",
        "renderer": "pypdfium2" if _renderer_ok() else "none",
        "enabled": ocr_enabled(),
    }


def _install_one(package: str) -> bool:
    try:
        from homeassistant.util.package import install_package, is_installed

        try:
            if is_installed(package):
                return True
        except Exception:
            pass
        try:
            return bool(install_package(package, upgrade=False, timeout=300))
        except TypeError:
            return bool(install_package(package, upgrade=False))
    except Exception:
        pass
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                package,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[-500:]
            print(f"OCR pip failed {package}: {err}", flush=True)
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print(f"OCR pip error {package}: {exc}", flush=True)
        return False


def _lock_path() -> Path:
    return Path(tempfile.gettempdir()) / "ppm_ocr_install.lock"


def ensure_ocr_packages() -> dict:
    """Install RapidOCR wheels into this interpreter if they are missing.

    Safe to call from Home Assistant setup and from harvest/rescan. Never
    raises. Tests set PPM_SKIP_OCR_INSTALL=1 so pip is not invoked.
    """
    global _ENSURED
    if not ocr_enabled():
        return ocr_status()
    status = ocr_status()
    if status["ready"]:
        _ENSURED = True
        return status
    if _skip_install():
        return status
    lock = _lock_path()
    started = time.time()
    while lock.exists() and time.time() - started < 360:
        time.sleep(2)
        _reset_engine()
        status = ocr_status()
        if status["ready"]:
            _ENSURED = True
            return status
    if _ENSURED:
        _reset_engine()
        return ocr_status()
    _ENSURED = True
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii", "replace"))
        os.close(fd)
        owned = True
    except FileExistsError:
        owned = False
    if not owned:
        started = time.time()
        while lock.exists() and time.time() - started < 360:
            time.sleep(2)
        _reset_engine()
        return ocr_status()
    try:
        _progress(
            "ocr_install",
            "Installing RapidOCR on this Home Assistant box (once, not in the sidebar load)…",
        )
        print("Installing optional petition OCR packages…", flush=True)
        for package in OCR_PACKAGES:
            ok = _install_one(package)
            print(f"OCR pip {package}: {'ok' if ok else 'failed'}", flush=True)
        _reset_engine()
        status = ocr_status()
        if not status["ready"]:
            _progress(
                "ocr_install",
                "RapidOCR wheels are not available on this Home Assistant Python; installing portable Tesseract…",
            )
            _bootstrap_tesseract()
            _reset_engine()
            status = ocr_status()
        if status["ready"]:
            _progress("ocr_ready", f"Petition OCR ready ({status['engine']}).")
            print(f"Petition OCR ready ({status['engine']})", flush=True)
        else:
            _progress(
                "ocr_missing",
                "Petition OCR did not install; image petitions stay native-text only.",
            )
            print(
                "Petition OCR unavailable after install; image petitions stay native-text only.",
                flush=True,
            )
        return status
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _ocr_rapid(engine, image) -> str:
    import numpy as np

    arr = np.array(image.convert("RGB"))
    result = engine(arr)
    if hasattr(result, "txts"):
        return "\n".join(str(item) for item in (result.txts or []) if item)
    rows = result
    if isinstance(result, (tuple, list)) and result and not isinstance(result[0], (list, tuple)):
        rows = result
    elif isinstance(result, tuple):
        rows = result[0]
    lines: list[str] = []
    for item in rows or []:
        if isinstance(item, str):
            lines.append(item)
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            lines.append(str(item[1]))
            continue
        if isinstance(item, dict) and item.get("txt"):
            lines.append(str(item.get("txt")))
    return "\n".join(line for line in lines if line.strip())


def _ocr_tesseract(image, command: str | None = None) -> str:
    cmd = command or _tesseract_cmd()
    if not cmd:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp = Path(handle.name)
    try:
        image.convert("RGB").save(temp, format="PNG")
        args = [cmd, str(temp), "stdout", "--psm", "6"]
        tessdata = ocr_dir() / "tessdata"
        if (tessdata / "eng.traineddata").is_file():
            args.extend(["--tessdata-dir", str(tessdata)])
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_ocr_page_timeout(),
        )
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def _render_pages(pdf_path: Path):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return
    doc = pdfium.PdfDocument(str(pdf_path))
    count = min(len(doc), _ocr_max_pages())
    for index in range(count):
        page = doc[index]
        bitmap = page.render(scale=OCR_SCALE)
        try:
            yield bitmap.to_pil()
        finally:
            bitmap.close()
            page.close()
    doc.close()


def ocr_pdf_text(path: Path | None) -> str:
    """Render pages and OCR. Cached beside the PDF. Empty if no engine or error."""
    if path is None or not Path(path).is_file():
        return ""
    pdf_path = Path(path)
    try:
        if pdf_path.stat().st_size < 10_000:
            return ""
    except OSError:
        return ""
    ensure_ocr_packages()
    engine, name = _load_engine()
    cached = _read_cache(pdf_path, name)
    if cached is not None:
        return cached
    if name == "none" or engine is None:
        print(f"OCR skip {pdf_path.name}: no RapidOCR or tesseract", flush=True)
        return ""
    if not _renderer_ok():
        print(f"OCR skip {pdf_path.name}: pypdfium2 not installed", flush=True)
        return ""
    parts: list[str] = []
    try:
        for image in _render_pages(pdf_path):
            try:
                if name == "tesseract":
                    parts.append(_ocr_tesseract(image, engine if isinstance(engine, str) else None))
                else:
                    parts.append(_ocr_rapid(engine, image))
            finally:
                image.close()
    except Exception as exc:  # noqa: BLE001
        print(f"OCR failed {pdf_path.name}: {exc}", flush=True)
        return ""
    text = "\n".join(part.strip() for part in parts if part and part.strip())
    if not text:
        return ""
    _write_cache(pdf_path, text, name)
    return text
