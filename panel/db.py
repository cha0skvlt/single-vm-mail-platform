"""SQLite mailbox accounts — source of truth (hashes only)."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    local TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS redirects (
    src TEXT NOT NULL,
    dest TEXT NOT NULL,
    PRIMARY KEY (src, dest),
    FOREIGN KEY (src) REFERENCES users(local) ON DELETE CASCADE,
    FOREIGN KEY (dest) REFERENCES users(local) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS autoreplies (
    local TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (local) REFERENCES users(local) ON DELETE CASCADE
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add autoreply date columns to databases created before they existed."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(autoreplies)")}
    if "start_date" not in columns:
        conn.execute("ALTER TABLE autoreplies ADD COLUMN start_date TEXT NOT NULL DEFAULT ''")
    if "end_date" not in columns:
        conn.execute("ALTER TABLE autoreplies ADD COLUMN end_date TEXT NOT NULL DEFAULT ''")


def db_path() -> Path:
    return Path(os.environ.get("MAILPANEL_DB", "/var/lib/mailpanel/users.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def user_count(conn: sqlite3.Connection | None = None) -> int:
    if conn is not None:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"])
    with session() as owned:
        return user_count(owned)
