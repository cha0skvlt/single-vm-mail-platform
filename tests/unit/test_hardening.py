"""Host hardening: no Docker, ufw mirrors SG including 443, secrets stay out of git."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.unit
def test_playbook_roles_are_mail_and_panel(repo_root: Path):
    playbook = yaml.safe_load((repo_root / "ansible/playbook.yml").read_text(encoding="utf-8"))
    roles = playbook[0]["roles"]
    assert roles == ["base", "fail2ban", "mail", "dkim", "monitoring", "panel"]
    assert "docker" not in roles
    roles_dir = {p.name for p in (repo_root / "ansible/roles").iterdir() if p.is_dir()}
    assert roles_dir == {"base", "fail2ban", "mail", "dkim", "monitoring", "panel"}


@pytest.mark.unit
def test_ufw_ports_match_mail_sg(repo_root: Path):
    defaults = yaml.safe_load(
        (repo_root / "ansible/roles/base/defaults/main.yml").read_text(encoding="utf-8")
    )
    ports = [str(p) for p in defaults["ufw_allowed_tcp_ports"]]
    assert ports == ["{{ ssh_port }}", "25", "443", "465", "995"]
    assert "80" not in ports
    assert "28000" not in ports
    paired = defaults["ufw_allowed_from_hosts"]
    assert len(paired) == 1
    assert paired[0]["from"] == "{{ ess_milter_host }}"
    assert str(paired[0]["port"]) == "{{ ess_milter_port }}"
    assert paired[0]["proto"] == "tcp"
    assert paired[0]["comment"] == "ess-milter"


@pytest.mark.unit
def test_base_installs_rsyslog_not_docker(repo_root: Path):
    tasks = (repo_root / "ansible/roles/base/tasks/main.yml").read_text(encoding="utf-8")
    assert "rsyslog" in tasks
    assert "docker" not in tasks.lower()
    assert "unattended-upgrades" in tasks
    assert "{{ timezone }}" in tasks
    group_vars = (repo_root / "ansible/group_vars/all.yml").read_text(encoding="utf-8")
    assert "timezone:" in group_vars
    assert "SystemMaxUse=500M" in tasks
    assert "/etc/systemd/journald.conf.d" in tasks
    assert "ufw allow from" in tasks
    assert "ufw_allowed_from_hosts" in tasks
    assert "ufw allow out to" not in tasks


@pytest.mark.unit
def test_no_docker_traefik_or_loki_stack(repo_root: Path):
    forbidden_names = ("docker-compose", "traefik", "loki.yml")
    for name in forbidden_names:
        matches = list(repo_root.rglob(f"*{name}*"))
        matches = [p for p in matches if ".terraform" not in p.parts and "__pycache__" not in p.parts]
        assert matches == []
    assert not (repo_root / "app").exists()
