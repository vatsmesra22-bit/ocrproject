"""Turn a photo of a printed inoperative-account list into rows.

Pipeline: photo quality check -> offline OCR (RapidOCR, PaddleOCR models) ->
straighten a tilted photo -> split merged text boxes into tokens -> find the
header row -> group tokens into rows while allowing for a curled page -> pick
account, mobile and name for each row -> read the photo a second time
(enhanced) and flag every row whose numbers differ between the two readings.

Why the second reading: on a poor photo the OCR can misread one middle digit
with high confidence, and the number still "looks valid" (right length,
starts 6-9). Two independent readings rarely make the same mistake, so a
disagreement is the signal that a human must check that row.

Only the fields needed for the reactivation message are returned (DPDP data
minimisation): CIF, father's name, address etc. are read by the OCR engine but
never leave this module.
"""
import io
import logging
import math
import re
import threading
import time
from statistics import median

import cv2
import numpy as np

from app import config

# Header spellings seen on SBI/BC lists, normalised to A-Z0-9 only.
# Columns we don't use are still listed so merged header boxes split cleanly.
HEADER_KEYWORDS = {
    "account": ["MEMBCUSTAC", "ACCOUNTNUMBER", "ACCOUNTNBR", "ACCOUNTNUM", "ACCOUNTNO", "ACNUMBER",
                "ACCTNO", "ACCNO", "ACNO", "CUSTAC", "ACCOUNT"],
    "mobile": ["MOBILENBR", "MOBILENO", "MOBILENUMBER", "MOBNO", "MOBILE", "CONTACTNO", "PHONENO"],
    "name": ["CUSTOMERNAME", "CUSTNAME", "NAME1", "NAMEL", "NAMEI", "NAME"],
    "_cif": ["CIFNO", "CIF"],
    "_father": ["FTHRNM", "FATHERNAME", "FTHRNAME"],
    "_bc": ["BCNAME"],
    "_csp": ["CSPNAME", "CSPCODE"],
    # "Operative/Inoperative" column: only INOPERATIVE customers are kept
    "_status": ["OPERATIVEINOPERATIVE", "ACCOUNTSTATUS", "ACSTATUS", "OPERATIVE", "STATUS"],
    "_other": ["REGION", "BRANCHNO", "BRANCH", "ADDRESS", "ADDR", "PRODUCTCODE", "ACCOUNTOPEN",
               "OPENDATE", "GENDER", "DATEOFBIRTH", "DOB", "AGENTCODE", "BCCODE"],
}
_KEYWORDS = sorted(
    ((kw, field) for field, kws in HEADER_KEYWORDS.items() for kw in kws),
    key=lambda kf: -len(kf[0]),
)

_ocr_engine = None
_ocr_lock = threading.Lock()  # one photo at a time: keeps memory use predictable


def _engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def run_ocr(image):
    """image: file path, bytes, or numpy array. Returns [(polygon, text, conf)]."""
    with _ocr_lock:
        started = time.monotonic()
        result, _ = _engine()(image)
        shape = getattr(image, "shape", None)
        logging.getLogger(__name__).info("ocr pass %s took %.1f s", shape[:2] if shape else "-",
                                         time.monotonic() - started)
    return result or []


class Token:
    __slots__ = ("text", "kind", "x", "cx", "cy", "slope", "conf")

    def __init__(self, text, kind, x, cx, cy, slope, conf):
        self.text, self.kind, self.x, self.cx, self.cy = text, kind, x, cx, cy
        self.slope, self.conf = slope, conf


def _box_geometry(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    (x0, y0), (x1, y1) = poly[0], poly[1]
    slope = (y1 - y0) / (x1 - x0) if x1 - x0 > 1 else 0.0
    return min(xs), max(xs), sum(ys) / 4, max(ys) - min(ys), slope


def _split_box(text, x0, x1, cy, slope, conf):
    """'91482064354Ratneshwari Si' -> digit token + letter token, each with an
    x position estimated from its character offset inside the box."""
    n = max(len(text), 1)
    width = x1 - x0
    tokens = []
    # Letters are split into single words so a name that runs into the next
    # column ("MOHAMMAD MOHSIN MOHAMMAD ZIYAUL") can be divided by position.
    for m in re.finditer(r"\d+|[A-Za-z][A-Za-z.'-]*", text):
        kind = "digits" if m.group()[0].isdigit() else "letters"
        tx = x0 + width * m.start() / n
        tcx = x0 + width * (m.start() + m.end()) / 2 / n
        tokens.append(Token(m.group().strip(), kind, tx, tcx, cy, slope, conf))
    return tokens


# Letters OCR mixes up in printed titles ("M0bile", "Mobi1e", "Acc0unt"): both the
# title and the known spellings are folded the same way before comparing.
_FOLD = str.maketrans({"0": "O", "1": "I", "L": "I", "5": "S", "8": "B", "Q": "O"})


def _header_matches(text, x0, x1):
    """Find header keywords inside one (possibly merged) header box."""
    norm, index = [], []
    for i, ch in enumerate(text.upper()):
        if ch.isalnum():
            norm.append(ch)
            index.append(i)
    norm = "".join(norm).translate(_FOLD)
    n = max(len(text), 1)
    found, i = [], 0
    while i < len(norm):
        for kw, field in _KEYWORDS:
            if norm.startswith(kw.translate(_FOLD), i):
                found.append((field, x0 + (x1 - x0) * index[i] / n))
                i += len(kw)
                break
        else:
            i += 1
    return found


def _trace_lines(boxes, line_h, page_w):
    """Chain boxes left-to-right into text lines.

    A photographed page is curved, so a row is not a straight line: the left
    column may tilt up while the right column tilts down. Each box's own tilt
    predicts where its line continues, so we link every box to the box on its
    right whose left edge sits where that prediction lands.
    """
    def y_at(b, x):
        return b["cy"] + b["slope"] * (x - (b["x0"] + b["x1"]) / 2)

    links = []
    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes):
            gap = b["x0"] - a["x1"]
            if (b["x0"] + b["x1"]) <= (a["x0"] + a["x1"]) or gap < -line_h * 0.5 \
                    or gap > page_w * 0.4:
                continue
            # Meet in the middle of the gap, each side extrapolating its own tilt.
            mid = (a["x1"] + b["x0"]) / 2
            dy = abs(y_at(a, mid) - y_at(b, mid))
            if dy < line_h * 0.6:
                links.append((dy + gap * 0.01, i, j))
    links.sort()
    nxt, prv = {}, {}
    for _, i, j in links:
        if i not in nxt and j not in prv:
            nxt[i], prv[j] = j, i
    lines = []
    for i in range(len(boxes)):
        if i in prv:
            continue
        chain, k = [], i
        while k is not None:
            chain.append(boxes[k])
            k = nxt.get(k)
        lines.append(chain)
    lines.sort(key=lambda ch: ch[0]["cy"])
    return lines


def parse_table(ocr_result):
    """Returns (rows, info). Each row: {"account", "mobile", "name"} (strings,
    possibly empty when unreadable) - nothing else from the sheet."""
    boxes = []
    for poly, text, conf in ocr_result:
        x0, x1, cy, h, slope = _box_geometry(poly)
        boxes.append({"poly": poly, "text": text, "conf": conf, "x0": x0, "x1": x1,
                      "cy": cy, "h": h, "w": x1 - x0, "slope": slope})
    if not boxes:
        return [], {"error": "No text found in the photo"}

    line_h = median(b["h"] for b in boxes)
    page_w = max(b["x1"] for b in boxes) - min(b["x0"] for b in boxes)

    # 1. Header: the column titles around the topmost MOBILE title.
    def is_data(b):
        return re.search(r"\d{6}", b["text"]) is not None

    mobile_boxes = [b for b in boxes if not is_data(b) and any(
        f == "mobile" for f, _ in _header_matches(b["text"], b["x0"], b["x1"]))]
    if mobile_boxes:
        top = min(mobile_boxes, key=lambda b: b["cy"])

        def in_title_band(b):
            return abs(b["cy"] - top["cy"]) <= line_h * 2
    else:
        # no MOBILE title: start at the first line that holds numbers
        data_boxes = [b for b in boxes if is_data(b)]
        if not data_boxes:
            return [], {"error": "Could not find the MOBILE column header"}
        first = min(data_boxes, key=lambda b: b["cy"])
        top = {"cy": first["cy"] - line_h}

        def in_title_band(b):  # only above the first row of numbers
            return first["cy"] - line_h * 3 <= b["cy"] < first["cy"] - line_h * 0.5
    # For each column keep only the topmost match: a value such as "OPERATIVE"
    # in the first data row must not be mistaken for the column title.
    best = {}  # field -> (cy, x, box id)
    for b in boxes:
        if is_data(b) or not in_title_band(b):
            continue
        for field, hx in _header_matches(b["text"], b["x0"], b["x1"]):
            if field not in best or b["cy"] < best[field][0]:
                best[field] = (b["cy"], hx, id(b))
    header = {f: v[1] for f, v in best.items()}
    header_ids = {v[2] for v in best.values()}
    inferred = _infer_number_columns(boxes, top["cy"], page_w, header)
    header.update(inferred)
    missing = [f for f in ("account", "mobile") if f not in header]
    if missing:
        return [], {"error": "Missing column header(s): " + ", ".join(m.upper() for m in missing)}
    if "name" not in header:
        header["_noname"] = -10 ** 6   # no NAME column: greet as "Customer"

    # 2. Trace each printed row across the (possibly curved) page.
    body = [b for b in boxes if id(b) not in header_ids]
    lines = _trace_lines(body, line_h, page_w)

    # 3. Pick the fields per row by nearest column title of the right kind.
    digit_cols = {f: x for f, x in header.items() if f in ("account", "mobile", "_cif")}
    letter_cols = {f: x for f, x in header.items()
                   if f in ("name", "_father", "_bc", "_csp", "_other", "_status", "_noname")}
    skipped_operative = 0

    rows = []
    for line in lines:
        if not any(is_data(b) for b in line) or max(b["cy"] for b in line) < top["cy"]:
            continue  # title text, page edge, pen marks
        picked = {"account": None, "mobile": None}
        name_words, confs, status_words = [], [], []
        for b in line:
            for t in _split_box(b["text"], b["x0"], b["x1"], b["cy"], b["slope"], b["conf"]):
                if t.kind == "digits":
                    if len(t.text) < 9:
                        continue  # dates, branch / product / agent codes, serial numbers
                    field = min(digit_cols, key=lambda f: abs(digit_cols[f] - t.x))
                    prev = picked.get(field)
                    if field in picked and (prev is None or
                                            abs(header[field] - t.x) < abs(header[field] - prev.x)):
                        picked[field] = t
                else:
                    field = min(letter_cols, key=lambda f: abs(letter_cols[f] - t.x))
                    if field == "name":
                        name_words.append(t)
                    elif field == "_status":
                        status_words.append(t.text.upper())
        if picked["account"] is None and picked["mobile"] is None:
            continue
        # The bank's list can mix operative and inoperative accounts: only the
        # inoperative ones are customers to contact (and the only ones kept - DPDP).
        if any(w.startswith("OPER") for w in status_words) and \
                not any(w.startswith("INOP") for w in status_words):
            skipped_operative += 1
            continue
        name_words.sort(key=lambda t: t.x)
        used = [t for t in picked.values() if t] + name_words
        rows.append({
            "account": picked["account"].text if picked["account"] else "",
            "mobile": picked["mobile"].text if picked["mobile"] else "",
            "name": " ".join(t.text for t in name_words),
            "low_confidence": any(t.conf < config.OCR_MIN_CONFIDENCE for t in used),
        })
    return rows, {"columns": sorted(f for f in header if not f.startswith("_")),
                  "skipped_operative": skipped_operative, "inferred": sorted(inferred)}


def _infer_number_columns(boxes, top_cy, page_w, header):
    """Columns whose titles weren't found, recognised by their numbers:
    mobile = column of 10-digit numbers starting 6-9; account = leftmost other
    column of 11-digit numbers. Only used for titles that are missing."""
    want = [f for f in ("mobile", "account") if f not in header]
    if not want:
        return {}
    toks = []
    for b in boxes:
        if b["cy"] <= top_cy:
            continue
        for t in _split_box(b["text"], b["x0"], b["x1"], b["cy"], b["slope"], b["conf"]):
            if t.kind == "digits" and 9 <= len(t.text) <= 12:
                toks.append(t)
    if len(toks) < 3:
        return {}
    toks.sort(key=lambda t: t.x)
    clusters, cur = [], [toks[0]]
    for t in toks[1:]:
        if t.x - cur[-1].x > page_w * 0.05:
            clusters.append(cur)
            cur = []
        cur.append(t)
    clusters.append(cur)
    clusters = [c for c in clusters if len(c) >= 3]
    found = {}
    taken = {header.get("mobile"), header.get("account")}

    def x_of(c):
        return median(t.x for t in c)

    if "mobile" in want:
        mob = [c for c in clusters
               if sum(bool(_MOBILE_LIKE.match(t.text)) for t in c) >= 0.6 * len(c)]
        if mob:
            best = max(mob, key=len)
            found["mobile"] = x_of(best)
            clusters = [c for c in clusters if c is not best]
    if "account" in want:
        acc = [c for c in clusters if sum(len(t.text) == 11 for t in c) >= 0.6 * len(c)
               and x_of(c) not in taken]
        if acc:
            found["account"] = x_of(min(acc, key=x_of))
    return found


_MOBILE_LIKE = re.compile(r"^(91)?[6-9]\d{9}$")


# Photo quality limits, measured on real sample lists (see docs/WORKLOG.md).
MIN_SHORT_SIDE = 700      # pixels; WhatsApp-forwarded photos are ~900
MIN_SHARPNESS = 120       # variance of Laplacian; a shaky photo scores < 120
MIN_BRIGHTNESS = 60       # mean grey level 0-255
MIN_JPEG_QUALITY = 55     # below ~50 the OCR misread digits that still looked valid
STRAIGHTEN_ABOVE = 2.0    # degrees of tilt before the photo is rotated
MAX_SIDE = 2200           # bigger phone photos are shrunk first: same accuracy, much faster
PROBE_SIDE = 1100         # small copy used to find which way round the photo is
UNCLEAR = ("Photo is not clear enough to read. Please take it again: paper flat, "
           "good light, column names visible")


def load_image(image):
    """File path (any characters), bytes, or array -> BGR array, or None."""
    if isinstance(image, np.ndarray):
        return image
    if isinstance(image, (bytes, bytearray)):
        data = np.frombuffer(image, np.uint8)
    else:
        try:
            data = np.fromfile(str(image), np.uint8)  # cv2.imread fails on non-ASCII paths
        except OSError:
            return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def jpeg_quality(data):
    """Estimated JPEG quality (1-100) from the file's quantisation table, or None."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            tables = getattr(im, "quantization", None)
    except Exception:
        return None
    if not tables or 0 not in tables:
        return None
    scale = sum(tables[0]) / len(tables[0]) / 57.625 * 100  # IJG table average at q=50
    return (200 - scale) / 2 if scale <= 100 else 5000 / scale


def photo_problem(img, data=None):
    """A message for the CSP if the photo is too poor to read safely, else None.
    data: the original file bytes, to check JPEG compression."""
    if data is not None:
        q = jpeg_quality(data)
        if q is not None and q < MIN_JPEG_QUALITY:
            return ("Photo is too compressed (probably forwarded on WhatsApp). Please take "
                    "the photo directly with the phone camera.")
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if min(grey.shape) < MIN_SHORT_SIDE:
        return ("Photo is too small / low quality. Please take the photo again with the "
                "phone camera (not a screenshot or forwarded photo).")
    if grey.mean() < MIN_BRIGHTNESS:
        return "Photo is too dark. Please take it again in good light."
    if grey.std() < 12:
        return "No list found in the photo. Please take a photo of the printed list."
    # Measure sharpness at a fixed size: a big phone photo spreads each edge over
    # more pixels and would otherwise look "blurry" just for being big.
    if cv2.Laplacian(_shrink(grey, 1000), cv2.CV_64F).var() < MIN_SHARPNESS:
        return "Photo is blurry. Please hold the phone still and take it again."
    return None


def _tilt_degrees(raw):
    slopes = []
    for poly, _, _ in raw:
        (x0, y0), (x1, y1) = poly[0], poly[1]
        if x1 - x0 > 60:
            slopes.append((y1 - y0) / (x1 - x0))
    return math.degrees(math.atan(median(slopes))) if len(slopes) >= 5 else 0.0


def _rotate(img, degrees):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def _shrink(img, side):
    h, w = img.shape[:2]
    if max(h, w) <= side:
        return img
    f = side / max(h, w)
    return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)


def _grow(img, factor):
    # never grow past ~1.2 x MAX_SIDE: big images make OCR slow without helping
    factor = min(factor, MAX_SIDE * 1.2 / max(img.shape[:2]))
    if factor <= 1.0:
        return img
    return cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def _upscaled(img):
    return _grow(img, 1.25)


def _enhanced(img):
    """A differently processed copy for the second reading: contrast-
    normalised and sharpened, so OCR mistakes don't repeat identically."""
    big = img  # same size as the first reading: half the work, still a different image
    lab = cv2.cvtColor(big, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    big = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(big, (0, 0), 2)
    return cv2.addWeighted(big, 1.5, blur, -0.5, 0)


def extract_rows(image, time_limit=None):
    """Photo -> (rows, info). info has "error" when the photo can't be used.
    Gives up with a clear "photo not clear" message after time_limit seconds
    (default config.OCR_TIME_LIMIT) instead of keeping the CSP waiting."""
    started = time.monotonic()
    limit = config.OCR_TIME_LIMIT if time_limit is None else time_limit

    def over():
        return time.monotonic() - started > limit

    data = None
    if isinstance(image, (bytes, bytearray)):
        data = bytes(image)
    elif not isinstance(image, np.ndarray):
        try:
            data = open(image, "rb").read()
        except OSError:
            data = None
    img = load_image(data if data is not None else image)
    if img is None:
        return [], {"error": "Could not open the photo. Please upload a JPG or PNG photo"}
    problem = photo_problem(img, data)
    if problem:
        return [], {"error": problem.rstrip(".")}
    if config.OCR_ENGINE == "voxomos":
        from app import ocr_voxomos
        try:
            payload = data if data is not None else cv2.imencode(".jpg", img)[1].tobytes()
            return ocr_voxomos.extract(payload)
        except ocr_voxomos.VoxomosError as e:
            logging.getLogger(__name__).warning("Voxomos OCR failed (%s) - reading locally", e)
    img = _shrink(img, MAX_SIDE)

    def read(image):
        raw = run_ocr(image)
        tilt = _tilt_degrees(raw)
        if abs(tilt) > STRAIGHTEN_ABOVE:
            image = _rotate(image, tilt)
            raw = run_ocr(image)
        rows, info = parse_table(raw)
        info["tilt"] = round(tilt, 1)
        return image, rows, info

    found, rows, info = read(img)
    if info.get("error") or not rows:
        # Photo taken sideways or upside down: find the right way round on a
        # small copy (fast), then read the full photo only in that direction.
        small = _shrink(img, PROBE_SIDE)
        for turn in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180):
            if over():
                return [], {"error": UNCLEAR}
            p_rows, p_info = parse_table(run_ocr(cv2.rotate(small, turn)))
            if not p_info.get("error") and p_rows:
                found, rows, info = read(cv2.rotate(img, turn))
                break
    if info.get("error") or not rows:
        # nothing readable in any direction: almost always an unclear photo
        # Say what is really wrong: a missing column title is not an "unclear photo"
        err = info.get("error") or ""
        if err.startswith("Missing column") or err.startswith("Could not find the MOBILE"):
            return rows, {**info, "error": err + " - make sure the row of column titles is in the photo"}
        return rows, {**info, "error": UNCLEAR}
    img = found
    if over():
        # read once but no time left for the check reading: flag everything
        for r in rows:
            r["unconfirmed"] = True
        info.update(unconfirmed=len(rows))
        return rows, info

    # Second, independent reading. If one style of processing can't read the
    # sheet at all, try the next; only if all fail is every row left unconfirmed.
    pairs = set()
    for variant in (_enhanced, _upscaled):
        second, info2 = parse_table(run_ocr(variant(img)))
        if not info2.get("error") and len(second) >= len(rows) // 2:
            pairs = {(r["account"], r["mobile"]) for r in second}
            break
    unconfirmed = 0
    for r in rows:
        if (r["account"], r["mobile"]) not in pairs:
            r["unconfirmed"] = True
            unconfirmed += 1
    info.update(unconfirmed=unconfirmed)
    return rows, info
