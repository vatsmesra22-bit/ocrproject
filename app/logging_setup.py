"""Logging to console and daily-rotated files in LOG_DIR:
  agent.log   everything that happens (INFO and up)
  errors.log  only problems (WARNING and up) - open this first after a crash
  audit.log   who did what (one JSON line per action)

Every log line passes through PiiMaskFilter, so a customer's account or mobile
number can never end up in a log file in full (DPDP: security safeguards).
Log the job id and counts; never log names.
"""
import json
import logging
import re
import sys
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from app import config

# 9+ digits = mobile (10), account/CIF (11), Aadhaar (12). Job ids and counts are shorter.
_LONG_NUMBER = re.compile(r"\d{9,}")


def mask_number(n):
    n = str(n)
    return "*" * max(len(n) - 4, 0) + n[-4:]


class PiiMaskFilter(logging.Filter):
    def filter(self, record):
        # Format first, then mask: masking the args separately would turn numbers
        # into text and break %d placeholders (e.g. uvicorn's status codes).
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = f"{record.msg} {record.args}"
        record.msg = _LONG_NUMBER.sub(lambda m: mask_number(m.group()), message)
        record.args = None
        if record.exc_info and not record.exc_text:
            # crash reports are masked too
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = _LONG_NUMBER.sub(lambda m: mask_number(m.group()), text)
        return True


_configured = False


def setup_logging():
    global _configured
    if _configured:
        return
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "agent.log", when="midnight", backupCount=config.RETENTION_DAYS,
        encoding="utf-8")
    # Only problems, kept longer, so a crash is easy to find
    error_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "errors.log", when="midnight", backupCount=max(config.RETENTION_DAYS, 90),
        encoding="utf-8")
    error_handler.setLevel(logging.WARNING)
    console = logging.StreamHandler()
    root = logging.getLogger()
    root.setLevel(config.LOG_LEVEL)
    for h in (file_handler, error_handler, console):
        h.setFormatter(fmt)
        h.addFilter(PiiMaskFilter())
        root.addHandler(h)
    # onnxruntime/rapidocr are chatty at INFO
    logging.getLogger("RapidOCR").setLevel(logging.WARNING)
    # Web server messages (incl. page crashes) go to the same files;
    # one line per page visit would only be noise, so those are left out.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Anything that crashes the whole program is written down before it stops
    def log_crash(exc_type, exc, tb):
        logging.getLogger("CRASH").critical("program stopped", exc_info=(exc_type, exc, tb))
    sys.excepthook = log_crash

    # Audit trail: one JSON line per agent action, kept separate from debug noise.
    audit_handler = TimedRotatingFileHandler(
        config.LOG_DIR / "audit.log", when="midnight", backupCount=config.AUDIT_RETENTION_DAYS,
        encoding="utf-8")
    audit_handler.setFormatter(logging.Formatter("%(message)s"))
    audit_handler.addFilter(PiiMaskFilter())
    audit_logger = logging.getLogger("audit")
    audit_logger.addHandler(audit_handler)
    _configured = True


def audit(event, job_id=None, csp_id=None, **details):
    """Record an agent action, e.g. audit("ocr_done", job_id, csp_id, rows=46).
    Details must be counts/ids only - never names or full numbers."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "event": event, "job_id": job_id, "csp_id": csp_id, **details}
    logging.getLogger("audit").info(json.dumps(entry, ensure_ascii=False))
