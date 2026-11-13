"""Smoke checks mail ports plus panel HTTPS on 443."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_smoke_covers_mail_and_https(repo_root: Path):
    script = (repo_root / "scripts/smoke-mail.sh").read_text(encoding="utf-8")
    assert 'check_tcp 25 "smtp"' in script
    assert 'check_tcp 443 "https"' in script
    assert 'check_tcp 465 "smtps"' in script
    assert 'check_tcp 995 "pop3s"' in script
    assert "check_tls 443" in script
    assert "check_tls 465" in script
    assert "check_tls 995" in script
    assert "mail.example.com" in script
    assert "80" not in script
    assert "587" not in script
    assert "993" not in script
