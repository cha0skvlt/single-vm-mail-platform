"""mail-autoreply-expire: expired windows are switched off for good, pending ones activated."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def panel_db(tmp_path: Path, monkeypatch):
    """Isolated panel db module: patched db_path, restored sys.modules."""
    db_path = tmp_path / "users.db"
    panel = Path(__file__).resolve().parents[2] / "panel"
    if str(panel) not in sys.path:
        sys.path.insert(0, str(panel))
    saved = {name: sys.modules.pop(name, None) for name in ("db", "users", "autoreplies")}
    import db as db_mod

    monkeypatch.setattr(db_mod, "db_path", lambda: db_path)
    yield db_mod
    for name, mod in saved.items():
        if mod is not None:
            sys.modules[name] = mod
        else:
            sys.modules.pop(name, None)


def _make_db(db_mod, db_path: Path) -> None:
    with db_mod.session() as conn:
        conn.execute(
            "INSERT INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
            ("gone", "gone@example.com", "x", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
            ("soon", "soon@example.com", "x", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO users (local, email, password_hash, created_at, updated_at) VALUES (?,?,?,?,?)",
            ("live", "live@example.com", "x", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO autoreplies (local, body, updated_at, start_date, end_date) VALUES (?,?,?,?,?)",
            ("gone", "bye", "2026-01-01T00:00:00Z", "2026-10-01", "2026-10-05"),
        )
        conn.execute(
            "INSERT INTO autoreplies (local, body, updated_at, start_date, end_date) VALUES (?,?,?,?,?)",
            ("soon", "wait", "2026-01-01T00:00:00Z", "2099-11-01", "2099-11-10"),
        )
        conn.execute(
            "INSERT INTO autoreplies (local, body, updated_at, start_date, end_date) VALUES (?,?,?,?,?)",
            ("live", "hi", "2026-01-01T00:00:00Z", "2026-10-01", "2026-12-31"),
        )


def _run_expire(tmp_path: Path, db_path: Path, fake_sync: Path) -> subprocess.CompletedProcess:
    script = (
        Path(__file__).resolve().parents[2]
        / "ansible/roles/mail/files/mail-autoreply-expire.py"
    )
    env = {
        "MAILPANEL_DB": str(db_path),
        "MAIL_AUTOREPLY_SYNC": str(fake_sync),
    }
    import os

    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, str(script)],
        env=full_env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.unit
def test_expire_deletes_expired_and_activates_pending(tmp_path: Path, panel_db):
    db_path = tmp_path / "users.db"
    _make_db(panel_db, db_path)
    fake_sync = tmp_path / "fake-sync"
    calls = tmp_path / "calls.log"
    fake_sync.write_text(
        "#!/bin/sh\n"
        f"echo \"$1|$(cat)\" >> \"{calls}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    import os

    os.chmod(fake_sync, 0o755)

    proc = _run_expire(tmp_path, db_path, fake_sync)
    assert proc.returncode == 0, proc.stderr or proc.stdout

    log = calls.read_text(encoding="utf-8").splitlines()
    # expired: cleared with empty body
    assert "gone|" in log
    # pending start not yet arrived: nothing for "soon"
    assert not any(line.startswith("soon|") for line in log)
    # live window already active: expire re-syncs it (idempotent self-heal
    # in case the sieve file was lost)
    assert "live|hi" in log

    # expired row is gone from the db — switched off FOR GOOD
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT local FROM autoreplies").fetchall()
    finally:
        conn.close()
    assert sorted(r[0] for r in rows) == ["live", "soon"]


@pytest.mark.unit
def test_expire_activates_arrived_start(tmp_path: Path, panel_db):
    db_path = tmp_path / "users.db"
    _make_db(panel_db, db_path)
    # "soon" window moved into the past-but-active range: start arrived, end not passed
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE autoreplies SET start_date = '2026-10-01', end_date = '2026-12-31' WHERE local = 'soon'"
    )
    conn.commit()
    conn.close()

    fake_sync = tmp_path / "fake-sync"
    calls = tmp_path / "calls.log"
    fake_sync.write_text(
        "#!/bin/sh\n"
        f"echo \"$1|$(cat)\" >> \"{calls}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    import os

    os.chmod(fake_sync, 0o755)

    proc = _run_expire(tmp_path, db_path, fake_sync)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    log = calls.read_text(encoding="utf-8").splitlines()
    assert "soon|wait" in log


@pytest.mark.unit
def test_expire_missing_db_fails_cleanly(tmp_path: Path):
    fake_sync = tmp_path / "fake-sync"
    fake_sync.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    import os

    os.chmod(fake_sync, 0o755)
    proc = _run_expire(tmp_path, tmp_path / "missing.db", fake_sync)
    assert proc.returncode == 1
    assert "db not found" in proc.stderr


@pytest.mark.unit
def test_expire_timer_is_hourly(repo_root: Path):
    timer = (
        repo_root / "ansible/roles/mail/files/mail-autoreply-expire.timer"
    ).read_text(encoding="utf-8")
    assert "OnCalendar=hourly" in timer
    assert "Persistent=true" in timer
    service = (
        repo_root / "ansible/roles/mail/files/mail-autoreply-expire.service"
    ).read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/python3 /usr/local/sbin/mail-autoreply-expire" in service
    tasks = (repo_root / "ansible/roles/mail/tasks/main.yml").read_text(encoding="utf-8")
    assert "mail-autoreply-expire" in tasks
