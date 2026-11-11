"""HA affidavits store + listing stamp (no live CountyFusion / no HA install)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CC = REPO / "custom_components" / "placer_probate_monitor"
FIX = REPO / "sweep" / "tests" / "fixtures"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def affidavits_mod():
    # Load dual_sweep package namespace first so relative imports resolve.
    pkg_name = "ppm_dual_sweep_test"
    if pkg_name not in sys.modules:
        pkg = type(sys)("pkg")
        # Minimal package scaffolding for dual_sweep under a unique name.
        import types

        root = types.ModuleType("ppm_test_cc")
        root.__path__ = [str(CC)]  # type: ignore[attr-defined]
        sys.modules["ppm_test_cc"] = root
        dual = types.ModuleType("ppm_test_cc.dual_sweep")
        dual.__path__ = [str(CC / "dual_sweep")]  # type: ignore[attr-defined]
        sys.modules["ppm_test_cc.dual_sweep"] = dual
    # Import dual_sweep submodules with package context by path package.
    # Simpler path: add CC parent to sys.path and import dual_sweep as top-level alias.
    if str(CC) not in sys.path:
        sys.path.insert(0, str(CC))
    # affidavits imports .dual_sweep — needs package. Load via file after
    # registering parent package without executing HA __init__.
    import types

    parent = types.ModuleType("custom_components")
    parent.__path__ = [str(REPO / "custom_components")]  # type: ignore[attr-defined]
    sys.modules.setdefault("custom_components", parent)
    ppm = types.ModuleType("custom_components.placer_probate_monitor")
    ppm.__path__ = [str(CC)]  # type: ignore[attr-defined]
    # Do NOT execute HA __init__.py (needs homeassistant).
    sys.modules["custom_components.placer_probate_monitor"] = ppm
    return _load(
        "custom_components.placer_probate_monitor.affidavits",
        CC / "affidavits.py",
    )


def test_stamp_listing_affidavit_fields(affidavits_mod):
    store = {
        "by_case": {
            "S-PR-0014335": {
                "case_number": "S-PR-0014335",
                "dual_signal": "yes",
                "dual_score": 100,
                "dual_reason": "spouse AOD",
                "apn": "001-032-006-000",
                "coverage": "full",
                "hearing_mismatch": "yes",
                "address": "138 Palm Avenue, Auburn, CA",
            }
        }
    }
    row = {"case_number": "S-PR-0014335", "decedent_address": ""}
    stamped = affidavits_mod.stamp_listing_affidavit(row, store)
    assert stamped["dual_signal"] == "yes"
    assert stamped["dual_score"] == 100
    assert stamped["dual_apn"] == "001-032-006-000"
    assert stamped["decedent_address"].startswith("138")


def test_run_affidavit_sweep_offline(tmp_path: Path, affidavits_mod):
    payload = affidavits_mod.run_affidavit_sweep(
        tmp_path,
        fixtures_dir=FIX,
        offline=True,
        force=True,
        max_searches=10,
    )
    assert payload["count"] >= 5
    assert payload["skipped"] is False
    assert payload["by_case"]["S-PR-0014335"]["dual_signal"] == "yes"
    assert payload["by_case"]["S-PR-0014387"]["dual_signal"] == "sold"

    again = affidavits_mod.run_affidavit_sweep(
        tmp_path, fixtures_dir=FIX, offline=True, force=False
    )
    assert again["skipped"] is True

    api = affidavits_mod.build_affidavits_payload(tmp_path)
    assert api["count"] == payload["count"]
    assert (tmp_path / "affidavits.json").exists()
