"""Render ansible/inventory.ini from terraform output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def render(
    host: str,
    *,
    port: int = 666,
    user: str = "deploy",
    group: str = "mail",
) -> str:
    return (
        f'# Group name = hostname ({group}); host alias "vm" avoids group/host name collision.\n'
        f"[{group}]\n"
        f"vm ansible_host={host} ansible_user={user} ansible_port={port}\n"
    )


def write(
    path: Path,
    host: str,
    *,
    port: int = 666,
    user: str = "deploy",
    group: str = "mail",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(host, port=port, user=user, group=group), encoding="utf-8")
    path.chmod(0o600)
    return path


def from_terraform(repo_root: Path) -> dict[str, str]:
    proc = subprocess.run(
        ["terraform", f"-chdir={repo_root / 'terraform'}", "output", "-json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    return {key: str(value.get("value", "")) for key, value in data.items()}
