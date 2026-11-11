"""Dual-affidavit store, listing stamp, and HA-local sweep runner.

Read-only toward Follow Up Boss. Results live under the integration data dir
as ``affidavits.json`` and are exposed via ``/api/placer_probate_monitor/affidavits``.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

AFFIDAVITS_FILENAME = "affidavits.json"
AFFIDAVIT_LAST_RUN_KEY = "last_run_date"


def affidavits_path(data_dir: Path) -> Path:
    return Path(data_dir) / AFFIDAVITS_FILENAME


def empty_store() -> dict[str, Any]:
    return {
        "generated_at": "",
        AFFIDAVIT_LAST_RUN_KEY: "",
        "count": 0,
        "by_case": {},
        "results": [],
    }


def load_affidavits(data_dir: Path) -> dict[str, Any]:
    path = affidavits_path(data_dir)
    if not path.exists():
        return empty_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _LOGGER.warning("Could not read %s: %s", path, exc)
        return empty_store()
    if not isinstance(payload, dict):
        return empty_store()
    by_case = payload.get("by_case")
    if not isinstance(by_case, dict):
        by_case = {}
        for row in payload.get("results") or []:
            if isinstance(row, dict) and row.get("case_number"):
                by_case[str(row["case_number"])] = row
        payload["by_case"] = by_case
    payload.setdefault("results", list(by_case.values()))
    payload.setdefault("count", len(by_case))
    payload.setdefault("generated_at", "")
    payload.setdefault(AFFIDAVIT_LAST_RUN_KEY, "")
    return payload


def save_affidavits(data_dir: Path, payload: dict[str, Any]) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = affidavits_path(data_dir)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def case_record_from_result(result: Any) -> dict[str, Any]:
    """Normalize a SweepRunner CaseResult or dict into the store row."""
    if hasattr(result, "to_dict") and hasattr(result, "csv_row"):
        row = result.csv_row()
        full = result.to_dict()
        return {
            "case_number": row.get("case_number") or "",
            "decedent": row.get("decedent") or "",
            "dual_signal": row.get("dual_signal") or "no",
            "dual_score": int(row.get("score") or 0),
            "dual_reason": row.get("reason") or "",
            "coverage": row.get("coverage") or "",
            "apn": row.get("apn") or "",
            "apn_source": row.get("apn_source") or "",
            "own_aod_docs": row.get("own_aod_docs") or "",
            "related_docs": row.get("related_docs") or "",
            "hearing_de111": row.get("hearing_de111") or "",
            "hearing_listing": row.get("hearing_listing") or "",
            "hearing_mismatch": row.get("hearing_mismatch") or "no",
            "address": row.get("address") or "",
            "spouse": row.get("spouse") or "",
            "spouse_dod": row.get("spouse_dod") or "",
            "dod": row.get("dod") or "",
            "evidence": full.get("evidence") or [],
        }
    if isinstance(result, dict):
        return {
            "case_number": str(result.get("case_number") or ""),
            "decedent": str(result.get("decedent") or ""),
            "dual_signal": str(result.get("dual_signal") or "no"),
            "dual_score": int(result.get("dual_score") or result.get("score") or 0),
            "dual_reason": str(result.get("dual_reason") or result.get("reason") or ""),
            "coverage": str(result.get("coverage") or ""),
            "apn": str(result.get("apn") or ""),
            "apn_source": str(result.get("apn_source") or ""),
            "own_aod_docs": str(result.get("own_aod_docs") or ""),
            "related_docs": str(result.get("related_docs") or ""),
            "hearing_de111": str(result.get("hearing_de111") or ""),
            "hearing_listing": str(result.get("hearing_listing") or ""),
            "hearing_mismatch": str(result.get("hearing_mismatch") or "no"),
            "address": str(result.get("address") or ""),
            "spouse": str(result.get("spouse") or ""),
            "spouse_dod": str(result.get("spouse_dod") or ""),
            "dod": str(result.get("dod") or ""),
            "evidence": result.get("evidence") or [],
        }
    return {}


def stamp_listing_affidavit(row: dict, store: dict[str, Any] | None) -> dict:
    """Attach dual-signal fields onto a listings row (mutates and returns)."""
    case = str(row.get("case_number") or "").strip()
    by_case = (store or {}).get("by_case") or {}
    hit = by_case.get(case) if case else None
    if not isinstance(hit, dict):
        row.setdefault("dual_signal", "")
        row.setdefault("dual_score", None)
        row.setdefault("dual_reason", "")
        row.setdefault("dual_apn", "")
        row.setdefault("dual_coverage", "")
        row.setdefault("hearing_mismatch", "")
        return row
    row["dual_signal"] = str(hit.get("dual_signal") or "")
    row["dual_score"] = hit.get("dual_score")
    row["dual_reason"] = str(hit.get("dual_reason") or "")
    row["dual_apn"] = str(hit.get("apn") or "")
    row["dual_coverage"] = str(hit.get("coverage") or "")
    row["hearing_mismatch"] = str(hit.get("hearing_mismatch") or "")
    row["own_aod_docs"] = str(hit.get("own_aod_docs") or "")
    row["related_docs"] = str(hit.get("related_docs") or "")
    # Prefer DE-111 / sweep address when listing decedent_address is empty.
    if not str(row.get("decedent_address") or "").strip() and hit.get("address"):
        row["decedent_address"] = str(hit.get("address") or "")
    return row


def build_affidavits_payload(data_dir: Path) -> dict[str, Any]:
    store = load_affidavits(data_dir)
    return {
        "count": int(store.get("count") or len(store.get("by_case") or {})),
        "generated_at": store.get("generated_at") or "",
        "last_run_date": store.get(AFFIDAVIT_LAST_RUN_KEY) or "",
        "by_case": store.get("by_case") or {},
        "results": store.get("results")
        or list((store.get("by_case") or {}).values()),
    }


def ran_today(store: dict[str, Any], today: date | None = None) -> bool:
    stamp = str(store.get(AFFIDAVIT_LAST_RUN_KEY) or "")[:10]
    if not stamp:
        return False
    day = today or date.today()
    return stamp == day.isoformat()


def should_run_affidavit_sweep(
    data_dir: Path,
    *,
    force: bool = False,
    today: date | None = None,
) -> bool:
    if force:
        return True
    return not ran_today(load_affidavits(data_dir), today=today)


def run_affidavit_sweep(
    data_dir: Path,
    *,
    listings: list[dict] | None = None,
    case: str | None = None,
    max_searches: int = 40,
    refresh: bool = False,
    offline: bool = False,
    fixtures_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run the dual-affidavit pipeline against local HA listings.

    Cache-first. Never writes to Follow Up Boss. At-most-daily unless ``force``.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    existing = load_affidavits(data_dir)
    today = date.today()
    if not force and ran_today(existing, today=today) and not case:
        _LOGGER.info("Affidavit sweep already ran today (%s); skipping", today.isoformat())
        payload = build_affidavits_payload(data_dir)
        payload["skipped"] = True
        payload["reason"] = "already_ran_today"
        return payload

    if listings is None and fixtures_dir is None:
        try:
            from .placer_probate_monitor import build_listings_payload
        except ImportError:
            from placer_probate_monitor import build_listings_payload

        listings = list(build_listings_payload(data_dir).get("listings") or [])

    from .dual_sweep.pipeline import SweepRunner

    # Keep sweep caches under the integration data dir.
    runner = SweepRunner(
        data_dir,
        fixtures_dir=fixtures_dir,
        listings=listings,
        max_searches=max_searches,
        refresh=refresh,
        offline=offline or fixtures_dir is not None,
    )
    try:
        results = runner.run(case=case, top_n=50)
    finally:
        runner.close()

    by_case = dict(existing.get("by_case") or {})
    for result in results:
        rec = case_record_from_result(result)
        if rec.get("case_number"):
            by_case[str(rec["case_number"])] = rec

    store = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        AFFIDAVIT_LAST_RUN_KEY: today.isoformat(),
        "count": len(by_case),
        "by_case": by_case,
        "results": list(by_case.values()),
    }
    save_affidavits(data_dir, store)
    payload = build_affidavits_payload(data_dir)
    payload["skipped"] = False
    payload["processed"] = len(results)
    return payload
