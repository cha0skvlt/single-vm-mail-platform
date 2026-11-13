"""Render Postfix/Dovecot maps from the panel SQLite database.

The server-side twin of this logic is
``ansible/roles/mail/files/mail-users-sync.sh``; ``ops check-maps`` renders
locally and diffs the result against the deployed files.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Maps:
    users: str
    vmailbox: str
    virtual: str
    redirects: str


def _block(items: list[str]) -> str:
    return "\n".join(items) + ("\n" if items else "")


def render(db: Path, domain: str) -> Maps:
    if not db.is_file():
        raise FileNotFoundError(f"{db} missing")
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT local, email, password_hash FROM users ORDER BY local"
        ).fetchall()
        try:
            redirs = conn.execute(
                """
                SELECT r.src, r.dest
                FROM redirects r
                INNER JOIN users s ON s.local = r.src
                INNER JOIN users d ON d.local = r.dest
                WHERE r.src != r.dest
                ORDER BY r.src, r.dest
                """
            ).fetchall()
        except sqlite3.OperationalError:
            redirs = []
    finally:
        conn.close()

    users: list[str] = []
    vmbox: list[str] = []
    for local, email, hashed in rows:
        users.append(f"{email}:{hashed}::::::")
        if local.lower() != email.lower():
            users.append(f"{local}:{hashed}::::::")
        vmbox.append(f"{email}\t{domain}/{local}/Maildir/")

    by_src: dict[str, list[str]] = defaultdict(list)
    for src, dest in redirs:
        if dest not in by_src[src]:
            by_src[src].append(dest)

    redir_lines = [
        f"{src}@{domain}\t"
        + ", ".join(f"{name}@{domain}" for name in [src, *by_src[src]])
        for src in sorted(by_src)
    ]

    return Maps(
        users=_block(users),
        vmailbox=_block(vmbox),
        virtual=f"postmaster@{domain}\tpostmaster@{domain}\n",
        redirects=_block(redir_lines),
    )


def targets(
    *,
    users_file: Path,
    vmailbox_file: Path,
    virtual_file: Path,
    redirect_file: Path,
) -> tuple[tuple[Path, str], ...]:
    return (
        (users_file, "users"),
        (vmailbox_file, "vmailbox"),
        (virtual_file, "virtual"),
        (redirect_file, "redirects"),
    )


def write(
    rendered: Maps,
    *,
    users_file: Path,
    vmailbox_file: Path,
    virtual_file: Path,
    redirect_file: Path,
) -> None:
    for path, field in targets(
        users_file=users_file,
        vmailbox_file=vmailbox_file,
        virtual_file=virtual_file,
        redirect_file=redirect_file,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(getattr(rendered, field), encoding="utf-8")


def check(
    rendered: Maps,
    *,
    users_file: Path,
    vmailbox_file: Path,
    virtual_file: Path,
    redirect_file: Path,
) -> list[str]:
    problems: list[str] = []
    for path, field in targets(
        users_file=users_file,
        vmailbox_file=vmailbox_file,
        virtual_file=virtual_file,
        redirect_file=redirect_file,
    ):
        if not path.is_file():
            problems.append(f"missing {path}")
            continue
        if path.read_text(encoding="utf-8") != getattr(rendered, field):
            problems.append(f"stale {path}")
    return problems
