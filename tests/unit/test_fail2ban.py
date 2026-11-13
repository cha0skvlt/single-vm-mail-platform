"""fail2ban: sshd + postfix + dovecot, systemd backend, no Traefik."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_fail2ban_jails_are_mail_not_web():
    out = render_role_template("fail2ban", "jail.local.j2")
    assert "[sshd]" in out
    assert "port = 666" in out
    assert "[postfix]" in out
    assert "[postfix-sasl]" in out
    assert "[dovecot]" in out
    assert "[mailpanel-auth]" in out
    assert "port = 443" in out
    assert "backend = systemd" in out
    assert "banaction = ufw" in out
    assert "198.51.100.20" in out
    assert "[traefik-auth]" not in out
    assert "[traefik-scan]" not in out
    assert "traefik" not in out.lower()


@pytest.mark.unit
def test_fail2ban_role_has_no_traefik_filters(repo_root: Path):
    templates = list((repo_root / "ansible/roles/fail2ban/templates").iterdir())
    names = {p.name for p in templates}
    assert names == {"jail.local.j2"}
    tasks = (repo_root / "ansible/roles/fail2ban/tasks/main.yml").read_text(encoding="utf-8")
    assert "traefik" not in tasks
    assert "state: restarted" in tasks
    defaults = (repo_root / "ansible/roles/fail2ban/defaults/main.yml").read_text(encoding="utf-8")
    assert "198.51.100.20" in defaults
