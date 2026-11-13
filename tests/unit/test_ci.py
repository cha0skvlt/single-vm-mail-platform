"""GitHub CI: checks only — this template never deploys."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.unit
def test_workflow_runs_checks_and_never_deploys(repo_root: Path):
    path = repo_root / ".github/workflows/ci.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    assert set(jobs) == {"secret-scan", "test-unit", "test-service", "terraform"}
    text = path.read_text(encoding="utf-8")
    assert "terraform apply" not in text
    assert "ansible-playbook" not in text
    assert "make test-quick" in text
    assert "make test-service" in text
    assert "make fmt" in text
    assert "make validate" in text


@pytest.mark.unit
def test_workflow_has_no_cloud_credentials(repo_root: Path):
    text = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for forbidden in (
        "SEL_",
        "DEPLOY_SSH_KEY",
        "MAIL_TLS_KEY",
        "MAIL_DKIM_PRIVATE",
        "APP_ENV",
    ):
        assert forbidden not in text
    assert "This template never deploys." in text
