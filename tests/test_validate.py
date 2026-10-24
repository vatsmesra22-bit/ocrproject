from app.validate import check_row, check_rows, clean_mobile, clean_name, group_by_mobile


def row(account="12345678901", mobile="9876543210", name="RAM KUMAR"):
    return {"account": account, "mobile": mobile, "name": name, "low_confidence": False}


def test_valid_row_passes():
    r = check_row(row())
    assert r["ok"] and r["problems"] == []


def test_mobile_rules():
    assert clean_mobile("919876543210") == "9876543210"
    assert not check_row(row(mobile="5876543210"))["ok"]   # must start 6-9
    assert not check_row(row(mobile="987654321"))["ok"]    # 9 digits
    no_mob = check_row(row(mobile=""))
    assert no_mob["no_mobile"] and not no_mob["ok"] and no_mob["problems"] == []  # call / visit


def test_account_must_be_11_digits():
    assert not check_row(row(account="1234567890"))["ok"]


def test_low_confidence_is_flagged():
    r = row()
    r["low_confidence"] = True
    assert not check_row(r)["ok"]


def test_names_glued_masked_and_cut_off():
    assert clean_name("SATISHKUMAR")[:2] == ("Satish Kumar", "Satish")
    assert clean_name("SatishKumar")[1] == "Satish"
    assert clean_name("MOHAMMADNAZIM")[1] == "Mohammad Nazim"
    assert clean_name("SIMRANXXX") == ("Simran", "Simran", True)
    assert clean_name("MAHESHKUM")[1] == "Mahesh"
    assert clean_name("XXX")[1] == "Customer"
    assert clean_name("")[1] == "Customer"


def test_real_names_are_not_broken():
    # endings that look like a cut-off surname but are real names
    assert clean_name("MOHSIN KHAN")[:2] == ("Mohsin Khan", "Mohsin")
    assert clean_name("MOHAMMADMOHSIN")[:2] == ("Mohammad Mohsin", "Mohammad Mohsin")
    assert clean_name("MOHAMMAD MOHSIN")[1] == "Mohammad Mohsin"
    assert clean_name("VASUDEV")[0] == "Vasudev"
    assert clean_name("SULEKHA")[0] == "Sulekha"
    assert clean_name("JITENDRATIW")[0] == "Jitendra Tiw"   # real cut-off still handled


def test_duplicate_account_flagged():
    rows = check_rows([row(), row(mobile="9876543211")])
    assert rows[0]["ok"] and not rows[1]["ok"]


def test_shared_mobile_gets_one_message():
    rows = check_rows([row(account="11111111111", name="SITA DEVI"),
                       row(account="22222222222", name="GITA DEVI"),
                       row(account="33333333333", mobile="8765432109")])
    groups = group_by_mobile(rows)
    assert len(groups) == 2
    shared = next(g for g in groups if g["mobile"] == "9876543210")
    assert shared["accounts_last4"] == ["1111", "2222"]
    assert shared["greeting"] == "Sita / Gita"


def test_rows_with_problems_are_not_messaged():
    rows = check_rows([row(mobile="123")])
    assert group_by_mobile(rows) == []
