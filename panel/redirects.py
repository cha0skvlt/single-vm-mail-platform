"""Local mailbox-to-mailbox redirects (keep a copy in the source)."""

from __future__ import annotations

from db import session
from users import UsersError, _sync_or_rollback, mail_domain, validate_local

MAX_REDIRECTS = 10


def list_redirects(local: str) -> dict[str, object]:
    local = validate_local(local)
    with session() as conn:
        if conn.execute("SELECT 1 FROM users WHERE local = ?", (local,)).fetchone() is None:
            raise UsersError("user not found")
        rows = conn.execute(
            "SELECT dest FROM redirects WHERE src = ? ORDER BY dest",
            (local,),
        ).fetchall()
    return {"local": local, "destinations": [row["dest"] for row in rows]}


def parse_destinations(raw: str) -> list[str]:
    parts = [chunk.strip() for chunk in (raw or "").replace(";", ",").split(",")]
    dests: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        if "@" in part:
            local_part, domain = part.split("@", 1)
            if domain.strip().lower() != mail_domain():
                raise UsersError("local mailbox only")
            part = local_part
        dest = validate_local(part)
        if dest in seen:
            continue
        seen.add(dest)
        dests.append(dest)
    return dests


def set_redirects(local: str, destinations: list[str] | str) -> dict[str, object]:
    local = validate_local(local)
    if isinstance(destinations, str):
        dests = parse_destinations(destinations)
    else:
        dests = parse_destinations(",".join(destinations))
    if len(dests) > MAX_REDIRECTS:
        raise UsersError("too many redirects")
    previous: list[str] = []
    with session() as conn:
        if conn.execute("SELECT 1 FROM users WHERE local = ?", (local,)).fetchone() is None:
            raise UsersError("user not found")
        previous = [
            row["dest"]
            for row in conn.execute(
                "SELECT dest FROM redirects WHERE src = ? ORDER BY dest",
                (local,),
            ).fetchall()
        ]
        have = {
            row["local"]
            for row in conn.execute("SELECT local FROM users").fetchall()
        }
        for dest in dests:
            if dest == local:
                raise UsersError("redirect to self")
            if dest not in have:
                raise UsersError("unknown mailbox")
        if _has_cycle(conn, local, dests):
            raise UsersError("redirect cycle")
        conn.execute("DELETE FROM redirects WHERE src = ?", (local,))
        conn.executemany(
            "INSERT INTO redirects (src, dest) VALUES (?, ?)",
            [(local, dest) for dest in dests],
        )
    _sync_or_rollback(lambda: _restore_src(local, previous))
    return {"local": local, "destinations": dests}


def _has_cycle(conn, src: str, dests: list[str]) -> bool:
    edges: dict[str, list[str]] = {}
    for row in conn.execute("SELECT src, dest FROM redirects"):
        if row["src"] == src:
            continue
        edges.setdefault(row["src"], []).append(row["dest"])
    edges[src] = list(dests)

    def reaches(start: str, target: str, seen: set[str]) -> bool:
        if start == target:
            return True
        if start in seen:
            return False
        seen.add(start)
        return any(reaches(nxt, target, seen) for nxt in edges.get(start, []))

    return any(reaches(dest, src, set()) for dest in dests)


def _restore_src(local: str, dests: list[str]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM redirects WHERE src = ?", (local,))
        conn.executemany(
            "INSERT INTO redirects (src, dest) VALUES (?, ?)",
            [(local, dest) for dest in dests],
        )
