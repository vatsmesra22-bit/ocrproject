"""Excel / CSV list upload - made-up numbers only."""
import io

import pytest
from openpyxl import Workbook

from app.sheet_list import SheetError, read_customer_sheet

CSV = (b"Branch report,,,,\n"
       b"A/C No,A/C Name,Operative/Inoperative,Agent Code,Mobile NoBB\n"
       b"11111111111,SITA DEVI,INOPERATIVE,1A850639,9876543210BB\n"
       b"22222222222,RAM LAL,OPERATIVE,1A850639,9876543211BB\n"
       b"33333333333,GITA KUMARI,INOPERATIVE,1A850639,BB\n"
       b",,,,\n")


def test_csv_keeps_only_inoperative_and_cleans_mobile():
    rows, info = read_customer_sheet("list.csv", CSV)
    assert [(r["account"], r["mobile"], r["name"]) for r in rows] == [
        ("11111111111", "9876543210", "SITA DEVI"),
        ("33333333333", "", "GITA KUMARI")]
    assert info["skipped_operative"] == 1


def test_xlsx_with_numbers_stored_as_numbers():
    wb = Workbook()
    ws = wb.active
    ws.append(["MEMB_CUST_AC", "NAME", "FTHR_NM", "MOBILE_NBR"])
    ws.append([11111111111, "SITA DEVI", "RAM", 9876543210])
    ws.append([22222222222.0, "GITA", "SHYAM", 9876543211.0])
    buf = io.BytesIO()
    wb.save(buf)
    rows, _ = read_customer_sheet("list.xlsx", buf.getvalue())
    assert [(r["account"], r["mobile"]) for r in rows] == [
        ("11111111111", "9876543210"), ("22222222222", "9876543211")]


@pytest.mark.parametrize("name,data,msg", [
    ("list.xls", b"x", "Save as"),
    ("list.pdf", b"x", "Excel"),
    ("list.csv", b"Name,Address\nA,B\n", "column titles"),
    ("list.csv", b"AcNo,Operative,MobileNo\n1,OPERATIVE,9876543210\n", "No inoperative"),
])
def test_bad_files_explain_what_to_do(name, data, msg):
    with pytest.raises(SheetError, match=msg):
        read_customer_sheet(name, data)
