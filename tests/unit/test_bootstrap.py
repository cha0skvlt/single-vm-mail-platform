"""CI bootstrap materializes secrets locally and does not print them."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.runners import run


@pytest.mark.unit
def test_bootstrap_requires_host_and_known_hosts(repo_root: Path, monkeypatch):
    monkeypatch.delenv("DEPLOY_HOST", raising=False)
    monkeypatch.delenv("DEPLOY_KNOWN_HOSTS", raising=False)
    proc = run(["bash", str(repo_root / "scripts/ci-deploy-bootstrap.sh")], cwd=repo_root)
    assert proc.returncode != 0
    assert "DEPLOY_HOST" in proc.stderr or "DEPLOY_KNOWN_HOSTS" in proc.stderr


@pytest.mark.unit
def test_bootstrap_writes_inventory_and_secret_files(repo_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    # Run from a copy of scripts so inventory lands in tmp? The script writes relative to repo.
    # Use a throwaway repo-shaped tree instead.
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts/_lib.sh").write_text(
        (repo_root / "scripts/_lib.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (work / "scripts/ci-deploy-bootstrap.sh").write_text(
        (repo_root / "scripts/ci-deploy-bootstrap.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    def pem(kind: str, body: str) -> str:
        # Assembled at runtime so no literal PEM header lives in the tree.
        return f"-----BEGIN {kind}-----\n{body}\n-----END {kind}-----\n"

    proc = run(
        ["bash", str(work / "scripts/ci-deploy-bootstrap.sh")],
        cwd=work,
        env={
            "HOME": str(tmp_path / "home"),
            "DEPLOY_HOST": "203.0.113.10",
            "DEPLOY_KNOWN_HOSTS": "[203.0.113.10]:666 ssh-ed25519 AAAA",
            "MAIL_USERS_CSV": "username,email,full_name,password,archived\nabramov,abramov@example.com,N,secret,yes\n",
            "MAIL_TLS_CERT": pem("CERTIFICATE", "X"),
            "MAIL_TLS_KEY": pem("PRIVATE KEY", "Y"),
            "MAIL_DKIM_PRIVATE": pem("RSA PRIVATE KEY", "Z"),
            "DKIM_SELECTOR": "mail",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "GdB192RO" not in proc.stdout
    assert "abramov@example.com" not in proc.stdout
    assert "BEGIN PRIVATE" not in proc.stdout
    assert "BEGIN RSA" not in proc.stdout
    inv = (work / "ansible/inventory.ini").read_text(encoding="utf-8")
    assert "[mail]" in inv
    assert "ansible_host=203.0.113.10" in inv
    assert "ansible_port=666" in inv
    assert (work / "data/mail_users.csv").is_file()
    assert (work / "ssl/fullchain.pem").is_file()
    assert (work / "ssl/privkey.pem").is_file()
    assert (work / "dkim/mail.private").is_file()
    assert oct((work / "ssl/privkey.pem").stat().st_mode)[-3:] == "600"
    known = (tmp_path / "home/.ssh/known_hosts").read_text(encoding="utf-8")
    assert "203.0.113.10" in known


@pytest.mark.unit
def test_bootstrap_normalizes_pem_newlines(repo_root: Path, tmp_path: Path):
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts/_lib.sh").write_text(
        (repo_root / "scripts/_lib.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (work / "scripts/ci-deploy-bootstrap.sh").write_text(
        (repo_root / "scripts/ci-deploy-bootstrap.sh").read_text(encoding="utf-8"), encoding="utf-8"
    )
    proc = run(
        ["bash", str(work / "scripts/ci-deploy-bootstrap.sh")],
        cwd=work,
        env={
            "HOME": str(tmp_path / "home"),
            "DEPLOY_HOST": "203.0.113.10",
            "DEPLOY_KNOWN_HOSTS": "[203.0.113.10]:666 ssh-ed25519 AAAA",
            "MAIL_TLS_CERT": "-----BEGIN CERTIFICATE-----\r\nX\r\n-----END CERTIFICATE-----",
            "MAIL_TLS_KEY": "-----BEGIN PRIVATE KEY-----\r\nY\r\n-----END PRIVATE KEY-----",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    cert = (work / "ssl/fullchain.pem").read_bytes()
    key = (work / "ssl/privkey.pem").read_bytes()
    assert cert.endswith(b"\n")
    assert key.endswith(b"\n")
    assert b"\r" not in cert
    assert b"\r" not in key
    assert b"-----END CERTIFICATE-----\n" in cert
