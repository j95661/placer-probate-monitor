# Dual Affidavit of Death sweep

Read-only CLI pipeline for Placer County probate listings. Resolves APN via
free GIS, searches the CountyFusion guest recorder index, and ranks
dual-affidavit signals (predeceased spouse, successor-trustee handoff, shared
parcel). **Never writes to Home Assistant or Follow Up Boss (v1).**

## Layout

| Path | Role |
|---|---|
| `sweep/sources/ha.py` | HA listings + DE-111 download |
| `sweep/ocr.py` | `pdftoppm` + RapidOCR + DE-111 field extract |
| `sweep/parcels.py` | Placer Public_Parcels APN lookup |
| `sweep/recorder/placer_countyfusion.py` | CountyFusion guest (`RecorderSource`) |
| `sweep/score.py` | Doc classes + dual-signal rules |
| `sweep/cli.py` | `python -m sweep run` |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Live OCR + recorder only:
sudo apt-get install -y poppler-utils   # pdftoppm
playwright install chromium
cp .env.example .env   # set HA_URL + HA_TOKEN
```

## Run

Offline acceptance fixtures (no HA / no CountyFusion):

```bash
python -m sweep run --fixtures sweep/tests/fixtures
```

Live (cache-first under `data/`):

```bash
python -m sweep run
python -m sweep run --case S-PR-0014335
python -m sweep run --since 2026-11-01 --max-searches 20
python -m sweep run --refresh
```

Outputs:

- `out/affidavit_sweep.csv`
- `out/affidavit_sweep.json`
- `out/leads.md`

## Tests

```bash
PYTHONPATH=. pytest -q sweep/tests
```

CI uses recorded fixtures only — no live CountyFusion calls.

## Later (not v1)

Expose results as a “Dual signals” column on the Hammond Realty Probate
listings tab via `/api/placer_probate_monitor/affidavits`, fed by a scheduled
run at most daily.
