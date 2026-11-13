"""Dovecot 2.4: POP3S 995 only, virtual users, both login forms, Seen on RETR."""

from __future__ import annotations

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_dovecot_is_24_not_23():
    out = render_role_template("mail", "dovecot.conf.j2")
    assert out.splitlines()[0].startswith("dovecot_config_version") or "dovecot_config_version = 2.4.0" in out
    assert "dovecot_config_version = 2.4.0" in out
    assert "dovecot_storage_version = 2.4.0" in out
    assert "mail_location" not in out
    assert "auth_default_realm" not in out
    assert "disable_plaintext_auth" not in out
    assert "ssl_cert =" not in out
    assert "ssl_key =" not in out


@pytest.mark.unit
def test_dovecot_protocols_and_listeners():
    out = render_role_template("mail", "dovecot.conf.j2")
    assert "protocols {\n  pop3 = yes\n  lmtp = yes\n}" in out.replace("\r\n", "\n")
    assert "imap" not in out
    assert "port = 995" in out
    assert "ssl = yes" in out
    assert "inet_listener pop3 {\n    port = 0" in out.replace("\r\n", "\n")


@pytest.mark.unit
def test_dovecot_auth_accepts_bare_and_fqdn_login():
    out = render_role_template("mail", "dovecot.conf.j2")
    assert "auth_default_domain = example.com" in out
    assert "auth_username_format = %{user | lower}" in out
    assert "auth_username_format = %{user | username | lower}" in out
    assert "default_password_scheme = SSHA512" in out
    assert "auth_allow_cleartext = no" in out
    assert "ssl = required" in out
    assert "ssl_min_protocol = TLSv1.2" in out
    assert "ssl_server_cert_file = /etc/ssl/mail/fullchain.pem" in out
    assert "ssl_server_key_file = /etc/ssl/mail/privkey.pem" in out


@pytest.mark.unit
def test_dovecot_pop3_marks_seen_for_retention():
    out = render_role_template("mail", "dovecot.conf.j2")
    assert "pop3_no_flag_updates = no" in out


@pytest.mark.unit
def test_dovecot_lmtp_and_sasl_sockets():
    out = render_role_template("mail", "dovecot.conf.j2")
    assert "/var/spool/postfix/private/dovecot-lmtp" in out
    assert "/var/spool/postfix/private/auth" in out
    assert "mail_driver = maildir" in out
    assert "mail_home = /var/vmail/example.com/%{user | username}" in out
    assert "mail_path = ~/Maildir" in out
    assert "postmaster_address = postmaster@example.com" in out
    lmtp = out.split("protocol lmtp {", 1)[1].split("}", 1)[0]
    assert "sieve = yes" in lmtp
    assert "sieve_script personal" in out
    assert "type = personal" in out
    assert "active_path = ~/.dovecot.sieve" in out
    protocols = out.split("protocols {", 1)[1].split("}", 1)[0]
    assert "sieve = yes" not in protocols
    assert "managesieve" not in out.lower()
