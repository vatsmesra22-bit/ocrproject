# Data protection - DPDP Act 2023 checklist

Engineering view only - **not legal advice**. Eko's compliance team must confirm
the items marked ⚖️. Section numbers refer to the Digital Personal Data
Protection Act, 2023; "Rules" to the DPDP Rules, 2025 (phased start - compliance
to confirm which obligations already apply).

Roles: **SBI** decides why the data is used (data fiduciary). **Eko Bharat
Ventures** runs Grahak Sampark for SBI's CSPs (data processor). ⚖️ confirm.

## ✅ Built into the app

| DPDP requirement | How Grahak Sampark meets it | Where |
|---|---|---|
| Lawful purpose, purpose limitation (s.4, s.8) | Data used only for the one reactivation message; no export, no other use | design |
| Notice (s.5, Rules) | Message says who (SBI CSP / Eko), why, how to stop (STOP) and **where to complain** (`GRIEVANCE_CONTACT`); public **/privacy** notice page | `messages.py`, `templates/privacy.html` |
| Data minimisation | Only name, mobile, account kept; CIF, father's name, address dropped right after OCR; message shows only first name + last 4 digits | `ocr_table.parse_table`, `messages.params` |
| Accuracy (s.8(3)) | Two OCR readings, red flags, mandatory "matched with paper" tick before sending | `ocr_table.extract_rows`, review page |
| Storage limitation / erasure (s.8(7)) | **No customer list is ever saved on the server**: photo/file read in memory, rows handed to the CSP's phone and forgotten; on the phone lists auto-deleted after `RETENTION_DAYS` (30) | `reader.py`, `templates/csp.html` |
| Security safeguards (s.8(5), Rules) | Offline OCR (no third party sees the photo); per-CSP login, scrypt passwords, lockout, idle logout, CSRF, HTTPS-only cookies in production; numbers masked in all logs; names never logged | `users.py`, `web.py`, `logging_setup.py` |
| Logs kept 1 year (Rules) | `audit.log` kept `AUDIT_RETENTION_DAYS` (365) - no names / full numbers | `logging_setup.py` |
| Right to erasure / withdraw (s.6(4), s.12) | Nothing to erase on the server (no lists there). Super admin **"Block number"**: no CSP can message that number again (keyed hash only); the CSP deletes the list on their phone | `stats.py` |
| Right to object to messages | **Said STOP** button; remembered for all CSPs as a keyed hash of the number | `stats.py` |
| Access control | Each CSP sees only own lists; super admin sees counts, not customer rows | `web.py` |
| Accountability | Every login, upload, review, send, erase, admin action in `audit.log` and on the admin page | `logging_setup.audit` |
| No double contact | Same list uploaded again is flagged "Repeat" on the phone; each customer's status is kept on the phone | `templates/csp.html` |

## ⚠️ Sending from the CSP's own WhatsApp (pilot default)

- The message reaches the customer through WhatsApp (Meta) and stays in the CSP's
  phone like any customer chat. CSPs must be told: don't forward or save the
  lists or chats, and tap **Said STOP** when a customer asks to stop.
- The photo upload page should only be used on the CSP's own phone / computer.

## 🔌 Voxomos OCR API (optional, OFF)

`OCR_ENGINE=voxomos` sends the list photo to an outside OCR service. It stays **off** (`OCR_ENGINE=local`) and must only be used
with made-up lists until all four are done:

1. The service does not keep results (the app logs a warning when the reply says
   `saved_to`), or deletes them right away.
2. Service hosted **in India**.
3. **Data agreement** with the service (processor terms, deletion, breach notice).
4. A key only for this project, kept only in the server `.env` - never in code or git.

Even when on, only account / mobile / name are kept from the reply.

## ⚖️ For Eko compliance - not code

1. **Legal basis** for contacting these customers (consent vs legitimate use / bank's
   own obligation to notify inoperative accounts).
2. **Agreement SBI ↔ Eko** covering this processing (s.8(2)).
3. **Grievance officer / DPO contact** to put in `GRIEVANCE_CONTACT` (s.8(10)) and
   the time limit for answering requests.
4. **Breach process** (s.8(6), Rules): who informs the Data Protection Board and
   affected customers, and within what time.
5. **Retention periods**: 30 days for lists on the CSP's phone, 365 days for the audit log.
6. **Minors' accounts** (s.9): lists may include accounts of children - decide how
   these are handled.
7. **Message wording** sign-off (Hindi + English).

## 🛠 Before go-live (tech)

- `DATA_DIR` holds only logins, counts and STOP hashes - encrypted disk still recommended.
- `GRIEVANCE_CONTACT` filled in; `APP_ENV=production`; HTTPS only.
- Backups encrypted and kept no longer than the retention period.

## 🧹 Test data on the developer laptop

Test photos on a developer laptop: delete them after testing; they are never committed to git. (Test lists are no
longer stored in `data/` - lists live only in the browser that uploaded them.)
