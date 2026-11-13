"""Postfix: 25 inbound, 465 SMTPS+auth, no open relay, DKIM milter."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_main_cf_virtual_and_no_open_relay():
    out = render_role_template("mail", "main.cf.j2")
    assert "myhostname = mail.example.com" in out
    assert "myorigin = example.com" in out
    assert "smtp_helo_name = mail.example.com" in out
    assert "mydestination = localhost" in out
    assert "mynetworks = 127.0.0.0/8 [::1]/128" in out
    assert "virtual_mailbox_domains = example.com" in out
    assert "virtual_alias_maps = hash:/etc/postfix/virtual hash:/etc/postfix/virtual_redirect" in out
    assert "virtual_transport = lmtp:unix:private/dovecot-lmtp" in out
    assert "smtpd_sasl_type = dovecot" in out
    assert "permit_sasl_authenticated" in out
    assert "reject_unauth_destination" in out
    smtpd_milters = next(
        line for line in out.splitlines() if line.startswith("smtpd_milters =")
    )
    assert smtpd_milters == "smtpd_milters = inet:127.0.0.1:8891"
    assert "non_smtpd_milters = inet:127.0.0.1:8891" in out
    assert "milter_default_action = accept" in out
    assert "{auth_type}" in out
    assert "{auth_authen}" in out
    assert "smtpd_tls_protocols = >=TLSv1.2" in out


@pytest.mark.unit
def test_main_cf_rbl_and_manual_blacklist_order():
    out = render_role_template("mail", "main.cf.j2")
    assert "check_client_access cidr:/etc/postfix/client_blacklist" in out
    assert "reject_rbl_client zen.spamhaus.org" in out
    assert "reject_rbl_client bl.spamcop.net" in out
    sasl = out.index("permit_sasl_authenticated")
    unauth = out.index("reject_unauth_destination")
    rbl = out.index("reject_rbl_client")
    assert sasl < rbl
    assert unauth < rbl
    assert out.index("check_client_access") < rbl


@pytest.mark.unit
def test_client_blacklist_has_no_active_rejects(repo_root: Path):
    path = repo_root / "ansible/roles/mail/files/client_blacklist"
    assert path.is_file()
    active = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert active == []
    assert any("REJECT" in line for line in path.read_text(encoding="utf-8").splitlines())


@pytest.mark.unit
def test_master_cf_ports_and_smtps_auth():
    out = render_role_template("mail", "master.cf.j2")
    assert "smtp      inet" in out
    assert "smtps     inet" in out
    assert "smtpd_tls_wrappermode=yes" in out
    assert "smtpd_sasl_auth_enable=yes" in out
    assert "permit_sasl_authenticated,reject" in out
    assert "submission" not in out
    assert " 587 " not in out


@pytest.mark.unit
def test_mail_role_does_not_enable_imap_or_plain_pop(repo_root: Path):
    tasks = (repo_root / "ansible/roles/mail/tasks/main.yml").read_text(encoding="utf-8")
    assert "dovecot-imapd" not in tasks
    packages = (repo_root / "ansible/roles/mail/defaults/main.yml").read_text(encoding="utf-8")
    assert "dovecot-pop3d" in packages
    assert "dovecot-lmtpd" in packages
    assert "dovecot-sieve" in packages
    assert "dovecot-imapd" not in packages
