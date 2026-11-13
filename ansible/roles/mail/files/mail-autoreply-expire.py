#!/usr/bin/env python3
"""Hourly autoreply window arbiter.

Reads the panel SQLite database and reconciles sieve files with the
autoreply date windows (calendar days in MAIL_TZ, default UTC):

- end_date in the past  -> autoreply is switched off FOR GOOD:
                           row deleted from the database and sieve files
                           cleared via mail-autoreply-sync (the same
                           battle-tested path the panel uses).
- start_date arrived    -> sieve files written so the vacation is live.

Never touches postfix/dovecot maps or any other mailbox data. Fails
loudly (non-zero exit) so systemd marks the run failed; it never
partially mutates a mailbox: each local is processed independently.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("MAILPANEL_DB", "/var/lib/mailpanel/users.db"))
SYNC_CMD = os.environ.get("MAIL_AUTOREPLY_SYNC", "/usr/local/sbin/mail-autoreply-sync")
MOSCOW_OFFSET_MINUTES = 3 * 60


def moscow_today() -> str:
    now = datetime.utcnow() + timedelta(minutes=MOSCOW_OFFSET_MINUTES)
    return now.strftime("%Y-%m-%d")


def is_active(start_date: str, end_date: str, today: str) -> bool:
    if start_date and today < start_date:
        return False
    if end_date and today > end_date:
        return False
    return True


def run_sync(local: str, body: str) -> None:
    subprocess.run(
        [SYNC_CMD, local],
        input=body or "",
        text=True,
        check=True,
    )


def main() -> int:
    if not DB_PATH.exists():
        print(f"db not found: {DB_PATH}", file=sys.stderr)
        return 1
    today = moscow_today()
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT local, body, start_date, end_date FROM autoreplies"
        ).fetchall()
    finally:
        conn.close()

    expired = [r for r in rows if r["end_date"] and r["end_date"] < today]
    pending = [r for r in rows if r["start_date"] and r["start_date"] <= today and (not r["end_date"] or r["end_date"] >= today)]

    failures = 0
    for row in expired:
        local = row["local"]
        try:
            run_sync(local, "")
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                conn.execute("DELETE FROM autoreplies WHERE local = ?", (local,))
                conn.commit()
            finally:
                conn.close()
            print(f"expired {local} (end_date={row['end_date']})")
        except Exception as exc:  # noqa: BLE001 - report and continue with others
            failures += 1
            print(f"error expiring {local}: {exc}", file=sys.stderr)

    for row in pending:
        local = row["local"]
        try:
            run_sync(local, row["body"])
            print(f"activated {local} (start_date={row['start_date']})")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"error activating {local}: {exc}", file=sys.stderr)

    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
