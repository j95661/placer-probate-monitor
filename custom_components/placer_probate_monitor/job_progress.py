"""Live job progress for the Home Assistant panel."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_COUNTY_LABELS = {"placer": "Placer", "sacramento": "Sacramento"}
_COUNTY_LEAD_RE = re.compile(r"^(placer|sacramento)\b", re.I)


def progress_path() -> Path | None:
    raw = str(os.environ.get("PPM_PROGRESS_PATH") or "").strip()
    return Path(raw) if raw else None


def read_progress(path: Path | None = None) -> dict:
    target = path or progress_path()
    if not target or not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def county_status_id(*values) -> str:
    for raw in values:
        key = str(raw or "").strip().lower()
        if key in _COUNTY_LABELS:
            return key
    env = str(os.environ.get("FUB_DATA_SOURCE") or "").strip().lower()
    return env if env in _COUNTY_LABELS else ""


def with_county_prefix(message: str, source_id: str | None = None) -> str:
    """Put Placer/Sacramento in front of status text. Skip if already there."""
    text = str(message or "").strip()
    if not text:
        return text
    label = _COUNTY_LABELS.get(county_status_id(source_id))
    if not label:
        return text
    if _COUNTY_LEAD_RE.match(text) or re.search(rf"\b{re.escape(label)}\b", text, re.I):
        return text
    return f"{label} {text}"


def clear_progress(source_id: str | None = None) -> None:
    target = progress_path()
    if not target:
        return
    key = county_status_id(source_id)
    try:
        payload = {
            "step": "start",
            "message": with_county_prefix("Starting job…", key),
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if key:
            payload["source_id"] = key
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def report_progress(step: str, message: str, **extra) -> None:
    payload = read_progress()
    payload.update(extra)
    key = county_status_id(extra.get("source_id"), payload.get("source_id"))
    if key:
        payload["source_id"] = key
    text = with_county_prefix(message, key)
    payload["step"] = step
    payload["message"] = text
    payload["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"PROGRESS {text}", flush=True)
    target = progress_path()
    if not target:
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass
