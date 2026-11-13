"""Mailbox redirects: validation, cycles, rollback, delete cascade."""

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
def redir_mod(users_mod):
    import redirects

    return redirects


@pytest.mark.unit
def test_set_list_clear_redirects(redir_mod, users_mod):
    users_mod.add_user("finotdel", "secret12")
    users_mod.add_user("main", "secret12")
    assert redir_mod.list_redirects("finotdel")["destinations"] == []
    out = redir_mod.set_redirects("finotdel", "main")
    assert out == {"local": "finotdel", "destinations": ["main"]}
    assert redir_mod.list_redirects("finotdel")["destinations"] == ["main"]
    redir_mod.set_redirects("finotdel", "")
    assert redir_mod.list_redirects("finotdel")["destinations"] == []


@pytest.mark.unit
def test_redirect_rejects_self_unknown_cycle(redir_mod, users_mod):
    users_mod.add_user("alpha", "secret12")
    users_mod.add_user("beta", "secret12")
    users_mod.add_user("gamma", "secret12")
    with pytest.raises(redir_mod.UsersError, match="redirect to self"):
        redir_mod.set_redirects("alpha", "alpha")
    with pytest.raises(redir_mod.UsersError, match="unknown mailbox"):
        redir_mod.set_redirects("alpha", "missing")
    with pytest.raises(redir_mod.UsersError, match="local mailbox only"):
        redir_mod.set_redirects("alpha", "beta@gmail.com")
    redir_mod.set_redirects("alpha", "beta@example.com")
    assert redir_mod.list_redirects("alpha")["destinations"] == ["beta"]
    redir_mod.set_redirects("alpha", "beta")
    redir_mod.set_redirects("beta", "gamma")
    with pytest.raises(redir_mod.UsersError, match="redirect cycle"):
        redir_mod.set_redirects("gamma", "alpha")


@pytest.mark.unit
def test_redirect_too_many(redir_mod, users_mod):
    users_mod.add_user("hub", "secret12")
    dests = []
    for i in range(11):
        name = f"u{i}"
        users_mod.add_user(name, "secret12")
        dests.append(name)
    with pytest.raises(redir_mod.UsersError, match="too many redirects"):
        redir_mod.set_redirects("hub", ",".join(dests))


@pytest.mark.unit
def test_set_redirects_rolls_back_when_sync_fails(redir_mod, users_mod, monkeypatch):
    users_mod.add_user("src", "secret12")
    users_mod.add_user("dst", "secret12")
    redir_mod.set_redirects("src", "dst")
    monkeypatch.setattr(users_mod, "sync_maps", lambda: (_ for _ in ()).throw(OSError("sync")))
    with pytest.raises(OSError, match="sync"):
        redir_mod.set_redirects("src", "")
    assert redir_mod.list_redirects("src")["destinations"] == ["dst"]


@pytest.mark.unit
def test_delete_user_drops_redirect_edges(users_mod, redir_mod):
    users_mod.add_user("src", "secret12")
    users_mod.add_user("dst", "secret12")
    redir_mod.set_redirects("src", "dst")
    users_mod.delete_user("dst")
    assert redir_mod.list_redirects("src")["destinations"] == []


@pytest.mark.unit
def test_delete_restores_redirects_when_sync_fails(users_mod, redir_mod, monkeypatch):
    users_mod.add_user("src", "secret12")
    users_mod.add_user("dst", "secret12")
    redir_mod.set_redirects("src", "dst")

    def boom():
        raise OSError("sync")

    monkeypatch.setattr(users_mod, "sync_maps", boom)
    with pytest.raises(OSError, match="sync"):
        users_mod.delete_user("dst")
    locals_ = [row["local"] for row in users_mod.list_users()]
    assert locals_ == ["dst", "src"]
    assert redir_mod.list_redirects("src")["destinations"] == ["dst"]
