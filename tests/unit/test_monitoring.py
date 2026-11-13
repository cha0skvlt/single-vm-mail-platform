"""Local Prometheus + Grafana on loopback; no peer-host Loki."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.support.jinja import render_role_template


@pytest.mark.unit
def test_prometheus_scrapes_localhost_node(repo_root: Path):
    out = render_role_template("monitoring", "prometheus.yml.j2")
    assert 'targets: ["127.0.0.1:9100"]' in out
    assert 'targets: ["127.0.0.1:9154"]' in out
    assert "178.72.149.252" not in out


@pytest.mark.unit
def test_grafana_subpath_and_loopback():
    out = render_role_template("monitoring", "grafana.ini.j2")
    assert "http_addr = 127.0.0.1" in out
    assert "domain = mail.example.com" in out
    assert "root_url = https://mail.example.com/grafana/" in out
    assert "serve_from_sub_path = true" in out
    assert "allow_sign_up = false" in out
    assert "admin_password = grafsecret" in out
    assert "preinstall = prometheus loki" in out
    assert "preinstall_async = false" in out
    assert "disable_login_form = true" in out
    assert "[auth.proxy]" in out
    assert "enable_login_token = true" in out
    assert "whitelist = 127.0.0.1" in out
    assert "auto_assign_org_role = Admin" in out


@pytest.mark.unit
def test_exporters_bind_localhost(repo_root: Path):
    tasks = (repo_root / "ansible/roles/monitoring/tasks/main.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:9100" in tasks
    assert "127.0.0.1:9090" in tasks
    assert "127.0.0.1:9154" in tasks or "MAIL_METRICS_PORT=9154" in (
        repo_root / "ansible/roles/monitoring/templates/mail-metrics.service.j2"
    ).read_text(encoding="utf-8")
    assert "http_listen_address: 127.0.0.1" in render_role_template("monitoring", "loki-config.j2")
    assert "loki_push_url" not in tasks
    assert "178.72.149.252" not in tasks
    assert "grafana" in tasks
    assert "prometheus" in tasks
    assert "mail-metrics" in tasks
    assert "promtail" in tasks
    assert "delegate_to: localhost" in tasks
    assert "dl.grafana.com" in (
        repo_root / "ansible/roles/monitoring/defaults/main.yml"
    ).read_text(encoding="utf-8")
    assert "apt.grafana.com" not in tasks


@pytest.mark.unit
def test_group_vars_have_no_peer_metrics(repo_root: Path):
    text = (repo_root / "ansible/group_vars/all.yml").read_text(encoding="utf-8")
    assert "peer_host_ip" not in text
    assert "loki_push_url" not in text
    assert "MAIL_ADMIN_USER" in text


@pytest.mark.unit
def test_grafana_has_mail_and_server_dashboards(repo_root: Path):
    dash = repo_root / "ansible/roles/monitoring/files/dashboards"
    names = {p.name for p in dash.iterdir()}
    assert names == {"server.json", "mail.json", "mail-logs.json"}
    mail = (dash / "mail.json").read_text(encoding="utf-8")
    assert "mail_postfix_status_total" in mail
    assert "mail_dovecot_pop3_login_total" in mail
    logs = (dash / "mail-logs.json").read_text(encoding="utf-8")
    assert '{job=\\"mail\\"}' in logs or '{job="mail"}' in logs
    ds = render_role_template("monitoring", "grafana-datasource.yml.j2")
    assert "uid: loki" in ds
    assert "uid: prometheus" in ds
    assert "deleteDatasources:" in ds
    assert "127.0.0.1:3100" in ds
