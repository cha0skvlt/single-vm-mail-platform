"""Mailbox auto-reply: set, clear, validation, file sync rollback."""

from __future__ import annotations

import sys

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


@pytest.fixture
def ar_mod(users_mod):
    import autoreplies

    return autoreplies


@pytest.mark.unit
def test_set_list_clear_autoreply(ar_mod, users_mod):
    users_mod.add_user("finotdel", "secret12")
    assert ar_mod.list_autoreply("finotdel")["body"] == ""
    out = ar_mod.set_autoreply("finotdel", "  Out of office  ")
    assert out == {"local": "finotdel", "body": "Out of office", "start_date": "", "end_date": ""}
    assert ar_mod.list_autoreply("finotdel")["body"] == "Out of office"
    ar_mod.set_autoreply("finotdel", "   ")
    assert ar_mod.list_autoreply("finotdel")["body"] == ""


@pytest.mark.unit
def test_autoreply_unknown_user(ar_mod):
    with pytest.raises(ar_mod.UsersError, match="user not found"):
        ar_mod.list_autoreply("missing")
    with pytest.raises(ar_mod.UsersError, match="user not found"):
        ar_mod.set_autoreply("missing", "hi")


@pytest.mark.unit
def test_autoreply_too_long(ar_mod, users_mod):
    users_mod.add_user("hub", "secret12")
    with pytest.raises(ar_mod.UsersError, match="autoreply too long"):
        ar_mod.set_autoreply("hub", "x" * 4001)


@pytest.mark.unit
def test_autoreply_rejects_sieve_words(ar_mod, users_mod):
    users_mod.add_user("hub", "secret12")
    with pytest.raises(ar_mod.UsersError, match="invalid autoreply"):
        ar_mod.set_autoreply("hub", "please fileinto INBOX")


@pytest.mark.unit
def test_set_autoreply_rolls_back_when_sync_fails(ar_mod, users_mod, monkeypatch):
    users_mod.add_user("src", "secret12")
    ar_mod.set_autoreply("src", "was")
    monkeypatch.setattr(
        ar_mod,
        "sync_autoreply_files",
        lambda local, body: (_ for _ in ()).throw(OSError("sync")),
    )
    with pytest.raises(OSError, match="sync"):
        ar_mod.set_autoreply("src", "new")
    assert ar_mod.list_autoreply("src")["body"] == "was"


@pytest.mark.unit
def test_delete_user_drops_autoreply(users_mod, ar_mod):
    users_mod.add_user("src", "secret12")
    ar_mod.set_autoreply("src", "gone")
    users_mod.delete_user("src")
    users_mod.add_user("src", "secret12")
    assert ar_mod.list_autoreply("src")["body"] == ""


@pytest.mark.unit
def test_delete_restores_autoreply_when_sync_fails(users_mod, ar_mod, monkeypatch):
    users_mod.add_user("src", "secret12")
    ar_mod.set_autoreply("src", "keep")

    def boom():
        raise OSError("sync")

    monkeypatch.setattr(users_mod, "sync_maps", boom)
    with pytest.raises(OSError, match="sync"):
        users_mod.delete_user("src")
    assert users_mod.list_users()[0]["local"] == "src"
    assert ar_mod.list_autoreply("src")["body"] == "keep"


@pytest.mark.unit
def test_set_autoreply_with_dates_roundtrip(ar_mod, users_mod):
    users_mod.add_user("otpusk", "secret12")
    out = ar_mod.set_autoreply("otpusk", "Away until Monday", "2026-10-20", "2026-10-31")
    assert out == {
        "local": "otpusk",
        "body": "Away until Monday",
        "start_date": "2026-10-20",
        "end_date": "2026-10-31",
    }
    listed = ar_mod.list_autoreply("otpusk")
    assert listed["start_date"] == "2026-10-20"
    assert listed["end_date"] == "2026-10-31"
    # clearing via empty body drops the row entirely, dates included
    ar_mod.set_autoreply("otpusk", "")
    assert ar_mod.list_autoreply("otpusk") == {
        "local": "otpusk",
        "body": "",
        "start_date": "",
        "end_date": "",
    }


@pytest.mark.unit
def test_autoreply_rejects_bad_dates(ar_mod, users_mod):
    users_mod.add_user("hub", "secret12")
    with pytest.raises(ar_mod.UsersError, match="invalid start date"):
        ar_mod.set_autoreply("hub", "hi", "20.10.2026")
    with pytest.raises(ar_mod.UsersError, match="invalid end date"):
        ar_mod.set_autoreply("hub", "hi", "", "31-12-2026")
    with pytest.raises(ar_mod.UsersError, match="end date before start date"):
        ar_mod.set_autoreply("hub", "hi", "2026-10-31", "2026-10-20")


@pytest.mark.unit
def test_autoreply_dates_optional(ar_mod, users_mod):
    users_mod.add_user("hub", "secret12")
    out = ar_mod.set_autoreply("hub", "hi", "", "")
    assert out["start_date"] == ""
    assert out["end_date"] == ""
    # legacy call signature still works
    out = ar_mod.set_autoreply("hub", "hi")
    assert out["start_date"] == ""
    assert out["end_date"] == ""


@pytest.mark.unit
def test_is_active_window(ar_mod):
    # inclusive boundaries, empty = unbounded
    assert ar_mod.is_active("", "", "2026-01-01")
    assert ar_mod.is_active("2026-10-20", "2026-10-31", "2026-10-20")
    assert ar_mod.is_active("2026-10-20", "2026-10-31", "2026-10-31")
    assert ar_mod.is_active("2026-10-20", "2026-10-31", "2026-10-25")
    assert not ar_mod.is_active("2026-10-20", "2026-10-31", "2026-10-19")
    assert not ar_mod.is_active("2026-10-20", "2026-10-31", "2026-11-01")
    assert ar_mod.is_active("", "2026-10-31", "2026-10-31")
    assert not ar_mod.is_active("", "2026-10-31", "2026-11-01")
    assert ar_mod.is_active("2026-10-20", "", "2026-12-01")
    assert not ar_mod.is_active("2026-10-20", "", "2026-10-19")


@pytest.mark.unit
def test_expired_and_pending_locals(ar_mod, users_mod):
    users_mod.add_user("gone", "secret12")
    users_mod.add_user("soon", "secret12")
    users_mod.add_user("now", "secret12")
    users_mod.add_user("forever", "secret12")
    ar_mod.set_autoreply("gone", "bye", "2026-10-01", "2026-10-05")
    ar_mod.set_autoreply("soon", "wait", "2026-11-01", "2026-11-10")
    ar_mod.set_autoreply("now", "hi", "2026-10-01", "2026-12-31")
    ar_mod.set_autoreply("forever", "hi")
    today = "2026-10-16"
    assert ar_mod.expired_locals(today) == ["gone"]
    assert ar_mod.pending_locals(today) == ["soon"]


@pytest.mark.unit
def test_future_autoreply_does_not_sync_sieve(ar_mod, users_mod, monkeypatch):
    users_mod.add_user("later", "secret12")
    synced = []

    def fake_sync(local, body):
        synced.append((local, body))

    monkeypatch.setattr(ar_mod, "sync_autoreply_files", fake_sync)
    ar_mod.set_autoreply("later", "Back later", "2099-01-01", "2099-01-15")
    # row is stored, but sieve must stay off until the window opens
    assert synced == [("later", "")]
    assert ar_mod.list_autoreply("later")["body"] == "Back later"


@pytest.mark.unit
def test_expired_autoreply_clears_sieve_immediately(ar_mod, users_mod, monkeypatch):
    users_mod.add_user("past", "secret12")
    synced = []

    def fake_sync(local, body):
        synced.append((local, body))

    monkeypatch.setattr(ar_mod, "sync_autoreply_files", fake_sync)
    ar_mod.set_autoreply("past", "was away", "2020-01-01", "2020-01-15")
    assert synced == [("past", "")]
    assert ar_mod.list_autoreply("past")["body"] == "was away"


@pytest.mark.unit
def test_active_autoreply_syncs_body(ar_mod, users_mod, monkeypatch):
    users_mod.add_user("live", "secret12")
    synced = []

    def fake_sync(local, body):
        synced.append((local, body))

    monkeypatch.setattr(ar_mod, "sync_autoreply_files", fake_sync)
    ar_mod.set_autoreply("live", "away", "2026-10-01", "2026-12-31")
    assert synced == [("live", "away")]
