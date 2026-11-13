"""CLI entry points for CI and operators (console script: ``ops``)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts import dkim, diagnostic, inventory, maps, smoke, users

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB = Path("/var/lib/mailpanel/users.db")
DEFAULT_USERS_FILE = Path("/etc/dovecot/users")
DEFAULT_VMAILBOX_FILE = Path("/etc/postfix/vmailbox")
DEFAULT_VIRTUAL_FILE = Path("/etc/postfix/virtual")
DEFAULT_REDIRECT_FILE = Path("/etc/postfix/virtual_redirect")


def _domain(value: str | None) -> str:
    return (value or os.environ.get("MAIL_DOMAIN") or "example.com").strip().lower()


def _map_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "users_file": Path(args.users_file),
        "vmailbox_file": Path(args.vmailbox_file),
        "virtual_file": Path(args.virtual_file),
        "redirect_file": Path(args.redirect_file),
    }


def cmd_check_maps(args: argparse.Namespace) -> int:
    try:
        rendered = maps.render(Path(args.db), _domain(args.domain))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    problems = maps.check(rendered, **_map_paths(args))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("maps: up to date")
    return 0


def cmd_users_import(args: argparse.Namespace) -> int:
    try:
        count = users.import_csv(
            Path(args.csv),
            db=Path(args.db),
            domain=_domain(args.domain),
            missing=args.missing,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if count is None:
        print("import skipped (database not empty)")
    else:
        print(f"imported {count} accounts")
    return 0


def cmd_users_sync(args: argparse.Namespace) -> int:
    try:
        rendered = maps.render(Path(args.db), _domain(args.domain))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    maps.write(rendered, **_map_paths(args))
    print(f"synced {len(rendered.vmailbox.splitlines())} mailboxes")
    return 0


def cmd_dkim_check(args: argparse.Namespace) -> int:
    problems = dkim.check(
        domain=_domain(args.domain),
        selector=args.selector,
        keyfile=Path(args.keyfile),
        record_file=Path(args.record),
    )
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("dkim: ok")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    results = smoke.run(args.host, domain=_domain(args.domain), timeout=args.timeout)
    failed = 0
    for result in results:
        if result.ok:
            print(f"smoke: {result.name} ({args.host}:{result.port}) {result.detail}")
        else:
            print(
                f"error: {result.name} ({args.host}:{result.port}) {result.detail}",
                file=sys.stderr,
            )
            failed += 1
    if failed:
        print("smoke: FAILED", file=sys.stderr)
        return 1
    print("smoke: ok (25/443/465/995 reachable, TLS valid)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    bundle = diagnostic.collect(Path(args.out))
    print(f"bundle: {bundle}")
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    host = args.host
    if args.from_terraform:
        outputs = inventory.from_terraform(REPO_ROOT)
        host = host or outputs.get("public_ip_address", "")
        if not host:
            print("error: terraform output public_ip_address is empty", file=sys.stderr)
            return 1
    if not host:
        print("error: --host or --from-terraform is required", file=sys.stderr)
        return 1
    path = inventory.write(
        Path(args.path),
        host,
        port=args.port,
        user=args.user,
        group=args.group,
    )
    print(f"wrote {path}")
    return 0


def _add_map_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--domain", default=None)
    parser.add_argument("--users-file", default=str(DEFAULT_USERS_FILE))
    parser.add_argument("--vmailbox-file", default=str(DEFAULT_VMAILBOX_FILE))
    parser.add_argument("--virtual-file", default=str(DEFAULT_VIRTUAL_FILE))
    parser.add_argument("--redirect-file", default=str(DEFAULT_REDIRECT_FILE))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ops")
    sub = parser.add_subparsers(dest="command", required=True)

    p_maps = sub.add_parser("check-maps", help="Diff rendered maps against deployed files")
    _add_map_paths(p_maps)
    p_maps.set_defaults(func=cmd_check_maps)

    p_import = sub.add_parser("users-import", help="Import accounts from CSV")
    p_import.add_argument("csv")
    p_import.add_argument("--db", default=str(DEFAULT_DB))
    p_import.add_argument("--domain", default=None)
    p_import.add_argument("--missing", action="store_true", help="Import only missing accounts")
    p_import.set_defaults(func=cmd_users_import)

    p_sync = sub.add_parser("users-sync", help="Render maps from SQLite and write them")
    _add_map_paths(p_sync)
    p_sync.set_defaults(func=cmd_users_sync)

    p_dkim = sub.add_parser("dkim-check", help="Check DKIM key and DNS record")
    p_dkim.add_argument("--domain", default=None)
    p_dkim.add_argument("--selector", default="mail")
    p_dkim.add_argument("--keyfile", default="dkim/mail.private")
    p_dkim.add_argument("--record", default="dkim/mail.txt")
    p_dkim.set_defaults(func=cmd_dkim_check)

    p_smoke = sub.add_parser("smoke", help="Post-deploy port and TLS checks")
    p_smoke.add_argument("--host", required=True)
    p_smoke.add_argument("--domain", default=None)
    p_smoke.add_argument("--timeout", type=float, default=10.0)
    p_smoke.set_defaults(func=cmd_smoke)

    p_doctor = sub.add_parser("doctor", help="Collect a diagnostic bundle")
    p_doctor.add_argument("--out", default=".")
    p_doctor.set_defaults(func=cmd_doctor)

    p_inv = sub.add_parser("inventory", help="Write ansible/inventory.ini")
    p_inv.add_argument("--host", default="")
    p_inv.add_argument("--from-terraform", action="store_true")
    p_inv.add_argument("--port", type=int, default=666)
    p_inv.add_argument("--user", default="deploy")
    p_inv.add_argument("--group", default="mail")
    p_inv.add_argument("--path", default="ansible/inventory.ini")
    p_inv.set_defaults(func=cmd_inventory)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
