"""Mail log classifier used by the Prometheus scraper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load(repo_root: Path):
    path = repo_root / "ansible/roles/monitoring/files/mail-metrics.py"
    spec = importlib.util.spec_from_file_location("mail_metrics", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_classify_postfix_dovecot_opendkim(repo_root: Path):
    mod = _load(repo_root)
    mod._counters.clear()
    lines = [
        "postfix/smtpd[1]: connect from mail.example[1.2.3.4]",
        "postfix/smtps/smtpd[2]: connect from client[5.6.7.8]",
        "postfix/smtp[3]: ABC: to=<a@b>, status=sent (250)",
        "postfix/smtpd[4]: NOQUEUE: reject: RCPT from x[9.9.9.9]: 554 blocked using zen.spamhaus.org",
        "dovecot: pop3-login: Login: user=<abramov>",
        "dovecot: pop3-login: Login aborted (auth_failed): user=<x>",
        "dovecot: lmtp(u): saved mail to INBOX",
        "opendkim[9]: ABC: DKIM verification successful",
    ]
    for line in lines:
        mod.classify(line)
    rendered = mod.render().decode()
    assert 'mail_postfix_connects_total{service="smtp"} 1.0' in rendered
    assert 'mail_postfix_connects_total{service="smtps"} 1.0' in rendered
    assert 'mail_postfix_status_total{status="sent"} 1.0' in rendered
    assert 'mail_postfix_status_total{status="rejected"} 1.0' in rendered
    assert "mail_postfix_rbl_reject_total 1.0" in rendered
    assert 'mail_dovecot_pop3_login_total{result="ok"} 1.0' in rendered
    assert 'mail_dovecot_pop3_login_total{result="fail"} 1.0' in rendered
    assert "mail_dovecot_lmtp_saved_total 1.0" in rendered
    assert 'mail_opendkim_verify_total{result="ok"} 1.0' in rendered
