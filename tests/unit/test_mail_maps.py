"""SQLite sync writes Dovecot/Postfix maps; CSV import only when empty."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from tests.support.runners import run


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            local TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?)",
        ("abramov", "abramov@example.com", "{SSHA512}hash", "t", "t"),
    )
    conn.commit()
    conn.close()


@pytest.mark.unit
def test_mail_users_sync_atomic_maps(repo_root: Path, tmp_path: Path):
    db = tmp_path / "users.db"
    _seed_db(db)
    users = tmp_path / "etc/dovecot/users"
    vmailbox = tmp_path / "etc/postfix/vmailbox"
    virtual = tmp_path / "etc/postfix/virtual"
    proc = run(
        ["bash", str(repo_root / "ansible/roles/mail/files/mail-users-sync.sh")],
        cwd=tmp_path,
        env={
            "MAILPANEL_DB": str(db),
            "MAIL_DOMAIN": "example.com",
            "USERS_FILE": str(users),
            "VMAILBOX_FILE": str(vmailbox),
            "VIRTUAL_FILE": str(virtual),
            "SKIP_POSTMAP": "1",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    text = users.read_text(encoding="utf-8")
    assert "abramov@example.com:{SSHA512}hash::::::" in text
    assert "abramov:{SSHA512}hash::::::" in text
    assert "abramov@example.com\texample.com/abramov/Maildir/" in vmailbox.read_text(encoding="utf-8")
    redirect = tmp_path / "etc/postfix/virtual_redirect"
    assert redirect.read_text(encoding="utf-8") == ""


@pytest.mark.unit
def test_import_skips_when_db_not_empty(repo_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAILPANEL_DB", str(tmp_path / "users.db"))
    monkeypatch.setenv("SKIP_MAIL_SYNC", "1")
    monkeypatch.setenv("MAIL_DOMAIN", "example.com")
    import sys

    sys.path.insert(0, str(repo_root / "panel"))
    from db import connect, user_count
    from users import import_csv_if_empty

    connect().close()
    conn = connect()
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?)",
        ("keep", "keep@example.com", "{SSHA512}x", "t", "t"),
    )
    conn.commit()
    conn.close()
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "username,email,full_name,password,archived\nabramov,abramov@example.com,N,secret12,yes\n",
        encoding="utf-8",
    )
    assert import_csv_if_empty(str(csv_path)) is None
    assert user_count() == 1


@pytest.mark.unit
def test_mail_users_sync_empty_db(repo_root: Path, tmp_path: Path):
    db = tmp_path / "users.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE users (
            local TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    users = tmp_path / "etc/dovecot/users"
    vmailbox = tmp_path / "etc/postfix/vmailbox"
    virtual = tmp_path / "etc/postfix/virtual"
    proc = run(
        ["bash", str(repo_root / "ansible/roles/mail/files/mail-users-sync.sh")],
        cwd=tmp_path,
        env={
            "MAILPANEL_DB": str(db),
            "MAIL_DOMAIN": "example.com",
            "USERS_FILE": str(users),
            "VMAILBOX_FILE": str(vmailbox),
            "VIRTUAL_FILE": str(virtual),
            "SKIP_POSTMAP": "1",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert users.read_text(encoding="utf-8") == ""
    assert vmailbox.read_text(encoding="utf-8") == ""
    assert "postmaster@example.com" in virtual.read_text(encoding="utf-8")
    assert (tmp_path / "etc/postfix/virtual_redirect").read_text(encoding="utf-8") == ""
    assert "synced 0" in proc.stdout


@pytest.mark.unit
def test_import_script_uses_pythonpath_and_resyncs(repo_root: Path, tmp_path: Path):
    script = (repo_root / "ansible/roles/mail/files/mail-users-import.sh").read_text(
        encoding="utf-8"
    )
    assert "PYTHONPATH" in script
    assert "sys.path.insert(0, sys.argv[2])" in script
    assert "${PYTHONPATH:-/opt/mail/panel}" in script

    db = tmp_path / "users.db"
    _seed_db(db)
    marker = tmp_path / "synced"
    sync = tmp_path / "sync.sh"
    sync.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    sync.chmod(0o755)
    csv_path = tmp_path / "users.csv"
    csv_path.write_text("email,password\n", encoding="utf-8")
    proc = run(
        ["bash", str(repo_root / "ansible/roles/mail/files/mail-users-import.sh"), str(csv_path)],
        cwd=tmp_path,
        env={
            "MAILPANEL_DB": str(db),
            "MAIL_DOMAIN": "example.com",
            "PYTHONPATH": str(repo_root / "panel"),
            "MAIL_USERS_SYNC": str(sync),
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "skipped" in proc.stdout
    assert marker.is_file()


def _run_sync(repo_root: Path, tmp_path: Path, db: Path):
    users = tmp_path / "etc/dovecot/users"
    vmailbox = tmp_path / "etc/postfix/vmailbox"
    virtual = tmp_path / "etc/postfix/virtual"
    redirect = tmp_path / "etc/postfix/virtual_redirect"
    proc = run(
        ["bash", str(repo_root / "ansible/roles/mail/files/mail-users-sync.sh")],
        cwd=tmp_path,
        env={
            "MAILPANEL_DB": str(db),
            "MAIL_DOMAIN": "example.com",
            "USERS_FILE": str(users),
            "VMAILBOX_FILE": str(vmailbox),
            "VIRTUAL_FILE": str(virtual),
            "SKIP_POSTMAP": "1",
        },
    )
    return proc, virtual, vmailbox, redirect


@pytest.mark.unit
def test_mail_users_sync_keep_copy_redirect_line(repo_root: Path, tmp_path: Path):
    db = tmp_path / "users.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE users (
            local TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE redirects (
            src TEXT NOT NULL,
            dest TEXT NOT NULL,
            PRIMARY KEY (src, dest)
        );
        """
    )
    conn.executemany(
        "INSERT INTO users VALUES (?,?,?,?,?)",
        [
            ("finotdel", "finotdel@example.com", "{SSHA512}a", "t", "t"),
            ("main", "main@example.com", "{SSHA512}b", "t", "t"),
        ],
    )
    conn.execute("INSERT INTO redirects VALUES (?,?)", ("finotdel", "main"))
    conn.commit()
    conn.close()
    proc, virtual, vmailbox, redirect = _run_sync(repo_root, tmp_path, db)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "postmaster@example.com" in virtual.read_text(encoding="utf-8")
    assert "finotdel@example.com\texample.com/finotdel/Maildir/" in vmailbox.read_text(
        encoding="utf-8"
    )
    assert (
        "finotdel@example.com\tfinotdel@example.com, main@example.com"
        in redirect.read_text(encoding="utf-8")
    )
    assert "synced 2 mailboxes 1 redirects" in proc.stdout


@pytest.mark.unit
def test_mail_users_sync_without_redirects_table(repo_root: Path, tmp_path: Path):
    db = tmp_path / "users.db"
    _seed_db(db)
    proc, _virtual, vmailbox, redirect = _run_sync(repo_root, tmp_path, db)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "abramov@example.com" in vmailbox.read_text(encoding="utf-8")
    assert redirect.read_text(encoding="utf-8") == ""


@pytest.mark.unit
def test_mail_users_sync_script_does_not_touch_sieve(repo_root: Path):
    text = (repo_root / "ansible/roles/mail/files/mail-users-sync.sh").read_text(encoding="utf-8")
    assert "sieve" not in text
    assert "autoreply" not in text
