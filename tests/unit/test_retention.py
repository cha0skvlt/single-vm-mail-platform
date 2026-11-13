"""Retention: delete only downloaded (SEEN) mail; unseen stays."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_cleanup_script_expunges_seen_only(repo_root: Path):
    script = (repo_root / "ansible/roles/mail/files/mail-cleanup.sh").read_text(encoding="utf-8")
    assert "doveadm expunge -A mailbox INBOX SEEN savedbefore" in script
    assert "UNSEEN" not in script
    assert "${MAIL_RETENTION_DAYS:-30}" in script


@pytest.mark.unit
def test_cleanup_timer_is_daily(repo_root: Path):
    timer = (repo_root / "ansible/roles/mail/files/mail-cleanup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer
    unit = render_role_template("mail", "mail-cleanup.service.j2")
    assert "MAIL_RETENTION_DAYS=30" in unit
    assert "ExecStart=/usr/local/sbin/mail-cleanup.sh" in unit
