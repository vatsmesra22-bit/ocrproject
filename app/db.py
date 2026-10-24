"""SQLite database (DATA_DIR/app.db): logins, list counts, opt-outs.

No customer list, name, account or mobile number is stored here (DPDP). Lists live
only on the CSP's phone. The tables hold:
- users: CSP and super admin logins
- list_stats: counts per list, sent by the CSP's phone (how many customers,
  messages sent, came...) - numbers only, for the super admin's dashboard
- earlier_totals: totals of work done before lists moved to the phones (23 Oct
  2026) - numbers only, so the dashboard keeps counting earlier work
- optouts: keyed HMAC of the mobile of each customer who said STOP, so no CSP
  messages that number again; the number cannot be read back from it
"""
import hashlib
import hmac
import sqlite3
from contextlib import contextmanager

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    csp_code        TEXT PRIMARY KEY,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'csp')),
    name            TEXT NOT NULL,
    address         TEXT NOT NULL DEFAULT '',
    mobile          TEXT NOT NULL DEFAULT '',
    branch          TEXT NOT NULL DEFAULT '',
    pw_hash         TEXT NOT NULL,
    must_change     INTEGER NOT NULL DEFAULT 1,
    active          INTEGER NOT NULL DEFAULT 1,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    last_login      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS list_stats (
    csp_id      TEXT NOT NULL,
    list_id     TEXT NOT NULL,      -- random id made by the phone
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    pages       INTEGER NOT NULL DEFAULT 1,
    customers   INTEGER NOT NULL DEFAULT 0,
    to_fix      INTEGER NOT NULL DEFAULT 0,
    no_mobile   INTEGER NOT NULL DEFAULT 0,
    messages    INTEGER NOT NULL DEFAULT 0,
    sent        INTEGER NOT NULL DEFAULT 0,   -- confirmed by the CSP
    not_on_wa   INTEGER NOT NULL DEFAULT 0,
    stopped     INTEGER NOT NULL DEFAULT 0,
    came        INTEGER NOT NULL DEFAULT 0,
    reminders   INTEGER NOT NULL DEFAULT 0,
    repeat      INTEGER NOT NULL DEFAULT 0,   -- same list uploaded again on that phone
    deleted     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (csp_id, list_id)
);

CREATE TABLE IF NOT EXISTS earlier_totals (
    label       TEXT PRIMARY KEY,
    lists       INTEGER NOT NULL DEFAULT 0,
    repeats     INTEGER NOT NULL DEFAULT 0,   -- of those lists, the same list again
    unread      INTEGER NOT NULL DEFAULT 0,   -- uploads that could not be read
    customers   INTEGER NOT NULL DEFAULT 0,
    sent        INTEGER NOT NULL DEFAULT 0,
    came        INTEGER NOT NULL DEFAULT 0,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS optouts (
    mobile_key  TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL
);

-- older versions kept one row per message here; lists are no longer on the server
DROP TABLE IF EXISTS sends;
"""

_ready = set()  # database files whose tables exist


@contextmanager
def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = config.DATA_DIR / "app.db"
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    if path not in _ready:
        conn.executescript(SCHEMA)
        _ready.add(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect():
        pass  # connect() creates the tables


def mobile_key(mobile):
    """Keyed hash of a 10-digit mobile. OPTOUT_KEY must never change after
    go-live, or earlier opt-outs stop matching."""
    return hmac.new(config.OPTOUT_KEY.encode(), mobile.encode(), hashlib.sha256).hexdigest()
