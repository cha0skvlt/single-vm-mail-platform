"""Mailbox CRUD + doveadm hash + sync hook."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from typing import Any

from db import session, user_count

LOCAL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MIN_PASSWORD_LEN = 6


class UsersError(ValueError):
    pass


def mail_domain() -> str:
    return os.environ.get("MAIL_DOMAIN", "example.com").strip().lower()


def validate_local(raw: str) -> str:
    local = (raw or "").strip().lower()
    if not local or not LOCAL_RE.fullmatch(local):
        raise UsersError("invalid login")
    if ".." in local or "/" in local or "@" in local:
        raise UsersError("invalid login")
    return local


def validate_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise UsersError("password too short")
    return password


def hash_password(password: str) -> str:
    proc = subprocess.run(
        ["doveadm", "pw", "-s", "SSHA512", "-p", password],
        capture_output=True,
        text=True,
        check=True,
    )
    hashed = proc.stdout.strip()
    if not hashed:
        raise UsersError("password hash failed")
    return hashed


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_users() -> list[dict[str, Any]]:
    with session() as conn:
        rows = conn.execute(
            "SELECT local, email, created_at, updated_at FROM users ORDER BY local"
        ).fetchall()
    return [dict(row) for row in rows]


def add_user(local: str, password: str) -> dict[str, str]:
    local = validate_local(local)
    password = validate_password(password)
    email = f"{local}@{mail_domain()}"
    hashed = hash_password(password)
    stamp = _now()
    with session() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE local = ?", (local,)).fetchone()
        if exists:
            raise UsersError("user exists")
        try:
            conn.execute(
                "INSERT INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
                (local, email, hashed, stamp, stamp),
            )
        except sqlite3.IntegrityError as exc:
            raise UsersError("user exists") from exc
    _sync_or_rollback(lambda: _delete_row(local))
    return {"local": local, "email": email}


def set_password(local: str, password: str) -> None:
    local = validate_local(local)
    password = validate_password(password)
    hashed = hash_password(password)
    previous = None
    with session() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE local = ?", (local,)
        ).fetchone()
        if row is None:
            raise UsersError("user not found")
        previous = row["password_hash"]
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE local = ?",
            (hashed, _now(), local),
        )
    _sync_or_rollback(
        lambda: _restore_hash(local, previous) if previous is not None else None
    )


def delete_user(local: str) -> None:
    local = validate_local(local)
    snapshot = None
    redirect_rows: list[tuple[str, str]] = []
    autoreply_body = ""
    with session() as conn:
        row = conn.execute("SELECT * FROM users WHERE local = ?", (local,)).fetchone()
        if row is None:
            raise UsersError("user not found")
        snapshot = dict(row)
        redirect_rows = [
            (r["src"], r["dest"])
            for r in conn.execute(
                "SELECT src, dest FROM redirects WHERE src = ? OR dest = ?",
                (local, local),
            ).fetchall()
        ]
        try:
            ar = conn.execute(
                "SELECT body FROM autoreplies WHERE local = ?",
                (local,),
            ).fetchone()
            if ar is not None:
                autoreply_body = ar["body"]
        except sqlite3.OperationalError:
            autoreply_body = ""
        conn.execute("DELETE FROM users WHERE local = ?", (local,))
    _sync_or_rollback(
        lambda: _restore_user_redirects_autoreply(snapshot, redirect_rows, autoreply_body)
        if snapshot
        else None
    )
    from autoreplies import sync_autoreply_files

    sync_autoreply_files(local, "")


def import_csv_if_empty(csv_path: str) -> int | None:
    """Load CSV only when the database has no rows.

    Returns imported count, or None when the database already has rows.
    Legacy short passwords are kept as-is (clients + archive use them).
    """
    if user_count() > 0:
        return None
    imported, _ = _import_csv_rows(csv_path)
    if imported:
        try:
            sync_maps()
        except Exception:
            with session() as conn:
                conn.execute("DELETE FROM users")
            raise
    return imported


def import_csv_missing(csv_path: str) -> int:
    """Insert accounts that are in the CSV but not in SQLite. Does not update existing hashes."""
    imported, added = _import_csv_rows(csv_path)
    if imported:
        try:
            sync_maps()
        except Exception:
            with session() as conn:
                conn.executemany("DELETE FROM users WHERE local = ?", [(local,) for local in added])
            raise
    return imported


def _import_csv_rows(csv_path: str) -> tuple[int, list[str]]:
    import csv
    from pathlib import Path

    path = Path(csv_path)
    imported = 0
    added: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as fh, session() as conn:
        for row in csv.DictReader(fh):
            email = (row.get("email") or "").strip().strip('"')
            pw = (row.get("password") or "").strip().strip('"')
            if not email or not pw:
                continue
            try:
                local = validate_local(email.split("@", 1)[0])
            except UsersError:
                continue
            hashed = hash_password(pw)
            stamp = _now()
            cur = conn.execute(
                "INSERT OR IGNORE INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
                (local, f"{local}@{mail_domain()}", hashed, stamp, stamp),
            )
            if cur.rowcount:
                imported += 1
                added.append(local)
    return imported, added


def _delete_row(local: str) -> None:
    with session() as conn:
        conn.execute("DELETE FROM users WHERE local = ?", (local,))


def _restore_hash(local: str, password_hash: str) -> None:
    with session() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE local = ?",
            (password_hash, local),
        )


def _restore_row(row: dict[str, Any]) -> None:
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
            (row["local"], row["email"], row["password_hash"], row["created_at"], row["updated_at"]),
        )


def _restore_user_and_redirects(row: dict[str, Any], redirect_rows: list[tuple[str, str]]) -> None:
    _restore_user_redirects_autoreply(row, redirect_rows, "")


def _restore_user_redirects_autoreply(
    row: dict[str, Any],
    redirect_rows: list[tuple[str, str]],
    autoreply_body: str,
) -> None:
    _restore_row(row)
    with session() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO redirects (src, dest) VALUES (?, ?)",
            redirect_rows,
        )
        if autoreply_body:
            conn.execute(
                """
                INSERT INTO autoreplies (local, body, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(local) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
                """,
                (row["local"], autoreply_body, _now()),
            )


def _sync_or_rollback(compensate) -> None:
    try:
        sync_maps()
    except Exception:
        compensate()
        raise


def sync_maps() -> None:
    if os.environ.get("SKIP_MAIL_SYNC", "").strip() in {"1", "true", "yes"}:
        return
    cmd = os.environ.get("MAIL_USERS_SYNC", "/usr/local/sbin/mail-users-sync")
    if os.geteuid() == 0:
        subprocess.run([cmd], check=True)
        return
    subprocess.run(["sudo", "--non-interactive", cmd], check=True)
