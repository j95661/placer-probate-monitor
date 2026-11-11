# Placer Probate Monitor

HACS custom **integration** (not an add-on). Add this GitHub repository in HACS as type **Integration**.

A Supervisor add-on is also in this repo (`repository.yaml`). Use HACS *or* the add-on, not both.

Configure recipients, SMTP, and run frequency in the Home Assistant UI.

v1.3.157+ adds a **Dual signals** column on Probate listings, fed by
`/api/placer_probate_monitor/affidavits` and the
`placer_probate_monitor.affidavit_sweep` service (scheduled at most daily).
