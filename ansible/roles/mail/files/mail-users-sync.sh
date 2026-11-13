#!/usr/bin/env bash
# Rebuild Dovecot passwd-file + Postfix vmailbox from SQLite (atomic replace).
# virtual stays postmaster-only; redirects live in a separate map.
set -euo pipefail

DB="${MAILPANEL_DB:-/var/lib/mailpanel/users.db}"
DOMAIN="${MAIL_DOMAIN:-example.com}"
USERS_FILE="${USERS_FILE:-/etc/dovecot/users}"
VMAILBOX_FILE="${VMAILBOX_FILE:-/etc/postfix/vmailbox}"
VIRTUAL_FILE="${VIRTUAL_FILE:-/etc/postfix/virtual}"
VIRTUAL_REDIRECT_FILE="${VIRTUAL_REDIRECT_FILE:-${VIRTUAL_FILE}_redirect}"

if [[ ! -f "${DB}" ]]; then
  echo "error: ${DB} missing" >&2
  exit 1
fi

python3 - "$DB" "$DOMAIN" "$USERS_FILE" "$VMAILBOX_FILE" "$VIRTUAL_FILE" "$VIRTUAL_REDIRECT_FILE" <<'PY'
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict

db, domain, users_file, vmailbox_file, virtual_file, redirect_file = sys.argv[1:7]
conn = sqlite3.connect(db)
rows = conn.execute("SELECT local, email, password_hash FROM users ORDER BY local").fetchall()
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
conn.close()

users, vmbox = [], []
for local, email, hashed in rows:
    users.append(f"{email}:{hashed}::::::")
    if local.lower() != email.lower():
        users.append(f"{local}:{hashed}::::::")
    vmbox.append(f"{email}\t{domain}/{local}/Maildir/")

by_src: dict[str, list[str]] = defaultdict(list)
for src, dest in redirs:
    if dest not in by_src[src]:
        by_src[src].append(dest)

redir_lines = []
for src in sorted(by_src):
    dests = ", ".join(f"{name}@{domain}" for name in [src, *by_src[src]])
    redir_lines.append(f"{src}@{domain}\t{dests}")

def atomic_write(path: str, text: str, mode: int) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

atomic_write(users_file, "\n".join(users) + ("\n" if users else ""), 0o640)
atomic_write(vmailbox_file, "\n".join(vmbox) + ("\n" if vmbox else ""), 0o644)
atomic_write(virtual_file, f"postmaster@{domain}\tpostmaster@{domain}\n", 0o644)
atomic_write(redirect_file, "\n".join(redir_lines) + ("\n" if redir_lines else ""), 0o644)
print(f"synced {len(vmbox)} mailboxes {len(redir_lines)} redirects")
PY

if [[ "${SKIP_POSTMAP:-}" != "1" ]]; then
  chown root:dovecot "${USERS_FILE}" || true
  postmap "${VMAILBOX_FILE}"
  postmap "${VIRTUAL_FILE}"
  postmap "${VIRTUAL_REDIRECT_FILE}"
fi
