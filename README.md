# Inoperative Account Agent

SBI gives each CSP a printed list of inoperative accounts. Calling every customer
one by one doesn't scale. With this agent the CSP photographs the list, checks
what was read, and sends each customer a WhatsApp message (Hindi + English)
from **their own WhatsApp** with one tap per customer, asking them to visit the
CSP with KYC to reactivate the account.

**Customer lists are never saved on the server (DPDP).** The photo / Excel file is
read in memory and the rows go to the CSP's phone, where the list stays (browser
storage, deleted after 30 days). The server keeps only logins, counts per list for
the dashboard, and a hashed STOP list.

| Milestone | Status |
|---|---|
| 1. Read the photo (offline OCR) + validate rows | **Done** |
| 2. Lists kept only on the CSP's phone; server keeps counts only; logs, audit trail | **Done** |
| 3. Web page: CSP login, upload, review/edit, super admin | **Done** |
| 4. WhatsApp sending from the CSP's own WhatsApp, one tap per customer | **Done** |
| 5. Deploy on a server | Steps: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

On the phone the app also shows reminders for customers who haven't come after
7 days, tracks who came, and remembers STOP for every CSP.

For a demo, open **/about** ("How it works") - no login needed. Printable CSP
guide: **/guide**. Super admin can download a per-CSP Excel report.
How the processing works, step by step: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)
Data protection (DPDP Act 2023): [docs/DATA_PROTECTION.md](docs/DATA_PROTECTION.md)
The message text: [docs/WHATSAPP_TEMPLATE.md](docs/WHATSAPP_TEMPLATE.md)

## Setup (Windows or Linux, Python 3.11)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux: .venv/bin/pip
cp .env.example .env                              # then fill in the values
```

Everything runs offline. The OCR models ship inside the `rapidocr-onnxruntime`
package; no customer data leaves the machine until a WhatsApp message is sent.

## Run on a laptop

```bash
.venv/Scripts/python -m app.cli serve              # web page at http://127.0.0.1:8000
```

The first visit opens a one-time "Create super admin" page (only on that
computer, only until an admin exists, never in production). On a server use
`python -m app.cli create-admin` instead - see docs/DEPLOYMENT.md.

Then log in as super admin, import the CSP sheet (CSP Code, CSP Name, Shop
Address, optional Mobile/Branch), download the temporary passwords and share
each one privately. CSPs only need the link, their CSP code and that password;
they set their own password at first login. In production put the app behind
HTTPS (needed for security and for the phone camera) and set `APP_ENV=production`.

## Command line

```bash
.venv/Scripts/python -m app.cli import-csps sheet.xlsx   # same as the admin page import
.venv/Scripts/python -m app.cli read path/to/test-list.jpg   # read a made-up list, counts only
```

The CLI prints counts and problems only - never customer names or numbers.

## Tests

```bash
.venv/Scripts/python -m pytest -q
```

Tests use small hand-made inputs, never real customer lists.

## Project layout

Easy-language overview of the whole system: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Something broke? Logs and common problems: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

```
app/
  config.py         settings from .env
  logging_setup.py  agent.log + audit.log, customer numbers masked
  ocr_table.py      photo -> rows (OCR, header detection, curved-row tracing)
  ocr_voxomos.py    optional Voxomos OCR API (OCR_ENGINE=voxomos), falls back to local
  sheet_list.py     Excel / CSV list -> rows (no OCR)
  validate.py       mobile/account checks, name cleanup, shared-mobile grouping
  reader.py         reads a photo / Excel file in memory, hands rows to the phone, keeps nothing
  stats.py          counts per list (from the phones) for the dashboard; STOP list (hashed)
  users.py          CSP/admin accounts, password hashing, lockout, sheet import
  messages.py       the customer message (Hindi + English) - the WhatsApp template text
  db.py             SQLite: logins, list counts, opt-out hashes (no names or numbers)
  web.py            web page: login, CSP app (templates/csp.html), API for the phone, super admin
  templates/        page layouts (phone-first, Hindi + English)
  cli.py            command line: create-admin, import-csps, serve, extract, resume, purge
tests/              unit tests (no real data)
docs/               how it works, data protection, work log
data/               app.db: logins, list counts, STOP hashes - no customer lists (git-ignored)
logs/               agent.log, errors.log, audit.log (git-ignored, rotated daily)
```

## Settings (.env)

| Name | Meaning |
|---|---|
| `APP_ENV` | `development` or `production` |
| `EKO_BASE_PATH` | sub-path the app lives under, e.g. `/ocrproject` (links, redirects, cookie and page calls follow it); empty = root |
| `SECRET_KEY` | signs CSP login sessions |
| `LOG_LEVEL`, `LOG_DIR` | logging |
| `DATA_DIR` | logins, list counts, STOP hashes (no customer lists) |
| `RETENTION_DAYS` | lists are deleted from the CSP's phone after this many days (default 30) |
| `AUDIT_RETENTION_DAYS` | audit log kept this many days (default 365, DPDP Rules) |
| `OCR_MIN_CONFIDENCE` | rows read less confidently are flagged for review (default 0.80) |
| `OCR_ENGINE` | `local` (default, offline) or `voxomos` (Eko's in-house OCR API; falls back to local if it fails). **Keep `local` until DPDP clearance** - see docs/DATA_PROTECTION.md |
| `VOXOMOS_URL`, `VOXOMOS_API_KEY`, `VOXOMOS_TIMEOUT` | only for `OCR_ENGINE=voxomos`; the key lives only in `.env` |
| `LOGIN_MAX_FAILED`, `LOGIN_LOCKOUT_MINUTES` | login lock (0 = off; keep 15 on the server) |
| `OPTOUT_KEY` | hashes opted-out numbers - set once, never change after go-live |
| `GRIEVANCE_CONTACT` | complaint phone / email shown to customers (from compliance) |
| `FOLLOWUP_DAYS`, `MAX_FOLLOWUPS` | reminder on the CSP's phone after 7 days, once |

## Logs

- `logs/agent.log` - what the agent did, step by step (rotated daily).
- `logs/audit.log` - one JSON line per action: login, upload, list read, list
  saved, sending started, STOP, admin actions - with CSP id and counts only. The super
  admin page shows the latest entries as "Recent activity".

Every log line is filtered so 9+ digit numbers (mobile, account, CIF, Aadhaar)
appear only as their last 4 digits. Names are never logged.
