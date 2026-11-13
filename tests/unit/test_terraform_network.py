"""Cloud SG: public mail+ssh+https, no exporter holes, no :80, no external milter."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_public_ports_are_mail_ssh_and_https(repo_root: Path):
    text = (repo_root / "terraform/network.tf").read_text(encoding="utf-8")
    assert "public_tcp_ports = [var.ssh_port, 25, 443, 465, 995]" in text
    assert "port_range_min    = 80" not in text
    assert "port_range_min    = 3100" not in text
    assert "port_range_min    = 9100" not in text
    assert "port_range_min    = 9154" not in text
    assert "peer_host_ip" not in text
    assert "ess_milter" not in text
    assert "28000" not in text
    assert "direction         = \"egress\"" not in text


@pytest.mark.unit
def test_no_peer_scrape_variable(repo_root: Path):
    variables = (repo_root / "terraform/variables.tf").read_text(encoding="utf-8")
    assert "peer_host_ip" not in variables


@pytest.mark.unit
def test_lifecycle_guards(repo_root: Path):
    network = (repo_root / "terraform/network.tf").read_text(encoding="utf-8")
    compute = (repo_root / "terraform/compute.tf").read_text(encoding="utf-8")
    assert "prevent_destroy = true" in network
    assert "prevent_destroy = true" in compute
    assert "flavor_id         = var.flavor_id" in compute


@pytest.mark.unit
def test_cloud_init_ssh_port_is_variable(repo_root: Path):
    text = (repo_root / "terraform/cloud-init.tf").read_text(encoding="utf-8")
    assert "Port ${var.ssh_port}" in text
    assert "PermitRootLogin no" in text
    assert "PasswordAuthentication no" in text
    assert "name: deploy" in text
