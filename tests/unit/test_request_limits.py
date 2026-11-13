"""Login rate limiter: block after N failures, recover after window."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture
def limits(repo_root, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "2")
    monkeypatch.setenv("LOGIN_RATE_WINDOW", "60")
    panel = str(repo_root / "panel")
    if panel not in sys.path:
        sys.path.insert(0, panel)
    sys.modules.pop("request_limits", None)
    import request_limits

    request_limits.reset_for_tests()
    yield request_limits
    request_limits.reset_for_tests()


@pytest.mark.unit
def test_login_blocked_after_max_attempts(limits, monkeypatch):
    now = 1_000.0
    monkeypatch.setattr(limits.time, "time", lambda: now)
    assert limits.login_blocked("1.2.3.4") is False
    limits.record_login_failure("1.2.3.4")
    assert limits.login_blocked("1.2.3.4") is False
    limits.record_login_failure("1.2.3.4")
    assert limits.login_blocked("1.2.3.4") is True
    limits.clear_login_failures("1.2.3.4")
    assert limits.login_blocked("1.2.3.4") is False


@pytest.mark.unit
def test_login_failures_expire_after_window(limits, monkeypatch):
    clock = {"t": 1_000.0}
    monkeypatch.setattr(limits.time, "time", lambda: clock["t"])
    limits.record_login_failure("8.8.8.8")
    limits.record_login_failure("8.8.8.8")
    assert limits.login_blocked("8.8.8.8") is True
    clock["t"] = 1_000.0 + 61
    assert limits.login_blocked("8.8.8.8") is False
