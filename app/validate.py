"""Check OCR rows and prepare them for messaging.

- Mobile must be an Indian mobile: 10 digits starting 6-9.
- SBI account numbers are 11 digits.
- Names come out of OCR without spaces ("SATISHKUMAR") and may be masked
  ("SIMRAN XXX") or cut off by the printer; we split common name parts and
  greet with the first name only.
- Several customers often share one family mobile: they get one message.
"""
import re

ACCOUNT_LEN = 11
_MOBILE = re.compile(r"^[6-9]\d{9}$")

# Common name parts on these lists, used to split names OCR glued together.
_PREFIXES = ["MOHAMMAD", "MOHAMMED", "MOHD", "MD", "SHRI", "SMT"]
_SUFFIXES = sorted([
    "KUMARI", "KUMAR", "DEVI", "SINGH", "YADAV", "AHMED", "AHMAD", "ALI", "ANSARI",
    "KHATOON", "KHATUN", "KHAN", "KHANAM", "PARVEEN", "PRAVEEN", "BEGUM", "RAM", "DAS",
    "RAY", "RAI", "SHARMA", "GUPTA", "PRASAD", "MANDAL", "PASWAN", "MAHTO", "SAH", "SHAH",
    "HUSSAIN", "HUSAIN", "MALIK", "NAZ", "TIWARI", "MISHRA", "JHA", "SAIFI", "PAL", "RAJ",
    "NABI", "RAHMAT", "ARYAN", "THAKUR", "CHAUDHARY", "SAHU", "VERMA", "PANDEY",
], key=len, reverse=True)
_MASK = re.compile(r"^X{2,}$")


def clean_mobile(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def _split_word(word, at_end=False):
    """'SATISHKUMAR' -> ['SATISH', 'KUMAR']; leaves real single words alone.

    at_end: this word ends the name, so the printer may have cut it off
    ('MAHESHKUM'). Only then, and only for long glued words, is a cut-off
    surname split away - otherwise real names like 'MOHSIN' would lose 'SIN'.
    """
    up = word.upper()
    for p in _PREFIXES:
        if up.startswith(p) and len(up) - len(p) >= 3:
            return [word[:len(p)]] + _split_word(word[len(p):], at_end)
    for s in _SUFFIXES:
        if up.endswith(s) and len(up) - len(s) >= 3:
            return _split_word(word[:-len(s)]) + [word[-len(s):]]
    for s in _SUFFIXES:
        # surname in the middle: 'ANILKUMARJI' -> ANIL KUMAR JI
        i = up.find(s, 3)
        if len(s) >= 4 and i > 0:
            return (_split_word(word[:i]) + [word[i:i + len(s)]]
                    + _split_word(word[i + len(s):], at_end))
    if at_end and len(up) >= 8:
        for s in _SUFFIXES:
            # surname cut off by the printer: 'MAHESHKUM' -> MAHESH KUM
            for cut in range(len(s) - 1, 2, -1):
                if len(s) >= 4 and up.endswith(s[:cut]) and len(up) - cut >= 3:
                    return _split_word(word[:-cut]) + [word[-cut:]]
    return [word]


def clean_name(raw):
    """Returns (full_name, greeting_name, masked)."""
    text = re.sub(r"[^A-Za-z .]", " ", raw or "")
    parts = []
    for w in text.replace(".", " ").split():
        # mixed case: split on case change ("SatishKumar")
        parts += re.findall(r"[A-Z][a-z]+|[A-Z]+(?![a-z])|[a-z]+", w) if not w.isupper() else [w]
    words = []
    for n, part in enumerate(parts):
        last = n == len(parts) - 1
        m = re.match(r"^(.*?)(X{2,})$", part)
        if m and m.group(1) and part.isupper():
            words += _split_word(m.group(1)) + ["XXX"]
        else:
            words += _split_word(part, at_end=last)
    masked = any(_MASK.match(w.upper()) for w in words)
    words = [w.capitalize() for w in words if not _MASK.match(w.upper())]
    if not words:
        return "", "Customer", masked
    first = words[0]
    if first.upper() in _PREFIXES and len(words) > 1:
        first = f"{first} {words[1]}"
    if len(first) < 2:
        first = "Customer"
    return " ".join(words), first, masked


def check_row(row):
    """Adds cleaned fields and a list of problems for the review screen."""
    mobile = clean_mobile(row.get("mobile"))
    account = re.sub(r"\D", "", row.get("account") or "")
    full, greet, masked = clean_name(row.get("name"))
    problems = []
    no_mobile = not mobile
    if no_mobile:
        pass  # can't be messaged - shown as "call / visit", doesn't block the list
    elif not _MOBILE.match(mobile):
        problems.append("mobile not a valid 10-digit number")
    if not full:
        problems.append("name missing - type it from the paper")
    if not account:
        problems.append("account missing")
    elif len(account) != ACCOUNT_LEN:
        problems.append(f"account should be {ACCOUNT_LEN} digits")
    if row.get("low_confidence"):
        problems.append("text unclear in photo - please check")
    if row.get("unconfirmed"):
        problems.append("numbers unclear in photo - please match with the paper")
    return {
        "account": account,
        "mobile": mobile,
        "name": full,
        "greeting": greet,
        "name_masked": masked,
        "problems": problems,
        "no_mobile": no_mobile,
        "ok": not problems and not no_mobile,
    }


def check_rows(rows):
    checked = [check_row(r) for r in rows]
    seen_accounts = {}
    for i, r in enumerate(checked):
        if r["account"] and r["account"] in seen_accounts:
            r["problems"].append(f"duplicate of row {seen_accounts[r['account']] + 1}")
            r["ok"] = False
        seen_accounts.setdefault(r["account"], i)
    return checked


def group_by_mobile(rows):
    """One message per mobile number: [{"mobile", "greeting", "accounts_last4"}].
    Only rows marked ok are included."""
    groups = {}
    for r in rows:
        if not r["ok"]:
            continue
        g = groups.setdefault(r["mobile"], {"mobile": r["mobile"], "greetings": [],
                                            "accounts_last4": []})
        g["greetings"].append(r["greeting"])
        g["accounts_last4"].append(r["account"][-4:])
    out = []
    for g in groups.values():
        names = [n for n in dict.fromkeys(g["greetings"]) if n != "Customer"]
        out.append({
            "mobile": g["mobile"],
            "greeting": " / ".join(names) if names else "Customer",
            "accounts_last4": g["accounts_last4"],
        })
    return out
