from datetime import datetime, timedelta, timezone

import pytest

from app import config, users


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # production defaults, whatever the local .env says
    monkeypatch.setattr(config, "LOGIN_MAX_FAILED", 5)
    monkeypatch.setattr(config, "LOGIN_LOCKOUT_MINUTES", 15)
    users.init_db()


SHEET = (b"CSP Code,CSP Name,Shop Address,Mobile,Branch\n"
         b"csp001,Test Kendra One,Village A,+91 98765 43210,Branch A\n"
         b"CSP002,Test Kendra Two,Village B,,\n"
         b"CSP002,Duplicate,Village C,,\n"
         b",No Code,Village D,,\n"
         b"CSP003,,Village E,,\n")


def test_passwords_are_hashed_and_verified():
    h = users.hash_password("secret123")
    assert "secret123" not in h
    assert users.verify_password("secret123", h)
    assert not users.verify_password("secret124", h)


def test_password_strength():
    for bad in ("short1", "lettersonly", "12345678"):
        with pytest.raises(users.UserError):
            users.check_password_strength(bad)


def test_import_creates_updates_and_reports():
    r = users.import_sheet("csps.csv", SHEET)
    assert [c[0] for c in r["created"]] == ["CSP001", "CSP002"]
    assert len(r["errors"]) == 3
    csp = users.get_user("csp001")
    assert csp["mobile"] == "9876543210" and csp["must_change"] == 1
    temp_pw = r["created"][0][2]
    # second import updates details, keeps the password
    r2 = users.import_sheet("csps.csv", SHEET.replace(b"Village A", b"Village Z"))
    assert r2["created"] == [] and r2["updated"] == 2
    assert users.get_user("CSP001")["address"] == "Village Z"
    assert users.authenticate("CSP001", temp_pw)


def test_import_rejects_missing_columns():
    with pytest.raises(users.UserError, match="ADDRESS"):
        users.import_sheet("x.csv", b"CSP Code,CSP Name\nA1,B\n")
    with pytest.raises(users.UserError):
        users.import_sheet("x.pdf", b"whatever")


def test_import_cannot_overwrite_admin():
    users.create_admin("BOSS", "Admin", "adminpass1")
    r = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nBOSS,Hijack,Somewhere\n")
    assert r["created"] == [] and "admin" in r["errors"][0]
    assert users.get_user("BOSS")["role"] == "admin"


def test_lockout_after_five_wrong_passwords():
    pw = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nA1,N,Addr\n")["created"][0][2]
    for _ in range(config.LOGIN_MAX_FAILED):
        with pytest.raises(users.UserError):
            users.authenticate("A1", "wrong")
    with pytest.raises(users.UserError, match="Too many"):
        users.authenticate("A1", pw)  # even the right password is refused while locked


def test_disabled_csp_cannot_log_in_and_reset_works():
    pw = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nA1,N,Addr\n")["created"][0][2]
    users.set_active("A1", False)
    with pytest.raises(users.UserError, match="disabled"):
        users.authenticate("A1", pw)
    users.set_active("A1", True)
    new = users.reset_password("A1")
    assert users.authenticate("A1", new)["must_change"] == 1


def test_change_password_clears_must_change():
    pw = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nA1,N,Addr\n")["created"][0][2]
    users.change_password("A1", pw, "mynewpass9")
    assert users.authenticate("A1", "mynewpass9")["must_change"] == 0


def test_lock_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(config, "LOGIN_LOCKOUT_MINUTES", 0)
    pw = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nA1,N,Addr\n")["created"][0][2]
    for _ in range(config.LOGIN_MAX_FAILED + 3):
        with pytest.raises(users.UserError, match="Wrong"):
            users.authenticate("A1", "wrong")
    assert users.authenticate("A1", pw)


def test_set_admin_password_unlocks(monkeypatch):
    monkeypatch.setattr(config, "LOGIN_LOCKOUT_MINUTES", 15)
    users.create_admin("BOSS", "Admin", "adminpass1")
    for _ in range(config.LOGIN_MAX_FAILED):
        with pytest.raises(users.UserError):
            users.authenticate("BOSS", "wrong")
    users.set_admin_password("boss", "newadmin22")
    assert users.authenticate("BOSS", "newadmin22")["role"] == "admin"
    with pytest.raises(users.UserError):
        users.set_admin_password("NOBODY", "newadmin22")


def test_password_from_csp_name_stays(tmp_path, monkeypatch):
    from app import config, users
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    users.init_db()
    r = users.import_sheet("x.csv", b"CSP Code,CSP Name,Address\nA1,Ram Kumar,Village A\n", name_passwords=True)
    assert r["created"] == [("A1", "Ram Kumar", "ramkumar")]
    user = users.authenticate("a1", "ramkumar")
    assert user["must_change"] == 0          # owner's choice: no forced change
