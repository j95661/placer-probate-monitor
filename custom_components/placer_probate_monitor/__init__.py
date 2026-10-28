"""Placer Probate Monitor Home Assistant integration."""

from __future__ import annotations

import logging
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_FUB_ERROR,
    ATTR_FUB_POSTED,
    ATTR_FUB_SKIPPED,
    ATTR_FUB_UPDATED,
    ATTR_FUB_VERIFY,
    ATTR_ECOURT_VIEW_LIMIT,
    ATTR_LAST_ERROR,
    ATTR_LAST_RESULT,
    ATTR_LAST_RUN,
    ATTR_NEW_COUNT,
    ATTR_NOTICE_COUNT,
    ATTR_PDF,
    EVENT_ECOURT_VIEW_LIMIT,
    CONF_COUNTY,
    CONF_ECOURT_PAUSE,
    CONF_FREQUENCY,
    CONF_FUB_API_KEY,
    CONF_FUB_SYSTEM_KEY,
    CONF_FUB_API_URL,
    CONF_FUB_ASSIGNED_TO,
    CONF_FUB_STAGE,
    CONF_FUB_ENABLED,
    CONF_FUB_EVENT_TYPE,
    CONF_FUB_SOURCE,
    CONF_FUB_VERIFY_ONLY,
    CONF_FUB_UPDATE_EXISTING,
    CONF_FUB_VERIFY_EXISTING,
    CONF_FUB_VERIFY_PERSON_ID,
    CONF_GENERATE_PDF,
    CONF_KEYWORDS,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_MAIL_FROM,
    CONF_MAX_PAGES,
    CONF_MONTHLY_DAY,
    CONF_RECIPIENTS,
    CONF_RUN_ON_START,
    CONF_RUN_TIME,
    CONF_SACRAMENTO_PORTAL_PASSWORD,
    CONF_SACRAMENTO_PORTAL_USER,
    CONF_SEND_EMAIL,
    CONF_SKIP_PORTAL,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_USER,
    CONF_TIMEZONE,
    CONF_WEEKLY_DAY,
    CONF_AUDIT_WEEKLY,
    DEFAULTS,
    DOMAIN,
    WEEKDAYS,
)

AUDIT_WEEKLY_HOUR = 20

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
COMPONENT_DIR = Path(__file__).resolve().parent


def merged_options(entry: ConfigEntry) -> dict:
    return {**DEFAULTS, **entry.data, **entry.options}


def parse_recipients(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "")
    return [
        part.strip()
        for part in text.replace(";", ",").replace("\n", ",").split(",")
        if part.strip()
    ]


def parse_run_time(value: str) -> tuple[int, int, int]:
    parts = str(value or "08:30:00").strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    second = int(float(parts[2])) if len(parts) > 2 else 0
    return hour, minute, second


def tzinfo(settings: dict) -> ZoneInfo:
    try:
        return ZoneInfo(str(settings.get(CONF_TIMEZONE) or "America/Los_Angeles"))
    except Exception:
        return ZoneInfo("America/Los_Angeles")


def apply_env(
    settings: dict,
    mapping_path: Path | None = None,
    hass: HomeAssistant | None = None,
) -> None:
    recipients = parse_recipients(settings.get(CONF_RECIPIENTS))
    os.environ["SMTP_HOST"] = str(settings.get(CONF_SMTP_HOST) or "smtp.gmail.com")
    os.environ["SMTP_PORT"] = str(int(settings.get(CONF_SMTP_PORT) or 587))
    os.environ["SMTP_USER"] = str(settings.get(CONF_SMTP_USER) or "")
    os.environ["SMTP_PASSWORD"] = str(settings.get(CONF_SMTP_PASSWORD) or "")
    os.environ["MAIL_FROM"] = str(
        settings.get(CONF_MAIL_FROM) or settings.get(CONF_SMTP_USER) or ""
    )
    os.environ["MAIL_TO"] = ",".join(recipients)
    os.environ["PROBATE_TZ"] = str(settings.get(CONF_TIMEZONE) or "America/Los_Angeles")
    os.environ["PROBATE_COUNTY"] = str(settings.get(CONF_COUNTY) or "Placer")
    os.environ["PROBATE_KEYWORDS"] = str(settings.get(CONF_KEYWORDS) or DEFAULTS[CONF_KEYWORDS])
    os.environ["PROBATE_MAX_PAGES"] = str(int(settings.get(CONF_MAX_PAGES) or 10))
    try:
        from .fub_client import apply_fub_go_required_env, source_window_settings
    except ImportError:
        from fub_client import apply_fub_go_required_env, source_window_settings

    placer_window = source_window_settings(settings, "placer")
    sac_window = source_window_settings(settings, "sacramento")
    os.environ["ECOURT_PAUSE"] = str(float(placer_window["ecourt_pause_seconds"]))
    os.environ["SACRAMENTO_PORTAL_PAUSE"] = str(float(sac_window["ecourt_pause_seconds"]))
    os.environ["SACRAMENTO_PORTAL_USER"] = str(
        settings.get(CONF_SACRAMENTO_PORTAL_USER) or ""
    ).strip()
    os.environ["SACRAMENTO_PORTAL_PASSWORD"] = str(
        settings.get(CONF_SACRAMENTO_PORTAL_PASSWORD) or ""
    )
    os.environ["FUB_ENABLED"] = (
        "1"
        if settings.get(CONF_FUB_ENABLED)
        and not settings.get("test_stored")
        else "0"
    )
    os.environ["FUB_API_URL"] = str(
        settings.get(CONF_FUB_API_URL) or "https://api.followupboss.com/v1"
    )
    os.environ["FUB_API_KEY"] = str(settings.get(CONF_FUB_API_KEY) or "")
    os.environ["FUB_SYSTEM_KEY"] = str(settings.get(CONF_FUB_SYSTEM_KEY) or "")
    os.environ["FUB_SOURCE"] = str(settings.get(CONF_FUB_SOURCE) or "probate")
    os.environ["FUB_ASSIGNED_TO"] = str(
        settings.get(CONF_FUB_ASSIGNED_TO) or "Blake Hammond"
    )
    os.environ["FUB_STAGE"] = str(settings.get(CONF_FUB_STAGE) or "").strip()
    os.environ["FUB_EVENT_TYPE"] = str(
        settings.get(CONF_FUB_EVENT_TYPE) or "Seller Inquiry"
    )
    apply_fub_go_required_env(settings)
    os.environ["FUB_VERIFY_ONLY"] = (
        "1" if settings.get(CONF_FUB_VERIFY_ONLY) else "0"
    )
    os.environ["FUB_UPDATE_EXISTING"] = (
        "1" if settings.get(CONF_FUB_UPDATE_EXISTING) else "0"
    )
    os.environ["FUB_VERIFY_EXISTING"] = (
        "1" if settings.get(CONF_FUB_VERIFY_EXISTING) else "0"
    )
    os.environ["FUB_VERIFY_PERSON_ID"] = str(
        settings.get(CONF_FUB_VERIFY_PERSON_ID) or ""
    ).strip()
    if mapping_path:
        os.environ["FUB_MAPPING_PATH"] = str(mapping_path)
    if hass is not None:
        data_dir = Path(hass.config.path(DOMAIN))
        os.environ["PPM_PROGRESS_PATH"] = str(data_dir / "job_progress.json")
        os.environ["PPM_OCR_DIR"] = str(data_dir / "ocr")
        os.environ["FUB_PETITION_DOCS_DIR"] = str(data_dir / "reports" / "docs")
        os.environ["FUB_SACRAMENTO_PETITION_DOCS_DIR"] = str(
            data_dir / "reports" / "sacramento" / "docs"
        )
        entry = hass.config_entries.async_entries(DOMAIN)
        if entry:
            os.environ["FUB_PETITION_TOKEN_SECRET"] = entry[0].entry_id
        try:
            from homeassistant.helpers.network import get_url

            base = str(get_url(hass, prefer_external=True) or "").rstrip("/")
        except Exception:  # noqa: BLE001
            base = ""
        if base:
            os.environ["FUB_PETITION_BASE_URL"] = (
                f"{base}/api/placer_probate_monitor/de111"
            )
            os.environ["FUB_DUTIES_BASE_URL"] = (
                f"{base}/api/placer_probate_monitor/de147"
            )
            os.environ["FUB_LETTERS_BASE_URL"] = (
                f"{base}/api/placer_probate_monitor/de150"
            )
        else:
            os.environ.pop("FUB_PETITION_BASE_URL", None)
            os.environ.pop("FUB_DUTIES_BASE_URL", None)
            os.environ.pop("FUB_LETTERS_BASE_URL", None)


def should_run_now(settings: dict, now: datetime) -> bool:
    freq = str(settings.get(CONF_FREQUENCY) or "daily")
    name = WEEKDAYS[now.weekday()]
    if freq == "hourly":
        return True
    if freq == "weekdays" and name in {"saturday", "sunday"}:
        return False
    if freq == "weekly" and name != str(settings.get(CONF_WEEKLY_DAY) or "monday").lower():
        return False
    if freq == "monthly" and now.day != int(settings.get(CONF_MONTHLY_DAY) or 1):
        return False
    return True


def _read_ecourt_view_limit(data_dir: Path, log: str) -> dict:
    payload = {
        "error": "ecourt_view_limit",
        "source": "placer",
        "source_name": "Placer County",
        "cases": [],
    }
    path = data_dir / "ecourt_alerts.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                payload["source"] = str(data.get("source") or "placer")
                payload["source_name"] = str(data.get("source_name") or "Placer County")
                cases = [
                    str(item) for item in (data.get("cases") or []) if str(item).strip()
                ]
                if cases:
                    payload["cases"] = cases
                    payload["error"] = str(data.get("error") or "ecourt_view_limit")
                    return payload
        except json.JSONDecodeError:
            pass
    cases: list[str] = []
    for line in log.splitlines():
        if not line.startswith("ECOURT_VIEW_LIMIT"):
            continue
        if "cases=" in line:
            raw = line.split("cases=", 1)[1].strip()
            cases.extend(part.strip() for part in raw.split(",") if part.strip())
        elif "case=" in line:
            cases.append(line.split("case=", 1)[1].strip().split()[0])
    payload["cases"] = list(dict.fromkeys(cases))
    if not payload["cases"]:
        payload["error"] = None
    return payload


async def notify_ecourt_view_limit(hass: HomeAssistant, alert: dict) -> None:
    cases = [str(item) for item in (alert or {}).get("cases") or [] if str(item).strip()]
    if not cases:
        return
    source = str((alert or {}).get("source") or "placer")
    source_name = str((alert or {}).get("source_name") or "Placer County")
    error = str((alert or {}).get("error") or "ecourt_view_limit")
    shown = ", ".join(cases[:12])
    extra = f" (+{len(cases) - 12} more)" if len(cases) > 12 else ""
    message = (
        f"Data source: {source_name} ({source})\n"
        f"Error: {error}\n"
        "Placer eCourt Public reached its case view limit, so some dockets "
        "and PDFs were not loaded.\n"
        f"Cases affected: {shown}{extra}\n"
        "Wait and run again, or raise the eCourt pause in the integration options."
    )
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": "Placer Probate Monitor: eCourt view limit",
            "message": message,
            "notification_id": EVENT_ECOURT_VIEW_LIMIT,
        },
        blocking=False,
    )
    hass.bus.async_fire(
        EVENT_ECOURT_VIEW_LIMIT,
        {
            "source": source,
            "source_name": source_name,
            "error": error,
            "cases": cases,
        },
    )
    _LOGGER.warning(
        "eCourt view limit on %s (%s): %s",
        source_name,
        source,
        ", ".join(cases),
    )


def _source_job_cmd(data_dir: Path, settings: dict, source_id: str) -> list[str]:
    reports = data_dir / "reports"
    if source_id == "sacramento":
        script = COMPONENT_DIR / "sacramento_probate_monitor.py"
        state = data_dir / "seen_cases_sacramento.json"
        out_dir = reports / "sacramento"
    else:
        script = COMPONENT_DIR / "placer_probate_monitor.py"
        state = data_dir / "seen_cases.json"
        out_dir = reports
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from .fub_client import sacramento_cli_window_args, source_window_settings
    except ImportError:
        from fub_client import sacramento_cli_window_args, source_window_settings

    window = source_window_settings(settings, source_id)
    if source_id == "sacramento":
        window_args = sacramento_cli_window_args(settings)
    else:
        window_args = [
            "--lookback-days",
            str(int(window["lookback_days"])),
            "--lookahead-days",
            str(int(window["lookahead_days"])),
        ]
    cmd = [
        sys.executable,
        str(script),
        *window_args,
        "--state-file",
        str(state),
        "--out-dir",
        str(out_dir),
    ]
    if not settings.get(CONF_SEND_EMAIL):
        cmd.append("--no-email")
    if settings.get(CONF_SKIP_PORTAL) and not (
        settings.get("rescan_local")
        or settings.get("test_stored")
        or settings.get("rescan_go")
    ):
        cmd.append("--skip-portal")
    if not settings.get(CONF_GENERATE_PDF):
        cmd.append("--no-pdf")
    if settings.get("test_stored"):
        cmd.append("--test-stored")
        if "--no-email" not in cmd:
            cmd.append("--no-email")
        if "--no-pdf" not in cmd:
            cmd.append("--no-pdf")
    elif settings.get("rescan_go"):
        cmd.append("--rescan-go")
        if "--no-email" not in cmd:
            cmd.append("--no-email")
        if "--no-pdf" not in cmd:
            cmd.append("--no-pdf")
    elif settings.get("rescan_local"):
        cmd.append("--rescan-local")
        if "--no-email" not in cmd:
            cmd.append("--no-email")
        if "--no-pdf" not in cmd:
            cmd.append("--no-pdf")
        if settings.get("fub_preview_one"):
            cmd.append("--fub-preview-one")
        elif settings.get(CONF_FUB_VERIFY_ONLY) and not settings.get(
            CONF_FUB_UPDATE_EXISTING
        ):
            cmd.append("--fub-verify-one")
    elif settings.get("fub_preview_one"):
        cmd.append("--fub-preview-one")
        if "--no-email" not in cmd:
            cmd.append("--no-email")
        if "--no-pdf" not in cmd:
            cmd.append("--no-pdf")
    elif settings.get(CONF_FUB_VERIFY_ONLY) and not settings.get(
        CONF_FUB_UPDATE_EXISTING
    ):
        cmd.append("--fub-verify-one")
    return cmd


def _parse_job_log(log: str, data_dir: Path, reports: Path, returncode: int) -> dict:
    new_count = None
    notice_count = None
    for line in reversed(log.splitlines()):
        if " new / " in line and (
            "Placer probate notices" in line
            or "Sacramento probate notices" in line
            or "local rescan" in line
            or "stored test" in line
        ):
            try:
                tail = line.split("—")[-1]
                new_count = int(tail.split("new")[0].strip())
                if "/" in tail:
                    notice_count = int(tail.split("/")[-1].split("unique")[0].strip())
            except ValueError:
                pass
            break
    ok = returncode == 0
    fub_posted = None
    fub_updated = None
    fub_skipped = None
    fub_error = None
    fub_verify = None
    stored_test = False
    go_count = None
    nogo_count = None
    stored_cases = []
    sidecar = data_dir / "fub_last.json"
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            fub_posted = payload.get("posted")
            fub_updated = payload.get("updated")
            fub_skipped = payload.get("skipped")
            fub_error = payload.get("error")
            fub_verify = payload.get("verify_record")
            if not fub_verify and payload.get("verify_note"):
                fub_verify = {"note": payload.get("verify_note")}
            stored_test = bool(payload.get("stored_test"))
            if payload.get("go_count") is not None:
                go_count = payload.get("go_count")
            if payload.get("nogo_count") is not None:
                nogo_count = payload.get("nogo_count")
            if isinstance(payload.get("cases"), list):
                stored_cases = payload.get("cases")
        except json.JSONDecodeError:
            pass
    view_limit = _read_ecourt_view_limit(data_dir, log)
    if fub_posted is None:
        for line in reversed(log.splitlines()):
            if line.startswith("FUB: posted="):
                try:
                    parts = dict(
                        item.split("=", 1) for item in line.replace("FUB: ", "").split()
                    )
                    fub_posted = int(parts.get("posted", 0))
                    fub_updated = int(parts.get("updated", 0))
                    fub_skipped = int(parts.get("skipped", 0))
                except ValueError:
                    pass
                break
    if fub_error is None:
        for line in reversed(log.splitlines()):
            if line.startswith("FUB enabled but") or line.startswith("FUB error"):
                fub_error = line[-500:]
                break
    pdfs = sorted(reports.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    pdfs += sorted(
        (reports / "sacramento").glob("*.pdf"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    pdfs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return {
        "ok": ok,
        ATTR_LAST_RESULT: "ok" if ok else "failed",
        ATTR_LAST_ERROR: None if ok else (log[-2000:] or f"exit {returncode}"),
        ATTR_PDF: pdfs[0].name if pdfs else None,
        ATTR_NEW_COUNT: new_count,
        ATTR_NOTICE_COUNT: notice_count,
        ATTR_FUB_POSTED: fub_posted,
        ATTR_FUB_UPDATED: fub_updated,
        ATTR_FUB_SKIPPED: fub_skipped,
        ATTR_FUB_ERROR: fub_error,
        ATTR_FUB_VERIFY: fub_verify,
        ATTR_ECOURT_VIEW_LIMIT: view_limit,
        "stored_test": stored_test,
        "go_count": go_count,
        "nogo_count": nogo_count,
        "stored_cases": stored_cases,
        "log_tail": log[-1500:],
    }


def _run_one_source(hass: HomeAssistant, settings: dict, source_id: str) -> dict:
    data_dir = Path(hass.config.path(DOMAIN))
    reports = data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    cmd = _source_job_cmd(data_dir, settings, source_id)
    proc = subprocess.run(
        cmd,
        cwd=str(COMPONENT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    try:
        from .ha_logs import merge_last_run_log, persist_job_logs
    except ImportError:
        from ha_logs import merge_last_run_log, persist_job_logs

    merge_last_run_log(data_dir, source_id, log)
    parsed = _parse_job_log(log, data_dir, reports, proc.returncode)
    persist_job_logs(
        data_dir,
        source_id=source_id,
        log_text=log,
        ok=bool(parsed.get("ok")),
        error=parsed.get(ATTR_LAST_ERROR),
    )
    return parsed


def _run_stored_fub_preview(hass: HomeAssistant, settings: dict) -> dict:
    """Fill Last stored extract from listings.json. No CNPA, court, or PDF rescan."""
    data_dir = Path(hass.config.path(DOMAIN))
    try:
        from .fub_client import preview_one_record, stored_rows_for_fub_one
        from .ha_logs import merge_last_run_log, persist_job_logs
        from .job_progress import report_progress
    except ImportError:
        from fub_client import preview_one_record, stored_rows_for_fub_one
        from ha_logs import merge_last_run_log, persist_job_logs
        from job_progress import report_progress

    source_id = str(settings.get("source_id") or "").strip().lower() or None
    use_existing = bool(settings.get(CONF_FUB_VERIFY_EXISTING))
    person_id = str(settings.get(CONF_FUB_VERIFY_PERSON_ID) or "").strip()
    wanted = person_id if use_existing else None
    report_progress(
        "preview",
        (
            f"Previewing stored listing for Follow Up Boss person {wanted}…"
            if wanted
            else "Previewing one stored listing (Follow Up Boss not updated)…"
        ),
    )
    rows = stored_rows_for_fub_one(
        data_dir, source_id=source_id, person_id=wanted
    )
    preview = preview_one_record(
        rows,
        mapping_path=data_dir / "fub_mapping.yaml",
        person_id=wanted,
    )
    record = preview.get("verify_record")
    note = preview.get("verify_note")
    skips = preview.get("skips") or []
    payload = {
        "posted": 0,
        "updated": 0,
        "skipped": len(skips),
        "error": None,
        "preview": True,
        "verify_record": record,
        "verify_note": note,
        "skips": skips,
    }
    if source_id:
        payload["source_id"] = source_id
    (data_dir / "fub_last.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    case = ""
    if isinstance(record, dict):
        case = str(record.get("case_number") or "")
    log = (
        f"Stored FUB preview — {len(rows)} listings — "
        f"{('go ' + case) if case and not note else (note or 'no go-case')}\n"
        "Preview only: Follow Up Boss not updated, seen-cases not updated.\n"
    )
    merge_last_run_log(data_dir, source_id or "preview", log)
    persist_job_logs(data_dir, source_id=source_id or "preview", log_text=log, ok=True, error=None)
    report_progress(
        "done",
        "Preview finished (Follow Up Boss not updated).",
        fub_posted=0,
        fub_updated=0,
        fub_skipped=len(skips),
    )
    return {
        "ok": True,
        ATTR_LAST_RESULT: "ok",
        ATTR_LAST_ERROR: None,
        ATTR_PDF: None,
        ATTR_NEW_COUNT: 0,
        ATTR_NOTICE_COUNT: len(rows),
        ATTR_FUB_POSTED: 0,
        ATTR_FUB_UPDATED: 0,
        ATTR_FUB_SKIPPED: len(skips),
        ATTR_FUB_ERROR: None,
        ATTR_FUB_VERIFY: record or ({"note": note} if note else None),
        ATTR_ECOURT_VIEW_LIMIT: {},
        "log_tail": log[-1500:],
    }


def _run_stored_fub_verify(hass: HomeAssistant, settings: dict) -> dict:
    """PUT/POST one stored listing. No CNPA, court, or PDF rescan."""
    data_dir = Path(hass.config.path(DOMAIN))
    try:
        from .fub_client import export_new_leads, stored_rows_for_fub_one
        from .ha_logs import merge_last_run_log, persist_job_logs
        from .job_progress import report_progress
    except ImportError:
        from fub_client import export_new_leads, stored_rows_for_fub_one
        from ha_logs import merge_last_run_log, persist_job_logs
        from job_progress import report_progress

    use_existing = bool(settings.get(CONF_FUB_VERIFY_EXISTING))
    person_id = str(settings.get(CONF_FUB_VERIFY_PERSON_ID) or "").strip()
    wanted = person_id if use_existing else None
    report_progress(
        "verify",
        (
            f"Updating stored listing for Follow Up Boss person {wanted}…"
            if wanted
            else "Verifying one stored listing…"
        ),
    )
    rows = stored_rows_for_fub_one(data_dir, person_id=wanted)
    if wanted and not rows:
        note = f"No stored listing has Follow Up Boss person {wanted}."
        report_progress("done", note, fub_posted=0, fub_updated=0, fub_skipped=0)
        payload = {
            "posted": 0,
            "updated": 0,
            "skipped": 0,
            "error": note,
            "verify_note": note,
            "skips": [],
        }
        (data_dir / "fub_last.json").write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        return {
            "ok": False,
            ATTR_LAST_RESULT: "failed",
            ATTR_LAST_ERROR: note,
            ATTR_PDF: None,
            ATTR_NEW_COUNT: 0,
            ATTR_NOTICE_COUNT: 0,
            ATTR_FUB_POSTED: 0,
            ATTR_FUB_UPDATED: 0,
            ATTR_FUB_SKIPPED: 0,
            ATTR_FUB_ERROR: note,
            ATTR_FUB_VERIFY: {"note": note},
            ATTR_ECOURT_VIEW_LIMIT: {},
            "log_tail": note,
        }
    source_id = str((rows[0] if rows else {}).get("source_id") or "placer").lower()
    state_path = data_dir / (
        "seen_cases_sacramento.json" if source_id == "sacramento" else "seen_cases.json"
    )
    state: dict = {"cases": {}}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("cases", {})
                state = loaded
        except json.JSONDecodeError:
            pass
    summary = export_new_leads(
        rows, state, mapping_path=data_dir / "fub_mapping.yaml"
    )
    state_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    (data_dir / "fub_last.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    record = summary.get("verify_record")
    note = summary.get("verify_note") or summary.get("error")
    case = ""
    if isinstance(record, dict):
        case = str(record.get("case_number") or "")
    log = (
        f"Stored FUB verify — {len(rows)} listing(s) — "
        f"{case or note or 'done'}\n"
    )
    merge_last_run_log(data_dir, source_id or "verify", log)
    persist_job_logs(
        data_dir,
        source_id=source_id or "verify",
        log_text=log,
        ok=not summary.get("error"),
        error=summary.get("error"),
    )
    report_progress(
        "done",
        note or "Verify finished.",
        fub_posted=int(summary.get("posted") or 0),
        fub_updated=int(summary.get("updated") or 0),
        fub_skipped=int(summary.get("skipped") or 0),
    )
    return {
        "ok": not summary.get("error"),
        ATTR_LAST_RESULT: "failed" if summary.get("error") else "ok",
        ATTR_LAST_ERROR: summary.get("error"),
        ATTR_PDF: None,
        ATTR_NEW_COUNT: 0,
        ATTR_NOTICE_COUNT: len(rows),
        ATTR_FUB_POSTED: int(summary.get("posted") or 0),
        ATTR_FUB_UPDATED: int(summary.get("updated") or 0),
        ATTR_FUB_SKIPPED: int(summary.get("skipped") or 0),
        ATTR_FUB_ERROR: summary.get("error"),
        ATTR_FUB_VERIFY: record or ({"note": note} if note else None),
        ATTR_ECOURT_VIEW_LIMIT: {},
        "log_tail": log[-1500:],
    }


def _run_stored_fub_push(hass: HomeAssistant, settings: dict) -> dict:
    """POST new / PUT existing stored GOs. No CNPA, court, or PDF rescan."""
    data_dir = Path(hass.config.path(DOMAIN))
    try:
        from .fub_client import (
            apply_listing_go,
            export_new_leads,
            load_mapping,
            stored_rows_for_fub_one,
        )
        from .ha_logs import merge_last_run_log, persist_job_logs
        from .job_progress import report_progress
    except ImportError:
        from fub_client import (
            apply_listing_go,
            export_new_leads,
            load_mapping,
            stored_rows_for_fub_one,
        )
        from ha_logs import merge_last_run_log, persist_job_logs
        from job_progress import report_progress

    source_id = str(settings.get("source_id") or "placer").strip().lower()
    if source_id not in {"placer", "sacramento"}:
        source_id = "placer"
    county = "Sacramento" if source_id == "sacramento" else "Placer"
    report_progress(
        "fub",
        f"Pushing stored {county} GOs to Follow Up Boss…",
        source_id=source_id,
    )
    rows = stored_rows_for_fub_one(data_dir, source_id=source_id)
    state_path = data_dir / (
        "seen_cases_sacramento.json" if source_id == "sacramento" else "seen_cases.json"
    )
    state: dict = {"cases": {}}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("cases", {})
                state = loaded
        except json.JSONDecodeError:
            pass
    mapping = load_mapping(data_dir / "fub_mapping.yaml")
    for row in rows:
        key = str(row.get("case_number") or "").strip()
        if row.get("fub_removed") and key:
            rec = state.setdefault("cases", {}).setdefault(key, {})
            rec["fub_removed"] = True
        apply_listing_go(row, state=state, mapping=mapping)
    summary = export_new_leads(
        rows, state, mapping_path=data_dir / "fub_mapping.yaml"
    )
    state_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    sidecar = {
        "posted": summary.get("posted"),
        "updated": summary.get("updated"),
        "skipped": summary.get("skipped"),
        "error": summary.get("error"),
        "skips": summary.get("skips") or [],
        "push_stored_fub": True,
        "source_id": source_id,
    }
    (data_dir / "fub_last.json").write_text(
        json.dumps(sidecar, indent=2, default=str),
        encoding="utf-8",
    )
    posted = int(summary.get("posted") or 0)
    updated = int(summary.get("updated") or 0)
    skipped = int(summary.get("skipped") or 0)
    note = summary.get("error") or (
        f"{county} stored push finished. Follow Up Boss posted {posted}, "
        f"updated {updated}, skipped {skipped}."
    )
    log = f"Stored FUB push — {county} — {len(rows)} listing(s) — {note}\n"
    merge_last_run_log(data_dir, source_id, log)
    persist_job_logs(
        data_dir,
        source_id=source_id,
        log_text=log,
        ok=not summary.get("error"),
        error=summary.get("error"),
    )
    report_progress(
        "done",
        note,
        fub_posted=posted,
        fub_updated=updated,
        fub_skipped=skipped,
        notice_count=len(rows),
        new_count=0,
        source_id=source_id,
    )
    return {
        "ok": not summary.get("error"),
        ATTR_LAST_RESULT: "failed" if summary.get("error") else "ok",
        ATTR_LAST_ERROR: summary.get("error"),
        ATTR_PDF: None,
        ATTR_NEW_COUNT: 0,
        ATTR_NOTICE_COUNT: len(rows),
        ATTR_FUB_POSTED: posted,
        ATTR_FUB_UPDATED: updated,
        ATTR_FUB_SKIPPED: skipped,
        ATTR_FUB_ERROR: summary.get("error"),
        ATTR_FUB_VERIFY: None,
        ATTR_ECOURT_VIEW_LIMIT: {},
        "source_id": source_id,
        "log_tail": log[-1500:],
    }


def run_monitor_job(hass: HomeAssistant, settings: dict) -> dict:
    data_dir = Path(hass.config.path(DOMAIN))
    apply_env(settings, mapping_path=data_dir / "fub_mapping.yaml", hass=hass)
    try:
        from .fub_client import enabled_live_sources
        from .job_progress import clear_progress, report_progress
    except ImportError:
        from fub_client import enabled_live_sources
        from job_progress import clear_progress, report_progress

    requested = str(settings.get("source_id") or "").strip().lower()
    if requested:
        # Panel Preview/Run always names a county. The daily-job toggle must
        # not block that; it only filters scheduled/startup/service runs.
        sources = [requested]
    else:
        sources = enabled_live_sources(settings)
    if requested in {"placer", "sacramento"}:
        os.environ["FUB_DATA_SOURCE"] = requested

    clear_progress(requested if requested in {"placer", "sacramento"} else None)
    if settings.get("fub_preview_one"):
        return _run_stored_fub_preview(hass, settings)
    if settings.get("push_stored_fub"):
        return _run_stored_fub_push(hass, settings)
    if (
        settings.get(CONF_FUB_VERIFY_ONLY)
        and not settings.get("rescan_local")
        and not settings.get("test_stored")
        and not settings.get("rescan_go")
        and not settings.get(CONF_FUB_UPDATE_EXISTING)
    ):
        return _run_stored_fub_verify(hass, settings)
    if settings.get("local_audit"):
        try:
            from .ha_logs import merge_last_run_log, persist_job_logs
            from .local_audit import run_local_audit_job
        except ImportError:
            from ha_logs import merge_last_run_log, persist_job_logs
            from local_audit import run_local_audit_job

        report_progress("audit", "Starting local stored-case audit…")
        result = run_local_audit_job(data_dir, settings)
        log_text = str(result.get("log_tail") or "")
        merge_last_run_log(data_dir, "audit", log_text)
        persist_job_logs(
            data_dir,
            source_id="audit",
            log_text=log_text,
            ok=bool(result.get("ok")),
            error=result.get(ATTR_LAST_ERROR),
        )
        return result
    if not sources:
        report_progress("done", "No county sources are enabled.")
        return {
            "ok": True,
            ATTR_LAST_RESULT: "ok",
            ATTR_LAST_ERROR: None,
            ATTR_PDF: None,
            ATTR_NEW_COUNT: 0,
            ATTR_NOTICE_COUNT: 0,
            ATTR_FUB_POSTED: 0,
            ATTR_FUB_UPDATED: 0,
            ATTR_FUB_SKIPPED: 0,
            ATTR_FUB_ERROR: None,
            ATTR_FUB_VERIFY: {
                "note": "No county sources are enabled. Turn Placer or Sacramento on from Probate sources."
            },
            ATTR_ECOURT_VIEW_LIMIT: {},
            "log_tail": "No county sources are enabled.",
        }

    try:
        from .pdf_ocr import ensure_ocr_packages, ocr_status
    except ImportError:
        from pdf_ocr import ensure_ocr_packages, ocr_status

    report_progress(
        "ocr_install",
        "Making sure petition OCR is installed on this Home Assistant box…",
    )
    ocr = ensure_ocr_packages()
    if not ocr.get("ready"):
        ocr = ocr_status()
        print(
            f"Petition OCR not ready engine={ocr.get('engine')} "
            f"renderer={ocr.get('renderer')}",
            flush=True,
        )
    else:
        print(f"Petition OCR ready ({ocr.get('engine')})", flush=True)

    (data_dir / "last_run.log").write_text("", encoding="utf-8")
    combined = {
        "ok": True,
        ATTR_LAST_RESULT: "ok",
        ATTR_LAST_ERROR: None,
        ATTR_PDF: None,
        ATTR_NEW_COUNT: 0,
        ATTR_NOTICE_COUNT: 0,
        ATTR_FUB_POSTED: 0,
        ATTR_FUB_UPDATED: 0,
        ATTR_FUB_SKIPPED: 0,
        ATTR_FUB_ERROR: None,
            ATTR_FUB_VERIFY: None,
            ATTR_ECOURT_VIEW_LIMIT: {},
            "stored_test": False,
            "go_count": 0,
            "nogo_count": 0,
            "stored_cases": [],
            "log_tail": "",
        }
    for source_id in sources:
        label = "Placer" if source_id == "placer" else "Sacramento"
        report_progress("start", f"Starting {label} job…")
        result = _run_one_source(hass, settings, source_id)
        if not result.get("ok"):
            combined["ok"] = False
            combined[ATTR_LAST_RESULT] = "failed"
            combined[ATTR_LAST_ERROR] = result.get(ATTR_LAST_ERROR)
        for key in (ATTR_NEW_COUNT, ATTR_NOTICE_COUNT, ATTR_FUB_POSTED, ATTR_FUB_UPDATED, ATTR_FUB_SKIPPED):
            combined[key] = int(combined.get(key) or 0) + int(result.get(key) or 0)
        if result.get(ATTR_PDF):
            combined[ATTR_PDF] = result.get(ATTR_PDF)
        if result.get(ATTR_FUB_ERROR):
            combined[ATTR_FUB_ERROR] = result.get(ATTR_FUB_ERROR)
        if result.get(ATTR_FUB_VERIFY):
            combined[ATTR_FUB_VERIFY] = result.get(ATTR_FUB_VERIFY)
        if result.get("stored_test"):
            combined["stored_test"] = True
        if result.get("go_count") is not None:
            combined["go_count"] = int(combined.get("go_count") or 0) + int(
                result.get("go_count") or 0
            )
        if result.get("nogo_count") is not None:
            combined["nogo_count"] = int(combined.get("nogo_count") or 0) + int(
                result.get("nogo_count") or 0
            )
        if result.get("stored_cases"):
            combined["stored_cases"] = list(combined.get("stored_cases") or []) + list(
                result.get("stored_cases") or []
            )
        limit = result.get(ATTR_ECOURT_VIEW_LIMIT) or {}
        if limit.get("cases"):
            combined[ATTR_ECOURT_VIEW_LIMIT] = limit
        combined["log_tail"] = result.get("log_tail") or combined["log_tail"]
        combined["source_id"] = source_id
    if len(sources) == 1:
        combined["source_id"] = sources[0]
    return combined


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    from .hass_views import async_setup_mapping_views

    async_setup_mapping_views(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    store = {
        "entry": entry,
        "unsubs": [],
        "running": False,
        "status": {
            ATTR_LAST_RUN: None,
            ATTR_LAST_RESULT: None,
            ATTR_LAST_ERROR: None,
            ATTR_NEW_COUNT: None,
            ATTR_NOTICE_COUNT: None,
            ATTR_PDF: None,
            ATTR_FUB_POSTED: None,
            ATTR_FUB_UPDATED: None,
            ATTR_FUB_SKIPPED: None,
            ATTR_FUB_ERROR: None,
            ATTR_FUB_VERIFY: None,
            ATTR_ECOURT_VIEW_LIMIT: None,
        },
    }
    hass.data[DOMAIN][entry.entry_id] = store
    try:
        from .ha_logs import attach_component_logger
    except ImportError:
        from ha_logs import attach_component_logger

    attach_component_logger(Path(hass.config.path(DOMAIN)))

    async def _execute(reason: str, overrides: dict | None = None) -> dict:
        if store["running"]:
            return {"ok": False, "error": "A run is already in progress."}
        store["running"] = True
        settings = {**merged_options(entry), **(overrides or {})}
        source_id = str(settings.get("source_id") or "").strip().lower()
        if source_id in {"placer", "sacramento"}:
            store["status"]["source_id"] = source_id
        async_dispatcher_send(hass, f"{DOMAIN}_status")
        try:
            result = await hass.async_add_executor_job(run_monitor_job, hass, settings)
        except Exception:
            _LOGGER.exception("Placer probate monitor failed")
            result = {
                "ok": False,
                ATTR_LAST_RESULT: "failed",
                ATTR_LAST_ERROR: "Monitor raised an exception; see Home Assistant logs.",
            }
        zone = tzinfo(settings)
        store["status"].update(
            {
                ATTR_LAST_RUN: datetime.now(zone).isoformat(timespec="seconds"),
                ATTR_LAST_RESULT: result.get(ATTR_LAST_RESULT),
                ATTR_LAST_ERROR: result.get(ATTR_LAST_ERROR),
                ATTR_NEW_COUNT: result.get(ATTR_NEW_COUNT),
                ATTR_NOTICE_COUNT: result.get(ATTR_NOTICE_COUNT),
                ATTR_PDF: result.get(ATTR_PDF),
                ATTR_FUB_POSTED: result.get(ATTR_FUB_POSTED),
                ATTR_FUB_UPDATED: result.get(ATTR_FUB_UPDATED),
                ATTR_FUB_SKIPPED: result.get(ATTR_FUB_SKIPPED),
                ATTR_FUB_ERROR: result.get(ATTR_FUB_ERROR),
                ATTR_FUB_VERIFY: result.get(ATTR_FUB_VERIFY),
                ATTR_ECOURT_VIEW_LIMIT: result.get(ATTR_ECOURT_VIEW_LIMIT),
                "stored_test": result.get("stored_test"),
                "local_audit": result.get("local_audit"),
                "audit_issues": result.get("audit_issues"),
                "go_count": result.get("go_count"),
                "nogo_count": result.get("nogo_count"),
                "stored_cases": result.get("stored_cases"),
                "source_id": result.get("source_id") or source_id or store["status"].get("source_id"),
            }
        )
        store["running"] = False
        async_dispatcher_send(hass, f"{DOMAIN}_status")
        await notify_ecourt_view_limit(hass, result.get(ATTR_ECOURT_VIEW_LIMIT) or {})
        _LOGGER.info("Placer probate monitor %s run: %s", reason, result.get(ATTR_LAST_RESULT))
        return result

    async def _scheduled(_now=None) -> None:
        settings = merged_options(entry)
        current = datetime.now(tzinfo(settings))
        if should_run_now(settings, current):
            await _execute("scheduled")

    async def _scheduled_audit(_now=None) -> None:
        settings = merged_options(entry)
        if settings.get(CONF_AUDIT_WEEKLY, True) is False:
            return
        current = datetime.now(tzinfo(settings))
        day = str(settings.get(CONF_WEEKLY_DAY) or "sunday").lower()
        if WEEKDAYS[current.weekday()] != day:
            return
        await _execute(
            "scheduled_audit",
            {
                "local_audit": True,
                CONF_FUB_ENABLED: False,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )

    def _listen() -> None:
        for unsub in store["unsubs"]:
            unsub()
        store["unsubs"] = []
        settings = merged_options(entry)
        hour, minute, second = parse_run_time(str(settings.get(CONF_RUN_TIME) or "08:30:00"))
        freq = str(settings.get(CONF_FREQUENCY) or "daily")
        if freq == "hourly":
            store["unsubs"].append(
                async_track_time_change(hass, _scheduled, minute=minute, second=second)
            )
        else:
            store["unsubs"].append(
                async_track_time_change(
                    hass, _scheduled, hour=hour, minute=minute, second=second
                )
            )
        store["unsubs"].append(
            async_track_time_change(
                hass, _scheduled_audit, hour=AUDIT_WEEKLY_HOUR, minute=0, second=0
            )
        )

    _listen()
    entry.async_on_unload(entry.add_update_listener(_update_listener))

    async def _start(_event=None) -> None:
        if merged_options(entry).get(CONF_RUN_ON_START):
            await _execute("startup")

    if hass.is_running:
        hass.async_create_task(_start())
    else:
        store["unsubs"].append(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start))

    store["run"] = _execute
    store["relisten"] = _listen

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from .hass_views import async_setup_mapping_ui

    async_setup_mapping_ui(hass)
    hass.data[DOMAIN]["ocr"] = {
        "ready": False,
        "engine": "installing",
        "renderer": "none",
        "enabled": True,
    }

    async def _install_ocr(_event=None) -> None:
        def _run() -> dict:
            from .pdf_ocr import ensure_ocr_packages

            return ensure_ocr_packages()

        try:
            status = await hass.async_add_executor_job(_run)
        except Exception as err:  # noqa: BLE001
            status = {
                "ready": False,
                "engine": "none",
                "renderer": "none",
                "enabled": True,
                "error": str(err)[:300],
            }
            _LOGGER.warning("Petition OCR install failed: %s", err)
        hass.data[DOMAIN]["ocr"] = status
        _LOGGER.info("Petition OCR: %s", status)

    hass.async_create_task(_install_ocr())

    async def _svc_run(_call: ServiceCall) -> None:
        result = await _execute("service")
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_test(_call: ServiceCall) -> None:
        settings = merged_options(entry)
        apply_env(settings)
        if not parse_recipients(settings.get(CONF_RECIPIENTS)):
            raise HomeAssistantError("Add at least one recipient.")

        def _send() -> None:
            from .placer_probate_monitor import send_email

            send_email(
                "Placer probate monitor — test",
                "This is a test from the Home Assistant integration. SMTP is working.",
                "<p>This is a test from the Home Assistant integration. SMTP is working.</p>",
            )

        await hass.async_add_executor_job(_send)

    async def _svc_verify(_call: ServiceCall) -> None:
        settings = merged_options(entry)
        if not str(settings.get(CONF_FUB_API_KEY) or "").strip():
            raise HomeAssistantError("Set the Follow Up Boss API key first.")
        result = await _execute(
            "verify_fub",
            {
                CONF_FUB_ENABLED: True,
                CONF_FUB_VERIFY_ONLY: True,
                CONF_FUB_UPDATE_EXISTING: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_preview(_call: ServiceCall) -> None:
        result = await _execute(
            "preview_one",
            {
                "fub_preview_one": True,
                CONF_FUB_ENABLED: False,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_rescan(_call: ServiceCall) -> None:
        result = await _execute(
            "rescan_local",
            {
                "rescan_local": True,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_test_stored(_call: ServiceCall) -> None:
        result = await _execute(
            "test_stored",
            {
                "test_stored": True,
                "rescan_local": True,
                CONF_FUB_ENABLED: False,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_rescan_go(_call: ServiceCall) -> None:
        result = await _execute(
            "rescan_go",
            {
                "rescan_go": True,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_push_stored_fub(_call: ServiceCall) -> None:
        settings = merged_options(entry)
        if not str(settings.get(CONF_FUB_API_KEY) or "").strip():
            raise HomeAssistantError("Set the Follow Up Boss API key first.")
        result = await _execute(
            "push_stored_fub",
            {
                "push_stored_fub": True,
                CONF_FUB_ENABLED: True,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_local_audit(_call: ServiceCall) -> None:
        result = await _execute(
            "local_audit",
            {
                "local_audit": True,
                CONF_FUB_ENABLED: False,
                CONF_FUB_VERIFY_ONLY: False,
                CONF_SEND_EMAIL: False,
                CONF_GENERATE_PDF: False,
            },
        )
        hass.bus.async_fire(f"{DOMAIN}_run_finished", result)

    async def _svc_cleanup_fub_notes(call: ServiceCall) -> None:
        settings = merged_options(entry)
        if not str(settings.get(CONF_FUB_API_KEY) or "").strip():
            raise HomeAssistantError("Set the Follow Up Boss API key first.")
        data = dict(call.data or {})
        from .hass_views import run_fub_notes_cleanup

        try:
            result = await hass.async_add_executor_job(
                run_fub_notes_cleanup, hass, data
            )
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc
        hass.bus.async_fire(f"{DOMAIN}_fub_notes_cleanup", result)
        _LOGGER.info(
            "FUB note cleanup dry_run=%s people=%s dups=%s extra=%s",
            result.get("dry_run"),
            result.get("people"),
            result.get("people_with_duplicate_notes"),
            result.get("extra_notes"),
        )

    hass.services.async_register(DOMAIN, "run_now", _svc_run)
    hass.services.async_register(DOMAIN, "test_email", _svc_test)
    hass.services.async_register(DOMAIN, "verify_fub", _svc_verify)
    hass.services.async_register(DOMAIN, "preview_one", _svc_preview)
    hass.services.async_register(DOMAIN, "rescan_local", _svc_rescan)
    hass.services.async_register(DOMAIN, "test_stored", _svc_test_stored)
    hass.services.async_register(DOMAIN, "rescan_go", _svc_rescan_go)
    hass.services.async_register(DOMAIN, "push_stored_fub", _svc_push_stored_fub)
    hass.services.async_register(DOMAIN, "local_audit", _svc_local_audit)
    hass.services.async_register(DOMAIN, "cleanup_fub_notes", _svc_cleanup_fub_notes)
    return True


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    store["relisten"]()
    async_dispatcher_send(hass, f"{DOMAIN}_status")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = hass.data[DOMAIN].pop(entry.entry_id, None)
    if store:
        for unsub in store.get("unsubs") or []:
            unsub()
    remaining = [
        key for key in (hass.data.get(DOMAIN) or {}) if key != "_fub_views"
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, "run_now")
        hass.services.async_remove(DOMAIN, "test_email")
        hass.services.async_remove(DOMAIN, "verify_fub")
        hass.services.async_remove(DOMAIN, "preview_one")
        hass.services.async_remove(DOMAIN, "rescan_local")
        hass.services.async_remove(DOMAIN, "test_stored")
        hass.services.async_remove(DOMAIN, "rescan_go")
        hass.services.async_remove(DOMAIN, "push_stored_fub")
        hass.services.async_remove(DOMAIN, "local_audit")
        hass.services.async_remove(DOMAIN, "cleanup_fub_notes")
        from .hass_views import async_unload_mapping_ui

        async_unload_mapping_ui(hass)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
