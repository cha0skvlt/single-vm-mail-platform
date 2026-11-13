"""OpenDKIM: localhost milter only, key from secret, fail if missing."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_opendkim_conf_localhost_socket():
    out = render_role_template("dkim", "opendkim.conf.j2")
    assert "Mode                    sv" in out
    assert "Socket                  inet:8891@127.0.0.1" in out
    assert "Domain                  example.com" in out
    assert "Selector                mail" in out
    assert "KeyFile                 /etc/opendkim/keys/example.com/mail.private" in out
    assert "MacroList               {auth_type}" in out


@pytest.mark.unit
def test_dkim_role_requires_local_key(repo_root: Path):
    tasks = (repo_root / "ansible/roles/dkim/tasks/main.yml").read_text(encoding="utf-8")
    assert "dkim/{{ dkim_selector }}.private" in tasks
    assert "when: not dkim_local_key.stat.exists" in tasks
    assert "inet:8891@127.0.0.1" in tasks
