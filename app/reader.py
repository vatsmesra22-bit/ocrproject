"""Reads a list photo or Excel file in memory and hands the rows to the CSP's phone.

DPDP - nothing about a customer is ever saved on the server:
- the photo / file is never written to disk; it lives in memory only while it is
  being read and is dropped as soon as the reading is done;
- the rows wait in memory until the CSP's phone collects them (take()), then they
  are gone from the server; uncollected results are dropped after KEEP_SECONDS;
- the list itself is kept only on the CSP's phone (see templates/csp.html).

Photos are read one at a time: two readings at once share the CPU and both get
slow. A waiting photo shows its place in the line (status()).
"""
import logging
import secrets
import threading
import time
from pathlib import Path

from app.logging_setup import audit
from app.ocr_table import extract_rows

log = logging.getLogger(__name__)

ALLOWED_PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_SHEET_BYTES = 5 * 1024 * 1024
KEEP_SECONDS = 15 * 60  # a result nobody collected is dropped after this


class ReadError(Exception):
    pass


_tasks = {}                    # token -> task (memory only)
_tasks_lock = threading.Lock()
_reading = threading.Lock()    # one photo at a time


def _check_photo(data, filename):
    if Path(filename or "").suffix.lower() not in ALLOWED_PHOTO_TYPES:
        raise ReadError("Please upload a photo (JPG or PNG)")
    if not data:
        raise ReadError("The uploaded file is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise ReadError("Photo is too large (max 15 MB)")


def _drop_old():
    now = time.monotonic()
    with _tasks_lock:
        for token in [t for t, task in _tasks.items() if now - task["at"] > KEEP_SECONDS]:
            del _tasks[token]


def start(csp_id, data, filename):
    """Queue a photo for reading. Returns a token the phone uses to ask for the result."""
    _check_photo(data, filename)
    _drop_old()
    token = secrets.token_urlsafe(16)
    task = {"csp": csp_id, "stage": "waiting", "at": time.monotonic(), "photo": data,
            "rows": None, "info": None, "error": None}
    with _tasks_lock:
        _tasks[token] = task
    audit("list_uploaded", csp_id=csp_id, bytes=len(data))
    threading.Thread(target=_read, args=(token,), daemon=True).start()
    return token


def _read(token):
    with _reading:
        with _tasks_lock:
            task = _tasks.get(token)
            if task is None:
                return  # cancelled while waiting
            task["stage"] = "reading"
            photo = task.pop("photo")
        started = time.monotonic()
        try:
            rows, info = extract_rows(photo)
        except Exception as e:  # OCR engine crash, unreadable image
            log.exception("reading a photo crashed")
            rows, info = [], {"error": f"Could not read the photo ({type(e).__name__})"}
        finally:
            del photo  # DPDP: the photo is gone once read
        seconds = round(time.monotonic() - started, 1)
        error = None
        if info.get("error"):
            error = info["error"] + ". Please retake the photo with the column titles visible."
        elif not rows:
            error = "No customer rows found. Please retake the photo flat and in good light."
        with _tasks_lock:
            if token not in _tasks:
                return
            task.update(stage="failed" if error else "done", error=error, at=time.monotonic(),
                        rows=None if error else rows, info=info)
        audit("list_read", csp_id=task["csp"], seconds=seconds,
              rows=0 if error else len(rows), failed=bool(error))


def status(token, csp_id):
    """{stage, ahead, error} - no customer data."""
    with _tasks_lock:
        task = _tasks.get(token)
        if task is None or task["csp"] != csp_id:
            return {"stage": "gone", "ahead": 0, "error": "This reading has expired - please upload again"}
        ahead = 0
        if task["stage"] == "waiting":
            ahead = sum(1 for t in _tasks.values()
                        if t["stage"] in ("waiting", "reading") and t["at"] < task["at"])
        return {"stage": task["stage"], "ahead": ahead, "error": task["error"]}


def take(token, csp_id):
    """The phone collects the rows: they leave the server's memory for good."""
    with _tasks_lock:
        task = _tasks.get(token)
        if task is None or task["csp"] != csp_id or task["stage"] != "done":
            return None
        del _tasks[token]
    return task["rows"], {"skipped_operative": task["info"].get("skipped_operative", 0)}


def cancel(token, csp_id):
    with _tasks_lock:
        task = _tasks.get(token)
        if task is not None and task["csp"] == csp_id:
            del _tasks[token]


def read_sheet(csp_id, data, filename):
    """Excel / CSV list: read the cells directly (no OCR), in memory."""
    from app.sheet_list import SheetError, read_customer_sheet
    if not data:
        raise ReadError("The uploaded file is empty")
    if len(data) > MAX_SHEET_BYTES:
        raise ReadError("File is too large (max 5 MB)")
    try:
        rows, info = read_customer_sheet(filename or "", data)
    except SheetError as e:
        raise ReadError(str(e))
    if not rows:
        raise ReadError("No customer rows found in the file")
    audit("list_read", csp_id=csp_id, rows=len(rows), source="sheet")
    return rows, {"skipped_operative": info.get("skipped_operative", 0), "source": "sheet"}
