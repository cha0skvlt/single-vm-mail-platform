"""Diagnostic bundle from a mail host."""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

COMMANDS: tuple[tuple[str, list[str]], ...] = (
    (
        "systemctl-status.txt",
        [
            "systemctl",
            "status",
            "postfix",
            "dovecot",
            "opendkim",
            "nginx",
            "mailpanel",
            "--no-pager",
        ],
    ),
    ("postfix.txt", ["postfix", "-n"]),
    ("dovecot.txt", ["dovecot", "-n"]),
    (
        "journal.txt",
        [
            "journalctl",
            "-u",
            "postfix",
            "-u",
            "dovecot",
            "-u",
            "opendkim",
            "-n",
            "200",
            "--no-pager",
        ],
    ),
)


def collect(out_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / f"mail-diagnostic-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, cmd in COMMANDS:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                body = proc.stdout + proc.stderr
            except (OSError, subprocess.TimeoutExpired) as exc:
                body = f"error: {exc}\n"
            (tmp_path / name).write_text(body, encoding="utf-8")
        with tarfile.open(bundle, "w:gz") as tar:
            for item in sorted(tmp_path.iterdir()):
                tar.add(item, arcname=item.name)
    return bundle
