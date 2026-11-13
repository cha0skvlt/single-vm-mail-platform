"""Secrets and passwords must not be committed."""

from __future__ import annotations

from pathlib import Path

import pytest

SECRET_PATHS = (
    "ssl/privkey.pem",
    "ssl/fullchain.pem",
    "data/mail_users.csv",
    "keys/ci_deploy",
    "ansible/inventory.ini",
    "dkim/mail.private",
    "terraform/terraform.tfvars",
    "terraform/s3-backend.env",
    ".panel-creds",
)


@pytest.mark.unit
def test_gitignore_covers_mail_secrets(repo_root: Path):
    gi = (repo_root / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "ssl/",
        "data/*.csv",
        "keys/ci_deploy",
        "ansible/inventory.ini",
        "dkim/*.private",
        "terraform/*.tfvars",
        "terraform/s3-backend.env",
        ".panel-creds",
    ):
        assert pattern in gi


@pytest.mark.unit
def test_repo_has_no_materialized_secrets(repo_root: Path):
    for rel in SECRET_PATHS:
        assert not (repo_root / rel).exists(), f"secret materialized: {rel}"
    assert (repo_root / "keys/deploy.pub").is_file()


@pytest.mark.unit
def test_gitleaks_allowlist_is_public_only(repo_root: Path):
    text = (repo_root / ".gitleaks.toml").read_text(encoding="utf-8")
    assert "example\\.(com|net|org)" in text
    assert "203\\.0\\.113" in text
    for forbidden in ("privkey", "mail_users.csv", "keys/ci_deploy", "terraform.tfvars"):
        assert forbidden not in text
