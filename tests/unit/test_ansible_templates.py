"""Jinja templates render without Ansible (mail-specific fail2ban + cleanup)."""

from __future__ import annotations

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_fail2ban_jail_template():
    out = render_role_template("fail2ban", "jail.local.j2")
    assert "port = 666" in out
    assert "ignoreip = 127.0.0.1/8 ::1" in out
    assert "[sshd]" in out
    assert "[postfix]" in out
    assert "[dovecot]" in out
    assert "[mailpanel-auth]" in out
