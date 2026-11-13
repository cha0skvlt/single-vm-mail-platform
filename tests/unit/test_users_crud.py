"""Mailbox CRUD, CSV import, and map-sync rollback."""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest


@pytest.fixture
def users_mod(repo_root, tmp_path, monkeypatch):
    monkeypatch.setenv("MAILPANEL_DB", str(tmp_path / "users.db"))
    monkeypatch.setenv("MAIL_DOMAIN", "example.com")
    monkeypatch.setenv("SKIP_MAIL_SYNC", "1")
    monkeypatch.setenv("SKIP_AUTOREPLY_SYNC", "1")
    panel = str(repo_root / "panel")
    if panel not in sys.path:
        sys.path.insert(0, panel)
    for name in ("db", "users", "redirects", "autoreplies"):
        sys.modules.pop(name, None)
    import users

    monkeypatch.setattr(users, "hash_password", lambda pw: "{SSHA512}" + pw)
    return users


@pytest.mark.unit
def test_add_list_password_delete(users_mod):
    added = users_mod.add_user("Abramov", "secret12")
    assert added == {"local": "abramov", "email": "abramov@example.com"}
    rows = users_mod.list_users()
    assert len(rows) == 1
    assert rows[0]["local"] == "abramov"
    assert "password_hash" not in rows[0]

    users_mod.set_password("abramov", "newpass99")
    users_mod.delete_user("abramov")
    assert users_mod.list_users() == []


@pytest.mark.unit
def test_add_duplicate_and_short_password(users_mod):
    users_mod.add_user("ivanov", "secret12")
    with pytest.raises(users_mod.UsersError, match="user exists"):
        users_mod.add_user("ivanov", "secret99")
    with pytest.raises(users_mod.UsersError, match="password too short"):
        users_mod.add_user("petrov", "short")
    users_mod.add_user("sidorov", "sixchr")
    users_mod.set_password("sidorov", "abcdef")
    with pytest.raises(users_mod.UsersError, match="user not found"):
        users_mod.set_password("missing", "secret12")
    with pytest.raises(users_mod.UsersError, match="user not found"):
        users_mod.delete_user("missing")


@pytest.mark.unit
def test_add_rolls_back_when_sync_fails(users_mod, monkeypatch):
    monkeypatch.setattr(users_mod, "sync_maps", lambda: (_ for _ in ()).throw(OSError("sync")))
    with pytest.raises(OSError, match="sync"):
        users_mod.add_user("rollback", "secret12")
    assert users_mod.list_users() == []


@pytest.mark.unit
def test_delete_restores_row_when_sync_fails(users_mod, monkeypatch):
    users_mod.add_user("keepme", "secret12")

    def boom():
        raise OSError("sync")

    monkeypatch.setattr(users_mod, "sync_maps", boom)
    with pytest.raises(OSError, match="sync"):
        users_mod.delete_user("keepme")
    rows = users_mod.list_users()
    assert [row["local"] for row in rows] == ["keepme"]


@pytest.mark.unit
def test_set_password_restores_hash_when_sync_fails(users_mod, monkeypatch):
    users_mod.add_user("hashme", "original1")
    from db import connect

    conn = connect()
    before = conn.execute("SELECT password_hash FROM users WHERE local = ?", ("hashme",)).fetchone()[0]
    conn.close()
    assert before == "{SSHA512}original1"

    monkeypatch.setattr(users_mod, "sync_maps", lambda: (_ for _ in ()).throw(OSError("sync")))
    with pytest.raises(OSError, match="sync"):
        users_mod.set_password("hashme", "changed99")

    conn = connect()
    after = conn.execute("SELECT password_hash FROM users WHERE local = ?", ("hashme",)).fetchone()[0]
    conn.close()
    assert after == "{SSHA512}original1"


@pytest.mark.unit
def test_import_skips_invalid_rows_and_counts_inserts(users_mod, tmp_path):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "username,email,full_name,password,archived\n"
        "ok,ok.user@example.com,N,secret12,no\n"
        "bad,../root@example.com,N,secret12,no\n"
        "empty,,N,secret12,no\n"
        "shortpw,short@example.com,N,abc,no\n"
        "dup,ok.user@example.com,N,secret99,no\n"
        "second,second@example.com,N,secret12,no\n",
        encoding="utf-8",
    )
    assert users_mod.import_csv_if_empty(str(csv_path)) == 3
    locals_ = [row["local"] for row in users_mod.list_users()]
    assert locals_ == ["ok.user", "second", "short"]


@pytest.mark.unit
def test_import_missing_keeps_short_passwords(users_mod, tmp_path):
    users_mod.add_user("keepme", "secret12")
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "email,password\nkeepme@example.com,secret12\nlegacy@example.com,ab\n",
        encoding="utf-8",
    )
    assert users_mod.import_csv_missing(str(csv_path)) == 1
    locals_ = [row["local"] for row in users_mod.list_users()]
    assert locals_ == ["keepme", "legacy"]


@pytest.mark.unit
def test_import_rolls_back_when_sync_fails(users_mod, tmp_path, monkeypatch):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text(
        "email,password\none@example.com,secret12\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(users_mod, "sync_maps", lambda: (_ for _ in ()).throw(OSError("sync")))
    with pytest.raises(OSError, match="sync"):
        users_mod.import_csv_if_empty(str(csv_path))
    assert users_mod.list_users() == []


@pytest.mark.unit
def test_integrity_error_becomes_user_exists(users_mod, monkeypatch):
    users_mod.add_user("taken", "secret12")

    real_session = users_mod.session

    def colliding_session():
        class FakeConn:
            def execute(self, sql, params=()):
                if sql.startswith("SELECT"):
                    return types.SimpleNamespace(fetchone=lambda: None)
                raise sqlite3.IntegrityError("UNIQUE")

        class Ctx:
            def __enter__(self):
                return FakeConn()

            def __exit__(self, *args):
                return False

        return Ctx()

    monkeypatch.setattr(users_mod, "session", colliding_session)
    monkeypatch.setattr(users_mod, "hash_password", lambda pw: "{SSHA512}x")
    with pytest.raises(users_mod.UsersError, match="user exists"):
        users_mod.add_user("other", "secret12")
    monkeypatch.setattr(users_mod, "session", real_session)
