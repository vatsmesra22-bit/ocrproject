"""Counts for the super admin, and the STOP list. Never customer data.

The CSP's phone keeps the list; after every change it sends only the numbers
(how many customers, sent, came...) for that list. The dashboard and the Excel
report add these up. Every list read is counted as a list tested; a list the
phone marked as the same list again is shown separately and its customers are
not added again. A deleted list is not counted at all.
"""
from datetime import datetime, timezone

from app import db

FIELDS = ("pages", "customers", "to_fix", "no_mobile", "messages", "sent", "not_on_wa",
          "stopped", "came", "reminders", "repeat", "deleted")
COUNTED = ("customers", "messages", "sent", "not_on_wa", "stopped", "came", "reminders")


class StatsError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_id(list_id):
    list_id = str(list_id or "")
    if not (8 <= len(list_id) <= 40) or not all(c.isalnum() or c == "-" for c in list_id):
        raise StatsError("Invalid list id")
    return list_id


def record_list(csp_id, list_id, counts):
    """Save the latest counts of one list (sent by the phone)."""
    list_id = _clean_id(list_id)
    values = {}
    for f in FIELDS:
        try:
            values[f] = max(0, min(100000, int(counts.get(f, 0) or 0)))
        except (TypeError, ValueError):
            raise StatsError(f"Bad number for {f}")
    now = _now()
    with db.connect() as conn:
        conn.execute(
            f"INSERT INTO list_stats (csp_id, list_id, created_at, updated_at, {', '.join(FIELDS)})"
            f" VALUES (?, ?, ?, ?, {', '.join('?' for _ in FIELDS)})"
            f" ON CONFLICT (csp_id, list_id) DO UPDATE SET updated_at = excluded.updated_at, "
            + ", ".join(f"{f} = excluded.{f}" for f in FIELDS),
            (csp_id, list_id, now, now, *values.values()))


def per_csp():
    """{csp_id: {lists (all tested), repeats (of those, same list again), customers...}}"""
    out = {}
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM list_stats WHERE deleted = 0").fetchall()
    for r in rows:
        p = out.setdefault(r["csp_id"], {"lists": 0, "repeats": 0, "last_list": "",
                                         **{f: 0 for f in COUNTED}})
        p["last_list"] = max(p["last_list"], r["created_at"])
        p["lists"] += 1
        if r["repeat"]:
            p["repeats"] += 1
            for f in ("sent", "not_on_wa", "stopped", "came", "reminders"):
                p[f] += r[f]   # real actions on the repeat still happened
            continue
        for f in COUNTED:
            p[f] += r[f]
    return out


def earlier():
    """Totals of earlier work (before lists moved to the phones) - numbers only."""
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM earlier_totals ORDER BY added_at")]


def add_earlier(label, **numbers):
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO earlier_totals (label, lists, repeats, unread, customers, sent,"
                     " came, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (label, *(int(numbers.get(k, 0)) for k in ("lists", "repeats", "unread", "customers",
                                                                "sent", "came")), _now()))


def totals():
    """Dashboard totals: every CSP's lists plus earlier work."""
    total = {"lists": 0, "repeats": 0, "unread": 0, **{f: 0 for f in COUNTED}}
    for p in per_csp().values():
        for k in p:
            if k in total:
                total[k] += p[k]
    for e in earlier():
        for k in ("lists", "repeats", "unread", "customers", "sent", "came"):
            total[k] += e[k]
    return total


# ---------- STOP list ----------

def clean_mobile(raw):
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def add_optout(mobile):
    mobile = clean_mobile(mobile)
    if len(mobile) != 10:
        raise StatsError("Enter the customer's 10-digit mobile number")
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO optouts (mobile_key, created_at) VALUES (?, ?)",
                     (db.mobile_key(mobile), _now()))


def opted_out(mobiles):
    """Which of these mobiles said STOP before (to any CSP)."""
    keys = {db.mobile_key(m): m for m in {clean_mobile(m) for m in mobiles} if len(m) == 10}
    if not keys:
        return set()
    with db.connect() as conn:
        found = conn.execute(
            f"SELECT mobile_key FROM optouts WHERE mobile_key IN ({', '.join('?' for _ in keys)})",
            list(keys)).fetchall()
    return {keys[r["mobile_key"]] for r in found}
