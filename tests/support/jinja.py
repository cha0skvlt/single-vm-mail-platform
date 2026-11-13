"""Render Ansible Jinja templates without ansible-core."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[2]

MAIL_DEFAULTS = {
    "hostname": "mail",
    "mail_fqdn": "mail.example.com",
    "mail_domain": "example.com",
    "vmail_home": "/var/vmail",
    "vmail_user": "vmail",
    "vmail_group": "vmail",
    "vmail_uid": 5000,
    "tls_cert": "/etc/ssl/mail/fullchain.pem",
    "tls_key": "/etc/ssl/mail/privkey.pem",
    "mail_retention_days": 30,
    "dkim_selector": "mail",
    "dkim_keyfile": "/etc/opendkim/keys/example.com/mail.private",
    "ssh_port": 666,
    "panel_user": "mailpanel",
    "panel_root": "/opt/mail/panel",
    "panel_db_dir": "/var/lib/mailpanel",
    "panel_bind": "127.0.0.1",
    "panel_port": 8080,
    "mail_admin_user": "admin",
    "mail_admin_password": "secret",
    "mail_session_secret": "session",
    "grafana_admin_user": "admin",
    "grafana_admin_password": "grafsecret",
    "fail2ban_ignoreip": ["127.0.0.1/8", "::1", "198.51.100.20"],
    "postfix_rbl_zones": ["zen.spamhaus.org", "bl.spamcop.net"],
    "ess_milter_host": "",
    "ess_milter_port": 28000,
}


def render_role_template(role: str, name: str, **extra: object) -> str:
    env = Environment(
        loader=FileSystemLoader(REPO_ROOT / "ansible/roles" / role / "templates"),
        autoescape=False,
        keep_trailing_newline=True,
    )
    ctx = {**MAIL_DEFAULTS, **extra}
    return env.get_template(name).render(**ctx)
