"""Per-mailbox vacation text with optional date range. Does not write the users table.

Dates are inclusive calendar days in the configured timezone (MAIL_TZ,
    default UTC), stored as
YYYY-MM-DD. An empty date means "no boundary": empty start = active from now,
empty end = never expires. Rows created before the migration keep both dates
empty and therefore behave exactly as before.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone

from db import session
from users import UsersError, mail_domain, validate_local, _now

MAX_BODY = 4000
_SIEVE_WORDS = ("fileinto", "redirect", "discard", "reject", "execute", "pipe")

# Timezone for calendar-day boundaries. Override with MAIL_TZ.
DEFAULT_TZ = "UTC"
_FALLBACK_OFFSET_MINUTES = 0


def _tz_offset_minutes() -> int:
    name = os.environ.get("MAIL_TZ", DEFAULT_TZ)
    try:
        from zoneinfo import ZoneInfo

        offset = datetime.now(ZoneInfo(name)).utcoffset()
    except Exception:
        return _FALLBACK_OFFSET_MINUTES
    return int(offset.total_seconds() // 60) if offset else 0


def _local_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=_tz_offset_minutes())


def _local_today() -> str:
    return _local_now().strftime("%Y-%m-%d")


def validate_date(raw: str | None, field: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise UsersError(f"invalid {field}") from exc
    return text


def is_active(start_date: str, end_date: str, today: str | None = None) -> bool:
    """Inclusive range check on calendar days (MAIL_TZ)."""
    day = today if today is not None else _local_today()
    if start_date and day < start_date:
        return False
    if end_date and day > end_date:
        return False
    return True


def list_autoreply(local: str) -> dict[str, str]:
    local = validate_local(local)
    with session() as conn:
        if conn.execute("SELECT 1 FROM users WHERE local = ?", (local,)).fetchone() is None:
            raise UsersError("user not found")
        row = conn.execute(
            "SELECT body, start_date, end_date FROM autoreplies WHERE local = ?",
            (local,),
        ).fetchone()
    return {
        "local": local,
        "body": row["body"] if row else "",
        "start_date": row["start_date"] if row else "",
        "end_date": row["end_date"] if row else "",
    }


def set_autoreply(
    local: str,
    body: str | None,
    start_date: str | None = "",
    end_date: str | None = "",
) -> dict[str, str]:
    local = validate_local(local)
    text = _normalize_body(body)
    start = validate_date(start_date, "start date")
    end = validate_date(end_date, "end date")
    if text and start and end and end < start:
        raise UsersError("end date before start date")
    previous = ""
    with session() as conn:
        if conn.execute("SELECT 1 FROM users WHERE local = ?", (local,)).fetchone() is None:
            raise UsersError("user not found")
        row = conn.execute(
            "SELECT body, start_date, end_date FROM autoreplies WHERE local = ?",
            (local,),
        ).fetchone()
        previous = row["body"] if row else ""
        if text:
            conn.execute(
                """
                INSERT INTO autoreplies (local, body, updated_at, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(local) DO UPDATE SET
                    body = excluded.body,
                    updated_at = excluded.updated_at,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date
                """,
                (local, text, _now(), start, end),
            )
        else:
            conn.execute("DELETE FROM autoreplies WHERE local = ?", (local,))
    # A window that is not active right now must not leave a live sieve script:
    # future start -> keep files off until the window opens (timer activates it),
    # past end -> clear files now, for good.
    if text and not is_active(start, end):
        sync_autoreply_files(local, "")
    else:
        _sync_or_rollback(local, previous)
    return {"local": local, "body": text, "start_date": start, "end_date": end}


def read_body(local: str) -> str:
    local = validate_local(local)
    with session() as conn:
        row = conn.execute(
            "SELECT body FROM autoreplies WHERE local = ?",
            (local,),
        ).fetchone()
    return row["body"] if row else ""


def restore_body(local: str, body: str) -> None:
    local = validate_local(local)
    text = (body or "").strip()
    with session() as conn:
        if text:
            conn.execute(
                """
                INSERT INTO autoreplies (local, body, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(local) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
                """,
                (local, text, _now()),
            )
        else:
            conn.execute("DELETE FROM autoreplies WHERE local = ?", (local,))


def expired_locals(today: str | None = None) -> list[str]:
    """Locals whose autoreply window has passed — to be switched off for good."""
    day = today if today is not None else _local_today()
    with session() as conn:
        rows = conn.execute(
            "SELECT local, start_date, end_date FROM autoreplies WHERE end_date != ''"
        ).fetchall()
    return [row["local"] for row in rows if row["end_date"] < day]


def pending_locals(today: str | None = None) -> list[str]:
    """Locals whose autoreply window has not started yet."""
    day = today if today is not None else _local_today()
    with session() as conn:
        rows = conn.execute(
            "SELECT local, start_date, end_date FROM autoreplies WHERE start_date != ''"
        ).fetchall()
    return [row["local"] for row in rows if row["start_date"] > day]


def sync_autoreply_files(local: str, body: str) -> None:
    if os.environ.get("SKIP_AUTOREPLY_SYNC", "").strip() in {"1", "true", "yes"}:
        return
    local = validate_local(local)
    cmd = os.environ.get("MAIL_AUTOREPLY_SYNC", "/usr/local/sbin/mail-autoreply-sync")
    argv = [cmd, local] if os.geteuid() == 0 else ["sudo", "--non-interactive", cmd, local]
    subprocess.run(argv, input=body or "", text=True, check=True)


def _normalize_body(raw: str | None) -> str:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\x00" in text:
        raise UsersError("invalid autoreply")
    if len(text) > MAX_BODY:
        raise UsersError("autoreply too long")
    lowered = text.lower()
    for word in _SIEVE_WORDS:
        if _has_word(lowered, word):
            raise UsersError("invalid autoreply")
    return text


def _has_word(text: str, word: str) -> bool:
    start = 0
    while True:
        idx = text.find(word, start)
        if idx < 0:
            return False
        before = text[idx - 1] if idx > 0 else " "
        after = text[idx + len(word)] if idx + len(word) < len(text) else " "
        if not before.isalnum() and not after.isalnum() and before != "_" and after != "_":
            return True
        start = idx + 1


def _sync_or_rollback(local: str, previous: str) -> None:
    try:
        sync_autoreply_files(local, list_autoreply(local)["body"])
    except Exception:
        restore_body(local, previous)
        raise
