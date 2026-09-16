# Placer County daily probate monitor

Hammond IT Consulting — Blake Hammond Realty

One local command that:

1. Pulls [CNPA public notices](https://www.capublicnotice.com) for
   **NOTICE OF PETITION TO ADMINISTER ESTATE** in **Placer County**
2. Looks up each `S-PR` number on
   [Placer eCourt Public](https://webportal.placerco.org/eCourtPublic/?q=node/48)
   using a full-year **Filed** date range
3. Writes a dossier PDF in the same layout as the sample daily feed
4. Optionally emails the digest with the PDF attached

A published petition is **not** proof that a house is in the estate.

## What you get per estate

From the newspaper notice:

- Decedent, petitioner, case number
- Hearing text printed in the ad
- Will / IAEA flags
- Attorney name, firm, phone
- Paper and publication dates
- Notice URL

From the court portal (same session as a manual search):

- Case Summary URL (`?q=node/45/…`)
- Official caption and filing date
- Parties (petitioner, decedent, objector, administrator)
- Next hearing and prior hearings
- Document register titles and dates
- Court-assigned counsel
- Filing / appearance fees

## Setup

```bash
cd placer-probate-monitor
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` only if you want email. Gmail needs an
[App Password](https://myaccount.google.com/apppasswords), not your normal password.

## Run

Print + write files, do not email, do not update seen-cases:

```bash
python3 placer_probate_monitor.py --dry-run
```

CNPA + eCourt + PDF, no email:

```bash
python3 placer_probate_monitor.py --no-email
```

Full daily job (update tracker and email PDF):

```bash
python3 placer_probate_monitor.py
```

Skip the court portal if it is down:

```bash
python3 placer_probate_monitor.py --no-email --skip-portal
```

Outputs in `data/reports/`:

- `Placer-Probate-Daily-Feed-YYYY-MM-DD.pdf`
- `dossiers-YYYY-MM-DD.json` (merged notice + portal)
- `notices-YYYY-MM-DD.json`
- `report-YYYY-MM-DD.html` / `.txt`

## Daily schedule

Linux / macOS cron (8:30 a.m. Pacific):

```cron
TZ=America/Los_Angeles
30 8 * * * cd /FULL/PATH/placer-probate-monitor && .venv/bin/python placer_probate_monitor.py >> data/cron.log 2>&1
```

macOS launchd: a LaunchAgent that runs the same command.

Windows Task Scheduler: start program
`C:\path\to\.venv\Scripts\python.exe` with argument
`placer_probate_monitor.py` and start-in folder set to the project.

## How the court lookup works

The public Case Summary URL 404s if you open it cold.
The script:

1. GET the search form
2. POST case number + Filed `01/01/{year}`–`12/31/{year}`
3. Read filing date / next event / Case Summary link
4. GET that link **in the same cookie session**
5. Pause ~1.2 seconds between cases

Do not raise the rate. One run per day is enough.

## Files

| File | Role |
|---|---|
| `placer_probate_monitor.py` | Daily entry point |
| `ecourt_client.py` | Placer portal search + Case Summary parse |
| `pdf_report.py` | Dossier PDF |
| `make_sample_pdf.py` | Frozen 16 Sep 2026 sample (optional) |

## Limits

- Portal documents are titles only. You cannot download the petition from the public site.
- No inventory / appraisal and no APN appear on these pages.
- CNPA only has papers that upload. A filing with no published notice will not show up here.
- If eCourt HTML changes, `ecourt_client.py` is the file to adjust.
