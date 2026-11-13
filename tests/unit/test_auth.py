"""Panel session cookies: issue, expiry, tamper, length-safe compare."""

from __future__ import annotations

import base64
import sys

import pytest


@pytest.fixture
def auth_mod(repo_root, monkeypatch):
    monkeypatch.setenv("MAIL_ADMIN_USER", "admin")
    monkeypatch.setenv("MAIL_ADMIN_PASSWORD", "correct-horse")
    monkeypatch.setenv("MAIL_SESSION_SECRET", "unit-test-session-secret")
    panel = str(repo_root / "panel")
    if panel not in sys.path:
        sys.path.insert(0, panel)
    sys.modules.pop("auth", None)
    import auth

    return auth


@pytest.mark.unit
def test_verify_login_accepts_only_configured_pair(auth_mod):
    assert auth_mod.verify_login("admin", "correct-horse") is True
    assert auth_mod.verify_login("admin", "wrong") is False
    assert auth_mod.verify_login("nope", "correct-horse") is False


@pytest.mark.unit
def test_verify_login_different_length_does_not_raise(auth_mod):
    assert auth_mod.verify_login("a", "x") is False
    assert auth_mod.verify_login("admin-extra", "correct-horse") is False
    assert auth_mod.verify_login("admin", "short") is False


@pytest.mark.unit
def test_session_cookie_roundtrip(auth_mod):
    header = auth_mod.issue_session_cookie("admin")
    assert header.startswith("mail_session=")
    assert "HttpOnly" in header
    assert "Secure" in header
    token = header.split(";", 1)[0].split("=", 1)[1]
    assert auth_mod.session_user(f"mail_session={token}") == "admin"
    assert auth_mod.session_user(None) is None
    assert auth_mod.session_user("other=1") is None


@pytest.mark.unit
def test_session_cookie_rejects_tamper_and_wrong_user(auth_mod, monkeypatch):
    header = auth_mod.issue_session_cookie("admin")
    token = header.split(";", 1)[0].split("=", 1)[1]
    raw = bytearray(base64.urlsafe_b64decode(token.encode("ascii")))
    raw[0] ^= 0x01
    bad = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    assert auth_mod.session_user(f"mail_session={bad}") is None

    monkeypatch.setenv("MAIL_ADMIN_USER", "other")
    assert auth_mod.session_user(f"mail_session={token}") is None


@pytest.mark.unit
def test_session_cookie_rejects_expired(auth_mod, monkeypatch):
    monkeypatch.setattr(auth_mod.time, "time", lambda: 1_700_000_000)
    header = auth_mod.issue_session_cookie("admin")
    token = header.split(";", 1)[0].split("=", 1)[1]
    monkeypatch.setattr(auth_mod.time, "time", lambda: 1_700_000_000 + auth_mod.SESSION_TTL_SEC + 1)
    assert auth_mod.session_user(f"mail_session={token}") is None


@pytest.mark.unit
def test_clear_session_cookie_expires(auth_mod):
    header = auth_mod.clear_session_cookie()
    assert "Max-Age=0" in header
    assert header.startswith("mail_session=")
