"""All settings come from environment variables, loaded from .env if present.

Copy .env.example to .env and fill it in. Secrets (SECRET_KEY, OPTOUT_KEY, API
keys) live only in .env, which is never committed.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _path(name, default):
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else BASE_DIR / p


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        raise SystemExit(f"Setting {name} must be a whole number")


APP_ENV = os.getenv("APP_ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = _path("LOG_DIR", "logs")
DATA_DIR = _path("DATA_DIR", "data")

# DPDP storage limitation: lists are deleted from the CSP's phone this many days
# after upload (the server never stores lists).
RETENTION_DAYS = _int("RETENTION_DAYS", "30")
# The audit trail holds no names or full numbers and must outlive the lists it
# describes (DPDP Rules 2025: keep processing logs at least one year - confirm
# the period with compliance).
AUDIT_RETENTION_DAYS = _int("AUDIT_RETENTION_DAYS", "365")
# Login lock: after LOGIN_MAX_FAILED wrong passwords the account is locked for
# LOGIN_LOCKOUT_MINUTES. 0 switches the lock off (only sensible on a laptop).
LOGIN_MAX_FAILED = _int("LOGIN_MAX_FAILED", "5")
LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", "15")
# Give up reading a photo after this many seconds and ask for a clearer one
OCR_TIME_LIMIT = _int("OCR_TIME_LIMIT", "150")
# Reading engine: "local" (offline, on this server) or "voxomos" (Eko's in-house OCR
# service - DPDP clearance needed first, see docs/DATA_PROTECTION.md). If the
# service fails, the local engine reads the photo instead.
OCR_ENGINE = os.getenv("OCR_ENGINE", "local").strip().lower()
VOXOMOS_URL = os.getenv("VOXOMOS_URL", "").strip()
VOXOMOS_API_KEY = os.getenv("VOXOMOS_API_KEY", "").strip()
VOXOMOS_TIMEOUT = float(os.getenv("VOXOMOS_TIMEOUT", "120"))
# Rows whose OCR confidence is below this are flagged for the CSP to check.
OCR_MIN_CONFIDENCE = float(os.getenv("OCR_MIN_CONFIDENCE", "0.80"))

# Key for hashing opted-out mobiles. Never change after go-live.
OPTOUT_KEY = os.getenv("OPTOUT_KEY", "") or SECRET_KEY or "dev-only-optout-key"


# DPDP notice: who customers can contact with questions or complaints about
# their data (Eko's grievance officer / DPO). Shown in every message and on
# the privacy page. Must be filled in before go-live.
GRIEVANCE_CONTACT = os.getenv("GRIEVANCE_CONTACT", "").strip()

# The CSP's phone shows a reminder for a customer who hasn't come FOLLOWUP_DAYS
# after the message, at most MAX_FOLLOWUPS times. Messages go from the CSP's own
# WhatsApp, one tap per customer.
FOLLOWUP_DAYS = _int("FOLLOWUP_DAYS", "7")
MAX_FOLLOWUPS = _int("MAX_FOLLOWUPS", "1")
