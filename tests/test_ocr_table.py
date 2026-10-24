"""Parser tests on hand-built OCR boxes (no real customer data, no OCR engine)."""
from app.ocr_table import parse_table


def box(x0, y, text, w=None, h=30, slope=0.0, conf=0.99):
    w = w or len(text) * 12
    dy = slope * w
    return [[[x0, y], [x0 + w, y + dy], [x0 + w, y + dy + h], [x0, y + h]], text, conf]


def test_flat_table_with_merged_boxes():
    ocr = [
        box(100, 10, "AcNo"), box(260, 10, "CIFNo"), box(420, 10, "Name1"),
        box(620, 10, "MobileNo"),
        # account alone, CIF merged with the name, mobile alone
        box(100, 50, "11111111111"), box(260, 50, "22222222222 Sita Devi", w=300),
        box(620, 50, "9876543210"),
        box(100, 90, "33333333333"), box(260, 90, "44444444444Ram Kumar", w=300),
        box(620, 90, "8765432109"),
    ]
    rows, info = parse_table(ocr)
    assert "error" not in info
    assert [(r["account"], r["mobile"], r["name"]) for r in rows] == [
        ("11111111111", "9876543210", "Sita Devi"),
        ("33333333333", "8765432109", "Ram Kumar"),
    ]


def test_curved_rows_are_followed():
    # Left column tilts up, right column tilts down: the mobile of row 1 sits
    # almost a full row lower than its account number.
    ocr = [box(100, 0, "AcNo"), box(300, 10, "Name"), box(560, 20, "MOBILE_NBR")]
    for i in range(4):
        y = 60 + i * 40
        ocr += [
            box(100, y + 6, f"1111111111{i}", w=140, slope=-0.05),
            box(260, y + 4, f"NAME{i}", w=200, slope=0.08),
            box(470, y + 24, f"98765432{i}0", w=130, slope=0.14),
        ]
    rows, _ = parse_table(ocr)
    assert [(r["account"][-1], r["mobile"][-2]) for r in rows] == [
        ("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")]


def test_other_columns_are_not_returned():
    ocr = [box(100, 10, "MEMB_CUST_ACNAME", w=300), box(500, 10, "FTHR_NM"),
           box(700, 10, "MOBILE_NBR"),
           box(100, 50, "11111111111"), box(260, 50, "SITA DEVI"),
           box(500, 50, "RAM LAL"), box(700, 50, "9876543210")]
    rows, _ = parse_table(ocr)
    assert rows == [{"account": "11111111111", "mobile": "9876543210",
                     "name": "SITA DEVI", "low_confidence": False}]


def test_missing_mobile_header_is_reported():
    rows, info = parse_table([box(100, 10, "AcNo"), box(100, 50, "11111111111")])
    assert rows == [] and "MOBILE" in info["error"]



def test_operative_rows_are_dropped_and_codes_ignored():
    ocr = [box(100, 10, "AcNo"), box(300, 10, "Name"), box(450, 10, "Product Code", w=140),
           box(620, 10, "Operative"), box(800, 10, "MobileNo"),
           box(100, 50, "11111111111"), box(300, 50, "SITA DEVI"), box(450, 50, "10111701"),
           box(620, 50, "OPERATIVE"), box(800, 50, "9876543210"),
           box(100, 90, "22222222222"), box(300, 90, "RAM LAL"), box(450, 90, "10111701"),
           box(620, 90, "INOPERATIVE"), box(800, 90, "9876543211")]
    rows, info = parse_table(ocr)
    assert [r["account"] for r in rows] == ["22222222222"]   # only the inoperative customer
    assert info["skipped_operative"] == 1



def test_plain_account_title_and_honest_error():
    ocr = [box(100, 10, "Account"), box(300, 10, "Name"), box(500, 10, "Mobile Nbr"),
           box(100, 50, "11111111111"), box(300, 50, "SITA DEVI"), box(500, 50, "9876543210")]
    rows, info = parse_table(ocr)
    assert rows and rows[0]["account"] == "11111111111"



def test_misread_titles_still_match():
    ocr = [box(100, 10, "Acc0unt No"), box(300, 10, "NAME"), box(500, 10, "M0bi1e No"),
           box(100, 50, "11111111111"), box(300, 50, "SITA DEVI"), box(500, 50, "9876543210")]
    rows, info = parse_table(ocr)
    assert rows[0]["account"] == "11111111111" and rows[0]["mobile"] == "9876543210"
    assert info["inferred"] == []


def test_columns_found_from_numbers_when_titles_unknown():
    # titles the agent has never seen: columns are recognised by their numbers
    ocr = [box(100, 10, "Khata"), box(300, 10, "Grahak"), box(500, 10, "Sampark")]
    for i in range(4):
        y = 50 + i * 40
        ocr += [box(100, y, f"1111111111{i}"), box(300, y, f"NAME{i}"), box(500, y, f"987654321{i}")]
    rows, info = parse_table(ocr)
    assert [(r["account"][-1], r["mobile"][-1]) for r in rows] == [("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")]
    assert info["inferred"] == ["account", "mobile"]
