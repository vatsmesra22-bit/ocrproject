# How the agent processes a list

**Where the list lives:** only on the CSP's phone (browser storage, `templates/csp.html`).
The server reads the photo in memory, gives the rows to the phone and forgets them.
It never writes a photo, a list, a name or a number to disk (DPDP).

## 1. Upload → read in memory  (`reader.start`)

- The CSP uploads a photo (JPG/PNG/WebP/BMP, up to 15 MB). It is held **in memory
  only**, never written to disk. Photos are read one at a time; the phone shows a
  timer and how many lists are ahead.
- When the reading is done the phone collects the rows (`reader.take`) - from that
  moment they are no longer on the server. Uncollected results are dropped after
  15 minutes. Audit events: `list_uploaded`, `list_read` (counts only).

## 1b. Photo quality check  (`ocr_table.photo_problem`)

Refused with a clear "please take the photo again" message when the photo is:
too small (< 700 px, e.g. a screenshot), too dark, blurry, or JPEG-compressed
below quality 55 (typically forwarded on WhatsApp). Limits come from a stress
test: below them the OCR started misreading digits that still looked valid.

## 1c. Or: the list as an Excel / CSV file  (`sheet_list.py`)

If the CSP has the list as a file, **📊 Upload Excel file** reads the cells
directly - no OCR, exact numbers - with the same column, inoperative and
minimisation rules, in memory, then goes straight to the check screen (step 8).

If a photo still can't be read, the agent stops after `OCR_TIME_LIMIT` (150 s) and asks
for a clearer photo; the waiting page shows a timer and, after a minute, a
"take a new photo" button.

**Optional second engine (`OCR_ENGINE=voxomos`, off by default):** the photo is sent
to Eko's in-house OCR API (Voxomos), which returns the table as records keyed by the
list's own column titles. `ocr_voxomos.py` maps the titles with the same rules as
below, keeps only account / mobile / name, drops operative rows, and the rows go
through the same validation and check screen. Any service problem (down, error,
nothing found) falls back to the local engine automatically. Made-up test: 5/5
rows in ~6 s (local: 25-40 s).

## 2. OCR: photo → text boxes  (`ocr_table.run_ocr`)

- Engine: **RapidOCR**, which runs Baidu's open-source **PaddleOCR** models
  through ONNX Runtime. Installed from PyPI (`rapidocr-onnxruntime`), Apache-2.0,
  fully **offline** - no internet, no API key, no per-page cost.
- Output: a list of text boxes, each with its 4 corner points, the text, and a
  confidence score (0-1).
- Takes about 10-20 seconds per photo on a normal laptop.

## 3. Find the column titles  (`ocr_table._header_matches`)

- Lists don't share one format, so columns are found **by name, not position**.
  Known spellings: account = `AcNo`, `MEMB_CUST_AC`, `Account No`...;
  mobile = `MobileNo`, `MOBILE_NBR`...; name = `Name1`, `NAME`, `Cust Name`...
- OCR sometimes merges titles (`MEMB_CUST_ACNAME`); they are split by matching
  the known spellings.
- A new list format usually only needs its title spellings added to
  `HEADER_KEYWORDS`.

## 4. Follow each printed row  (`ocr_table._trace_lines`)

- A phone photo of paper is **curved**: on the sample, the left column tilts up
  and the right column tilts down, so a row's mobile number can sit almost a
  full row lower than its account number. Straight-line grouping mixes rows up.
- So each row is **traced box by box**: every box's own tilt predicts where its
  row continues, and it is linked to the box on its right that lands there.

## 5. Pick the 3 fields we need  (`ocr_table.parse_table`)

- Boxes that hold two columns (`91482064354Ratneshwari`) are split into number
  and word pieces, each with its estimated position.
- Each piece goes to the nearest column title of the same kind (numbers to
  number columns, words to text columns).
- If the list has an Operative/Inoperative column, **only INOPERATIVE customers are
  kept**; operative accounts are skipped (and counted for the CSP).
- Numbers shorter than 9 digits (dates, codes) are never taken as account or mobile.
- **Only account, mobile and name are kept.** CIF, father's name, address,
  region etc. are read by the OCR engine but discarded here (DPDP minimisation).
- A row is marked *low confidence* if any of its pieces scored below
  `OCR_MIN_CONFIDENCE`.

## 5b. Read twice, flag disagreements  (`ocr_table.extract_rows`)

- A tilted photo (> 2°) is straightened first and read again.
- A photo taken sideways or upside down is turned round automatically (the
  agent tries 90°, 270° and 180° when the straight reading finds no table).
- The photo is then read a **second time**, enlarged and sharpened. Any row
  whose account + mobile differ between the two readings is marked
  "numbers unclear - please match with the paper".
- Stress test on the samples (blur, dark, glare, tilt, low resolution,
  compression, grain): no wrong row went through unflagged once the quality
  limits and the second reading were in place. Reading takes ~20-40 s.
- Some digits are smudged on the paper itself, so the CSP's paper check before
  sending stays mandatory.

## 6. Validate  (`validate.py`)

- Mobile: 10 digits starting 6-9 (a leading 91 is removed).
- Account: 11 digits; the same account twice is flagged as a duplicate.
- Name: OCR drops spaces (`SATISHKUMAR`), printers cut names off (`MAHESHKUM`),
  and some lists mask names (`SIMRAN XXX`). Common name parts are used to split
  them; the message greets with the **first name only**, or "Customer".
- Any problem marks the row **needs review**; it is not messaged until fixed.
- A customer with **no mobile** is shown as "call / visit" - not an error, not messaged.
- Customers who share one mobile (families) are grouped: **one message per
  mobile**, listing each account's last 4 digits.

## 7. The list goes to the phone  (`templates/csp.html`)

- The phone stores the rows in its own browser storage, together with the check
  result (`/api/check`), and works out whether the same list was uploaded before
  on this phone (80%+ same account numbers = **Repeat**, with a warning).
- After every change the phone sends **only counts** (customers, to fix, sent,
  came...) to the server for the super admin's dashboard (`/api/stats`, `stats.py`).
- Lists older than `RETENTION_DAYS` (30) are deleted from the phone automatically;
  the CSP can also delete a list at any time.

## 8. CSP review  (`/api/check`)

- The CSP fixes flagged rows (or ticks Remove), can add a missed customer, and
  presses Save. The phone sends the rows to `/api/check`, which checks them and
  returns the messages - it stores and logs nothing. Name, 11-digit account and
  10-digit mobile are required; duplicates are flagged.
- Customers who said STOP to any CSP before are marked and never messaged
  (the server only has a keyed hash of their number).

## 9. Send from the CSP's own WhatsApp

- After saving, the CSP ticks **"I have matched every mobile number with the
  paper"** - the last human check against OCR misreads - and presses
  **Send from my WhatsApp**.
- Every customer gets a big **📲 WhatsApp** button. It opens WhatsApp on the CSP's
  phone on that customer's number with the message already written (`wa.me` link).
- The app can't see inside WhatsApp, so a tap only marks **"Opened - did it go?"**.
  Coming back, the CSP answers **Yes, sent** (counted as sent) or **No**.
- A sticky **📲 Next customer** button jumps to the next customer not done yet.
- **Not on WhatsApp** (shows a 📞 Call button) and **Said STOP** (number blocked for
  every CSP) are one tap each. **✅ Came** marks a customer who visited.
- No API, no Meta approval, no cost; messages come from a number the customer knows.

## 10. Reminders  (on the phone)

- A customer whose message went `FOLLOWUP_DAYS` (7) days ago and who hasn't come
  shows in **🔔 Reminders due** on the home screen, once (`MAX_FOLLOWUPS`), with a
  one-tap reminder message. Came / STOP stop the reminders.

## If something goes wrong

| What happens | What the agent does |
|---|---|
| Server restarts while a photo is being read | the reading is lost (it was only in memory); the phone says "expired - please upload again" |
| Phone loses network | the list is safe on the phone; counts are sent again with the next change |
| OCR engine crashes / bad image | clear error on the phone: take a new photo |
| Column titles not visible | clear error: retake the photo with titles visible |
| No rows read | clear error: retake flat, in good light |
| Browser data cleared / new phone | the list is gone from that phone - upload it again (nothing is on the server) |

## Results on the two sample lists (19 Oct 2026)

| Sample | Rows on paper | Rows read | Account + mobile correct | Messages |
|---|---|---|---|---|
| Curved phone photo, 4 columns | 46 | 46 | 46 | 46 |
| Scanned sheet, ~10 columns | 56 | 56 | 56 | 54 (2 shared mobiles) |

Accuracy was checked by comparing every row against the photo by eye.
