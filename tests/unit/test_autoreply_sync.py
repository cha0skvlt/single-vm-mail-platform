"""mail-autoreply-sync writes only sieve files for one local."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.runners import run


@pytest.mark.unit
def test_autoreply_sync_writes_sieve_not_maps(repo_root: Path, tmp_path: Path):
    vmail = tmp_path / "vmail"
    users_map = tmp_path / "etc/dovecot/users"
    users_map.parent.mkdir(parents=True, exist_ok=True)
    users_map.write_text("keep:hash::::::\n", encoding="utf-8")
    before = users_map.read_text(encoding="utf-8")
    maildir = vmail / "example.com" / "finotdel" / "Maildir"
    maildir.mkdir(parents=True, exist_ok=True)
    (maildir / "cur").mkdir()
    msg = maildir / "cur" / "msg"
    msg.write_text("mail", encoding="utf-8")
    script = repo_root / "ansible/roles/mail/files/mail-autoreply-sync.sh"
    proc = run(
        ["bash", "-c", f"printf '%s' 'Out of office' | bash '{script}' finotdel"],
        cwd=tmp_path,
        env={
            "MAIL_DOMAIN": "example.com",
            "VMAIL_HOME": str(vmail),
            "SKIP_CHOWN": "1",
            "SKIP_SIEVEC": "1",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    home = vmail / "example.com" / "finotdel"
    sieve = (home / "sieve" / "autoreply.sieve").read_text(encoding="utf-8")
    assert 'require ["vacation"]' in sieve
    assert ":days 1" in sieve
    assert "finotdel@example.com" in sieve
    assert "Out of office" in sieve
    assert (home / ".dovecot.sieve").is_symlink()
    assert users_map.read_text(encoding="utf-8") == before
    assert msg.read_text(encoding="utf-8") == "mail"
    assert (home / "Maildir").is_dir()


@pytest.mark.unit
def test_autoreply_sync_clear_keeps_maildir(repo_root: Path, tmp_path: Path):
    vmail = tmp_path / "vmail"
    home = vmail / "example.com" / "finotdel"
    (home / "sieve").mkdir(parents=True)
    (home / "sieve" / "autoreply.sieve").write_text("old", encoding="utf-8")
    (home / ".dovecot.sieve").symlink_to("sieve/autoreply.sieve")
    (home / ".dovecot.lda-dupes").write_text("x", encoding="utf-8")
    maildir = home / "Maildir" / "cur"
    maildir.mkdir(parents=True)
    msg = maildir / "msg"
    msg.write_text("mail", encoding="utf-8")
    script = repo_root / "ansible/roles/mail/files/mail-autoreply-sync.sh"
    proc = run(
        ["bash", "-c", f"printf '' | bash '{script}' finotdel"],
        cwd=tmp_path,
        env={
            "MAIL_DOMAIN": "example.com",
            "VMAIL_HOME": str(vmail),
            "SKIP_CHOWN": "1",
            "SKIP_SIEVEC": "1",
        },
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert not (home / "sieve" / "autoreply.sieve").exists()
    assert not (home / ".dovecot.sieve").exists()
    assert not (home / ".dovecot.lda-dupes").exists()
    assert msg.read_text(encoding="utf-8") == "mail"


@pytest.mark.unit
def test_autoreply_sync_rejects_slash_login(repo_root: Path, tmp_path: Path):
    script = repo_root / "ansible/roles/mail/files/mail-autoreply-sync.sh"
    proc = run(
        ["bash", "-c", f"printf 'hi' | bash '{script}' '../etc'"],
        cwd=tmp_path,
        env={"VMAIL_HOME": str(tmp_path / "vmail"), "SKIP_CHOWN": "1", "SKIP_SIEVEC": "1"},
    )
    assert proc.returncode != 0
    assert not list((tmp_path / "vmail").glob("**/*")) if (tmp_path / "vmail").exists() else True


@pytest.mark.unit
def test_autoreply_sync_rejects_sieve_command(repo_root: Path, tmp_path: Path):
    script = repo_root / "ansible/roles/mail/files/mail-autoreply-sync.sh"
    proc = run(
        ["bash", "-c", f"printf '%s' 'redirect \"evil@x\"' | bash '{script}' finotdel"],
        cwd=tmp_path,
        env={
            "MAIL_DOMAIN": "example.com",
            "VMAIL_HOME": str(tmp_path / "vmail"),
            "SKIP_CHOWN": "1",
            "SKIP_SIEVEC": "1",
        },
    )
    assert proc.returncode != 0
    home = tmp_path / "vmail" / "example.com" / "finotdel"
    assert not (home / "sieve" / "autoreply.sieve").exists()
