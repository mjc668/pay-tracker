# Demo Seed Data

This folder contains a seed script that populates Pay Tracker with realistic demo data — useful for testing, screenshots, or showing the app to someone for the first time.

## What it creates

**User:** `demo@demo.com` / `demo1234`

**9 bill templates** covering all frequencies:

| Name | Category | Frequency | Amount |
|---|---|---|---|
| Rent | Housing | Monthly | €1,200.00 |
| Electricity | Utilities | Every 2 months | €95.00 |
| Internet | Utilities | Monthly | €39.99 |
| Netflix | Entertainment | Monthly | €17.99 |
| Car Insurance | Car | Annual | €680.00 |
| Gym Membership | Health | Monthly | €45.00 |
| Property Tax | Housing | Quarterly | €210.00 |
| Spotify *(archived)* | Entertainment | Monthly | €10.99 |
| Tyre Change | Car | One-off | €180.00 |

**17 payment instances** covering all statuses:
- **paid** — historical records with `paid_at` timestamps
- **overdue** — Internet June 2026 (missed payment)
- **upcoming** — July 2026 bills ready to be paid
- One paid amount that differs from the template (Electricity — real-world invoice variance)

## Requirements

- Docker containers must be running: `docker compose up`
- Python 3 with the `requests` package

## How to use!

**1. Install the dependency (one time):**

```bash
python3 -m pip install requests
```

**2. Start the app:**

```bash
docker compose up
```

**3. Run the seed script from the project root**

```bash
python3 demo/seed.py
```

**4. Open the app:**

Go to [http://localhost:3010](http://localhost:3010) and log in with `demo@demo.com` / `demo1234`.

## Re-running

Running the script again on the same account **wipes and re-seeds** — the restore endpoint replaces all existing data for that user. Safe to run multiple times.

## Editing the data

All seed data lives in `demo/seed_data.json`. It follows the same backup format used by the app's export/restore feature (`schema_version: 3`). Edit the JSON directly and re-run the script to apply changes.
