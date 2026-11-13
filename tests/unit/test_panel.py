"""Panel is a prod-status fork: mailsystem login, MAILBOARD, users CRUD chrome."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_login_is_mailsystem(repo_root: Path):
    login = (repo_root / "panel/static/login.html").read_text(encoding="utf-8")
    assert "mailsystem" in login
    assert "Production" not in login
    assert "/img/mark.svg" in login
    assert "/img/favicon-mail.svg" in login
    assert 'action="/login"' in login
    assert "theme-boot.js" in login


@pytest.mark.unit
def test_board_is_mailboard_one_column(repo_root: Path):
    index = (repo_root / "panel/static/index.html").read_text(encoding="utf-8")
    assert "MAIL</span>" in index
    assert "BOARD</span>" in index
    assert "Mail" in index
    assert "status-beacon--ok" in index
    assert 'href="/img/favicon-mail.svg"' in index
    assert 'href="/grafana/"' in index
    css = (repo_root / "panel/static/css/panel-grid.css").read_text(encoding="utf-8")
    assert "polygon(50% 6.7%, 100% 93.3%, 0% 93.3%)" in css
    assert "border-radius: 50%" not in css
    fav = (repo_root / "panel/static/js/panel/favicon.js").read_text(encoding="utf-8")
    assert "trianglePath" in fav
    assert "status-favicon" in fav
    assert "Traefik" not in index
    assert "phpMyAdmin" not in index
    assert "Diagnostic" not in index
    assert "Add user" in index
    assert "users-body" in index
    assert 'minlength="6"' in index
    assert 'id="pw-modal"' in index
    assert 'id="rd-modal"' in index
    assert 'id="ar-modal"' in index
    assert "At least 6 characters" in index
    assert "Password changed" in index
    assert "Redirects saved" in index
    assert "Autoreply saved" in index
    users_css = (repo_root / "panel/static/css/users-table.css").read_text(encoding="utf-8")
    assert "tbody tr:hover" in users_css


@pytest.mark.unit
def test_nginx_443_only_and_grafana_subpath(repo_root: Path):
    out = render_role_template("panel", "nginx.conf.j2")
    assert "listen 443 ssl" in out
    assert "listen 80" not in out
    assert "server_name mail.example.com" in out
    assert "location = /grafana/api/live/ws" in out
    assert "location /grafana/api/" in out
    assert "location /grafana/" in out
    assert out.count("auth_request /auth/verify;") == 3
    assert "internal;" in out
    assert out.count("X-WEBAUTH-USER $panel_user") == 3
    assert "proxy_set_header Upgrade $http_upgrade;" in out
    assert "proxy_set_header Connection $connection_upgrade;" in out
    assert "proxy_read_timeout 3600s;" in out
    assert "@grafana_unauthorized" in out
    assert "return 401;" in out
    assert "@grafana_need_login" in out
    assert "return 302 /login;" in out
    upgrade_map = (
        repo_root / "ansible/roles/panel/files/grafana-upgrade-map.conf"
    ).read_text(encoding="utf-8")
    assert "map $http_upgrade $connection_upgrade" in upgrade_map
    assert "127.0.0.1:3000" in out
    assert "127.0.0.1:8080" in out
    assert "proxy_set_header X-Real-IP $remote_addr;" in out


@pytest.mark.unit
def test_panel_auth_cookie_name(repo_root: Path):
    auth = (repo_root / "panel/auth.py").read_text(encoding="utf-8")
    assert 'COOKIE_NAME = "mail_session"' in auth
    assert "MAIL_ADMIN_USER" in auth
    assert "MAIL_SESSION_SECRET" in auth
    assert "PROD_" not in auth


@pytest.mark.unit
def test_mail_role_no_oneshot_users_guard(repo_root: Path):
    tasks = (repo_root / "ansible/roles/mail/tasks/main.yml").read_text(encoding="utf-8")
    assert "creates: /etc/dovecot/users" not in tasks
    assert "mail-users-sync" in tasks
    assert "mail-autoreply-sync" in tasks
    assert "mail-users-import" in tasks
    assert "Upload accounts CSV" not in tasks
    assert "/root/mail_users.csv" not in tasks
    assert "virtual_redirect" in tasks
    assert "modification_time: preserve" in tasks
    assert "creates: /etc/postfix/virtual_redirect.db" in tasks
    handlers = (repo_root / "ansible/roles/mail/handlers/main.yml").read_text(encoding="utf-8")
    assert "Reload postfix" in handlers
    main_tasks = (repo_root / "ansible/roles/mail/tasks/main.yml").read_text(encoding="utf-8")
    assert "notify: Reload postfix" in main_tasks


@pytest.mark.unit
def test_panel_copy_sets_directory_mode(repo_root: Path):
    tasks = (repo_root / "ansible/roles/panel/tasks/main.yml").read_text(encoding="utf-8")
    assert "directory_mode: \"0755\"" in tasks
    assert "src: \"{{ playbook_dir }}/../panel/\"" in tasks
    sudoers = (repo_root / "ansible/roles/panel/templates/sudoers.j2").read_text(encoding="utf-8")
    assert "mail-users-sync" in sudoers
    assert "mail-autoreply-sync" in sudoers


@pytest.mark.unit
def test_board_encodes_user_in_api_path(repo_root: Path):
    js = (repo_root / "panel/static/js/panel/main.js").read_text(encoding="utf-8")
    assert "encodeURIComponent(local)" in js
    assert "escapeHtml(local)" in js
    assert "/api/health" in js
    assert "updateStatusFavicon" in js
    assert "prompt(" not in js
    assert "openPasswordModal" in js
    assert "openRedirectModal" in js
    assert "openAutoreplyModal" in js
    assert "data-action=\"autoreply\"" in js
    assert "data-action=\"redirect\"" in js
    pw = js.index('data-action="password"')
    ar = js.index('data-action="autoreply"')
    rd = js.index('data-action="redirect"')
    assert pw < ar < rd
    assert "rdLoaded" in js
    assert "!rdLoaded" in js
    assert "MIN_PASSWORD_LEN = 6" in js


@pytest.mark.unit
def test_mail_health_reports_down_when_unit_fails(repo_root: Path, monkeypatch):
    import sys

    panel = str(repo_root / "panel")
    if panel not in sys.path:
        sys.path.insert(0, panel)
    sys.modules.pop("server", None)
    import server

    monkeypatch.setattr(server, "_unit_is_active", lambda name: name != "opendkim")
    data = server.mail_health()
    assert data["ok"] is False
    assert data["overall"] == "down"
    assert [c["name"] for c in data["checks"]] == ["postfix", "dovecot", "opendkim"]
