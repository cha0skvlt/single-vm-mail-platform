"""Inventory contract: deploy@666, group mail, no SSH 22."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_INV_LINE = re.compile(
    r"^vm\s+ansible_host=(?P<host>\S+)\s+ansible_user=(?P<user>\S+)\s+ansible_port=(?P<port>\d+)\s*$"
)


def _parse_example(text: str) -> tuple[str, str, str, str]:
    group = ""
    host = user = port = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
            continue
        match = _INV_LINE.match(stripped)
        if match:
            host, user, port = match.group("host", "user", "port")
    return group, host, user, port


@pytest.mark.unit
def test_inventory_example_contract(repo_root: Path):
    text = (repo_root / "ansible/inventory.ini.example").read_text(encoding="utf-8")
    group, host, user, port = _parse_example(text)
    assert group == "mail"
    assert host == "YOUR_PUBLIC_IP"
    assert user == "deploy"
    assert port == "666"


@pytest.mark.unit
def test_inventory_example_rejects_ssh_22(repo_root: Path):
    text = (repo_root / "ansible/inventory.ini.example").read_text(encoding="utf-8")
    assert "ansible_port=22" not in text
    assert "ansible_port=666" in text


@pytest.mark.unit
def test_bootstrap_writes_same_inventory_shape(repo_root: Path):
    script = (repo_root / "scripts/ci-deploy-bootstrap.sh").read_text(encoding="utf-8")
    assert "[mail]" in script
    assert "ansible_user=deploy" in script
    assert "ansible_port=666" in script
    assert "ansible_host=${DEPLOY_HOST}" in script
