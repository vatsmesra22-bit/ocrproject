"""Eko's in-house OCR service (Voxomos) as an optional reading engine.

Switched on with OCR_ENGINE=voxomos. The service returns the table directly as
records keyed by the list's own column titles, e.g.
    {"success": true, "records": [{"Account": "...", "Name": "...", "Mobile No": "..."}]}
Titles are mapped to account / mobile / name with the same title rules as the
local OCR, and only those three fields are kept (DPDP minimisation).

DPDP: with this engine the list photo leaves Eko's server and goes to Voxomos.
Use it only after compliance has confirmed: India hosting, no storage of the
photo or the result on Voxomos's side, and a data agreement (see
docs/DATA_PROTECTION.md). The API key lives only in .env (VOXOMOS_API_KEY).
"""
import logging
import re

import httpx

from app import config

log = logging.getLogger(__name__)


class VoxomosError(Exception):
    pass


def _field_for(title):
    from app.ocr_table import _header_matches
    fields = [f for f, _ in _header_matches(str(title), 0, 1)]
    for wanted in ("account", "mobile", "name", "_status"):
        if wanted in fields:
            return wanted
    return None


_MOBILE = re.compile(r"^(91)?[6-9]\d{9}$")


def _column_map(records):
    """Column title -> field. Titles first; columns whose titles are unknown are
    recognised by their values (11 digits = account, 10 digits from 6-9 = mobile,
    letters = name). Only titles are logged, never values (DPDP)."""
    titles = []
    for rec in records:
        for t in rec:
            if t not in titles:
                titles.append(t)
    log.info("Voxomos column titles: %s", titles)
    cmap, used = {}, set()
    for t in titles:
        f = _field_for(t)
        if f:
            cmap[t] = f
            used.add(f)

    def share(t, test):
        vals = [re.sub(r"\s", "", str(r.get(t) or "")) for r in records]
        vals = [v for v in vals if v]
        return sum(map(test, vals)) / len(vals) if len(vals) >= 2 else 0

    free = [t for t in titles if t not in cmap and _field_for(t) is None]
    if "mobile" not in used:
        for t in free:
            if share(t, lambda v: bool(_MOBILE.match(re.sub(r"\D", "", v)))) >= 0.6:
                cmap[t] = "mobile"; used.add("mobile"); free.remove(t)
                break
    if "account" not in used:
        for t in free:
            if share(t, lambda v: len(re.sub(r"\D", "", v)) == 11) >= 0.6:
                cmap[t] = "account"; used.add("account"); free.remove(t)
                break
    if "name" not in used:
        for t in free:
            if share(t, lambda v: len(v) >= 3 and sum(c.isalpha() for c in v) >= 0.8 * len(v)) >= 0.6:
                cmap[t] = "name"; used.add("name")
                break
    log.info("Voxomos columns used: %s", {f: t for t, f in cmap.items() if not f.startswith("_")})
    return cmap


def records_to_rows(records):
    """Voxomos records -> (rows, skipped_operative) in the local OCR's row shape."""
    rows, skipped = [], 0
    records = [r for r in records or [] if isinstance(r, dict)]
    cmap = _column_map(records) if records else {}
    for rec in records:
        picked = {}
        for title, value in rec.items():
            field = cmap.get(title)
            if field and field not in picked:
                picked[field] = "" if value is None else str(value).strip()
        status = picked.get("_status", "").upper()
        if status.startswith("OPER") and not status.startswith("INOP"):
            skipped += 1
            continue
        account = re.sub(r"\D", "", picked.get("account", ""))
        mobile = re.sub(r"\D", "", picked.get("mobile", ""))
        if not account and not mobile:
            continue  # blank / footer line
        rows.append({"account": account, "mobile": mobile,
                     "name": picked.get("name", ""), "low_confidence": False})
    return rows, skipped


def _content_type(filename, data):
    """The service only accepts images marked as such."""
    if data[1:4] == b"PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def extract(data, filename="list.jpg", client=None):
    """Photo bytes -> (rows, info). Raises VoxomosError on any service problem
    so the caller can fall back to the local OCR."""
    if not config.VOXOMOS_API_KEY or not config.VOXOMOS_URL:
        raise VoxomosError("VOXOMOS_URL / VOXOMOS_API_KEY are not set")
    own = client is None
    client = client or httpx.Client(timeout=config.VOXOMOS_TIMEOUT)
    try:
        resp = client.post(config.VOXOMOS_URL, headers={"X-API-Key": config.VOXOMOS_API_KEY},
                           files={"image": (filename, data, _content_type(filename, data))})
    except httpx.HTTPError as e:
        raise VoxomosError(f"service unreachable ({type(e).__name__})")
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise VoxomosError(f"service answered HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        raise VoxomosError("service sent something that is not JSON")
    if not body.get("success"):
        raise VoxomosError("service could not read the photo")
    rows, skipped = records_to_rows(body.get("records"))
    if not rows:
        raise VoxomosError("service found no customers")
    if body.get("saved_to"):
        # DPDP: the service kept a copy - logged (without the path) so it is visible
        log.warning("Voxomos reports it saved a copy of the result on its server")
    return rows, {"columns": ["account", "mobile", "name"], "skipped_operative": skipped,
                  "engine": "voxomos"}
