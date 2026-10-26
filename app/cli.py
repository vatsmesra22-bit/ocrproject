"""Command line for accounts, a test reading and the web server.

    python -m app.cli read PHOTO                   read a (test) list photo, print counts only
    python -m app.cli create-admin                 create the super admin (asks for password)
    python -m app.cli reset-admin-password         new password for the super admin (server)
    python -m app.cli import-csps SHEET            create/update CSP logins from a sheet
    python -m app.cli serve [--port 8000]          run the web page

Output shows counts and problems only - never customer names or numbers.
"""
import argparse
import csv
import getpass
import os
import sys
from pathlib import Path

from app.logging_setup import setup_logging
from app import users


def main(argv=None):
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rd = sub.add_parser("read")
    rd.add_argument("photo")
    sub.add_parser("create-admin")
    im = sub.add_parser("import-csps")
    im.add_argument("sheet")
    im.add_argument("--name-passwords", action="store_true",
                    help="first-login password = CSP name (small letters, no spaces)")
    im.add_argument("--out", default="csp-passwords.csv",
                    help="where to write new CSPs' temporary passwords")
    sub.add_parser("reset-admin-password")
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    setup_logging()
    try:
        if args.cmd == "read":
            # nothing is saved - the photo is read in memory and only counts are printed
            from app.ocr_table import extract_rows
            from app.validate import check_rows
            rows, info = extract_rows(Path(args.photo).read_bytes())
            if info.get("error"):
                print(f"error: {info['error']}", file=sys.stderr)
                return 1
            checked = check_rows(rows)
            print(f"rows: {len(checked)}  ok: {sum(r['ok'] for r in checked)}  "
                  f"to fix: {sum(bool(r['problems']) for r in checked)}  "
                  f"no mobile: {sum(r['no_mobile'] for r in checked)}")
            for i, r in enumerate(checked, 1):
                if r["problems"]:
                    print(f"  row {i}: {', '.join(r['problems'])}")
        elif args.cmd == "create-admin":
            return _create_admin()
        elif args.cmd == "reset-admin-password":
            users.init_db()
            code = input("Super admin login ID: ").strip()
            pw = getpass.getpass("New password (not shown): ")
            if pw != getpass.getpass("Type it again: "):
                print("error: passwords do not match", file=sys.stderr)
                return 1
            users.set_admin_password(code, pw)
            print("Password changed. You can log in now.")
        elif args.cmd == "import-csps":
            users.init_db()
            p = Path(args.sheet)
            result = users.import_sheet(p.name, p.read_bytes(), name_passwords=args.name_passwords)
            if result["created"]:
                with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["CSP Code", "Name", "Temporary password"])
                    w.writerows(result["created"])
                print(f"{len(result['created'])} new CSP(s); temporary passwords written to {args.out}")
                print("Share each password privately, then delete that file.")
            print(f"{result['updated']} existing CSP(s) updated")
            for e in result["errors"]:
                print(f"  skipped - {e}")
        elif args.cmd == "serve":
            import uvicorn
            # Real client IPs come from the reverse proxy's X-Forwarded-For, trusted
            # only from FORWARDED_ALLOW_IPS (never "*"). One worker: readings in
            # progress are held in this process's memory (reader.py).
            from app import config
            uvicorn.run("app.web:app", host=args.host, port=args.port, proxy_headers=True,
                        root_path=config.BASE_PATH,  # app under a sub-path (EKO_BASE_PATH)
                        log_config=None,  # use our log files (logging_setup.py)
                        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
                        workers=1)
    except (users.UserError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _create_admin():
    users.init_db()
    if any(u["role"] == "admin" for u in users.list_users()):
        print("A super admin already exists.")
        return 1
    name = input("Your full name: ").strip()
    code = input("Login ID (e.g. ADMIN1): ").strip()
    print("Choose a NEW password: 8+ characters, letters and numbers, not used anywhere else.")
    pw = getpass.getpass("Password (not shown): ")
    if pw != getpass.getpass("Type it again: "):
        print("error: passwords do not match", file=sys.stderr)
        return 1
    code = users.create_admin(code, name, pw)
    print(f"Super admin {code} created. Log in at the web page with this ID.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
