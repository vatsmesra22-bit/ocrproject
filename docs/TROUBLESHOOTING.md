# Problem aaye to kya karein

## 1. Logs kahan hain

Folder: `inoperative-account-agent\logs\` (laptop ya server par)

| File | Isme kya hai | Kab kholo |
|---|---|---|
| `errors.log` | **Sirf problems** - error, crash, warning | **Sabse pehle yahi** |
| `agent.log` | Sab kuch jo hua (list padhi, kitna time laga...) | Detail chahiye to |
| `audit.log` | Kisne kya kiya (login, upload, save, send) | Kaun/kab dekhna ho to |

- Har din nayi file banti hai; purani file ke naam ke aage date lagti hai
  (jaise `errors.log.2026-10-22`).
- `errors.log` 90 din, `agent.log` 30 din, `audit.log` 365 din rakhe jaate hain.
- Logs mein customer ke number **chhupe** hote hain (`******3210`), naam kabhi nahi.

## 2. Log kaise padhein

Har line: `tarikh samay  LEVEL  kahan_se: kya hua`

```
2026-10-22 16:28:12 WARNING app.ocr_table: Voxomos OCR failed (service unreachable) - reading locally
```

- `INFO` = normal, `WARNING` = dhyan do, `ERROR` / `CRITICAL` = problem.
- `CRASH ... program stopped` = app band ho gaya - neeche `Traceback` mein
  aakhri line asli wajah batati hai.

## 3. Aam problems

| Kya dikha | Matlab | Kya karein |
|---|---|---|
| `Voxomos OCR failed ... reading locally` | Voxomos ne jawab nahi diya | Kuch nahi - local OCR ne padh liya; baar-baar ho to internet / Voxomos check karo |
| `service answered HTTP 401` | Voxomos key galat ya band | `.env` mein `VOXOMOS_API_KEY` check karo |
| `ocr pass ... took 150 s` | Laptop dheema | Charger lagao, dusre bhari program band karo |
| `reading a photo crashed` | Photo padhte waqt crash | Nayi saaf photo lo; `errors.log` ki Traceback Claude ko dikhao |
| `Missing column header(s)` | List ke column titles nahi mile | Photo mein titles wali line saaf aani chahiye |
| Page khulta hi nahi | App band hai | App dobara chalao (neeche) |

## 4. App dobara chalana

```
cd inoperative-account-agent
.\tools\run_test_mode.ps1
```
Phir browser mein `http://127.0.0.1:8000`. Beech mein ruki list apne aap aage chalti hai.

## 5. Claude / kisi aur ko dikhana ho to

- `errors.log` ki **sirf error wali lines** bhejo - customer list ki photo ya data **kabhi nahi** (DPDP).

## 6. Code kahan hai (kaunsi file kya karti hai)

Aasaan nakshe ke liye: [ARCHITECTURE.md](ARCHITECTURE.md). Har file ke upar uska kaam likha hai.
